# BugHound Mini Model Card (Reflection)

Completed after iterative testing in this repo, including strict-mode parsing, anti-overedit guardrails, and risk policy tuning.

---

## 1) What is this system?

**Name:** BugHound  
**Purpose:** Analyze a Python snippet, propose a fix, and run reliability checks before suggesting whether the fix should be auto-applied.

**Intended users:** Students learning agentic workflows and AI reliability concepts.

Additional intended users:
- Instructors/demo leaders who need a transparent, inspectable example of an agent loop.
- Beginner developers who want a "safe first pass" on small Python snippets.

---

## 2) How does it work?

BugHound follows a five-step loop:

1. PLAN
- Logs the intended workflow and active strictness policy.

2. ANALYZE
- Heuristic mode: uses local rules to detect `print(` usage, bare `except:`, and `TODO` markers.
- Gemini mode: sends analyzer prompts and expects strict JSON issue objects.
- If Gemini output is malformed or API calls fail, BugHound falls back to heuristics.

3. ACT
- Heuristic mode: applies minimal deterministic rewrites (for example, `print` -> `logging.info`, bare `except:` -> `except Exception as e:`).
- Gemini mode: requests a full rewritten snippet constrained to minimal edits.
- In strict mode, Gemini fixes are validated with AST parsing, banned pattern checks, signature-preservation checks (for low/medium severity), and severity-aware change budgets.
- Invalid Gemini fixes fall back to heuristic fixes.

4. TEST
- Runs `assess_risk` on original vs fixed code and issue severity.
- Produces `score`, `level`, `reasons`, and `should_autofix`.

5. REFLECT
- If `should_autofix` is true, logs that auto-apply is acceptable.
- Otherwise explicitly recommends human review.

---

## 3) Inputs and outputs

**Inputs:**

- Tested snippets:
	- `sample_code/print_spam.py`: small function with multiple `print` statements.
	- `sample_code/flaky_try_except.py`: IO function with bare `except:`.
	- `sample_code/mixed_issues.py`: mixed `TODO`, `print`, and bare `except:`.
	- `sample_code/cleanish.py`: already-clean function using `logging`.
	- Additional synthetic test snippets in `tests/test_agent_workflow.py` to simulate malformed model outputs, over-editing, and signature changes.

- Input shape observed:
	- Short Python functions (3-15 lines).
	- Control-flow-heavy snippets with try/except.
	- Small scripts with code-quality smells.

**Outputs:**

- Issue types detected:
	- `Code Quality` (print statements)
	- `Reliability` (bare `except:`)
	- `Maintainability` (`TODO` markers)

- Fix types proposed:
	- Replace `print(` with `logging.info(` and add `import logging` if missing.
	- Replace bare `except:` with `except Exception as e:`.
	- Keep no-op behavior for already clean code where no issues are detected.
	- In strict mode, reject excessive model rewrites and fall back to heuristic edits.

- Risk report behavior:
	- Returns a bounded score (0-100), risk level (`low`/`medium`/`high`), textual reasons, and `should_autofix` boolean.
	- Auto-fix is now conservative: it requires low risk, score >= 90, no medium/high issues, max one issue, and no structural risk flags.

---

## 4) Reliability and safety rules

Rule A: Return statement preservation check
- What it checks:
	- If original code contains `return` and fixed code does not, BugHound deducts risk points and flags possible behavior change.
- Why it matters:
	- Losing a return can silently change function contracts and downstream logic.
- Possible false positive:
	- A valid refactor might replace an explicit return with an equivalent expression flow (rare in small snippets but possible).
- Possible false negative:
	- The fixed code may still contain `return` while changing return values or branches incorrectly.

Rule B: Significant size change check (`line_delta_ratio > 0.25`)
- What it checks:
	- Penalizes fixes that substantially change total code size.
- Why it matters:
	- Large diffs on small bugs are a common sign of over-editing and hidden behavior drift.
- Possible false positive:
	- A legitimate reliability fix (for example, adding required error handling and logging) can increase size and be penalized.
- Possible false negative:
	- A harmful rewrite with similar line count may evade this guardrail.

Rule C: Conservative auto-fix policy gates
- What it checks:
	- Even with low risk level, auto-fix is blocked unless score >= 90, issue count <= 1, no medium/high severities, and no structural risk detected.
- Why it matters:
	- Prevents optimistic auto-apply on ambiguous or multi-issue edits.
- Possible false positive:
	- Safe low-risk fixes with two tiny low-severity issues might still require manual review.
- Possible false negative:
	- A single-issue fix that passes gates could still contain subtle semantic mistakes not captured by static checks.

---

## 5) Observed failure modes

1. Model output parsing failure (analysis phase)
- Example:
	- A simulated model response wrapped a valid JSON array in prose.
- What went wrong:
	- In strict mode, BugHound intentionally rejected this output as non-compliant and fell back to heuristics.
- Reliability impact:
	- Accuracy may drop when fallback heuristics are less expressive than Gemini, but safety improves.

2. Over-editing / scope creep in model fix (act phase)
- Example:
	- A simulated model rewrite renamed functions and introduced many unrelated lines for a low-severity issue.
- What went wrong:
	- The edit was much broader than required.
- Mitigation implemented:
	- Strict validation now rejects low/medium fixes that alter function signatures and enforces severity-aware line-change limits.

3. API/network failure path
- Example:
	- Analyzer/fixer API exceptions are caught and logged.
- What went wrong:
	- Gemini result unavailable.
- Mitigation:
	- Immediate fallback to deterministic heuristic analysis/fix.

---

## 6) Heuristic vs Gemini comparison

Heuristic mode
- Strengths:
	- Deterministic and consistent for known patterns (`print`, bare `except:`, `TODO`).
	- Predictable minimal edits and stable behavior under failures.
- Weaknesses:
	- Narrow coverage; likely misses issues outside hard-coded patterns.

Gemini mode
- Strengths:
	- Potentially better semantic understanding and broader issue detection.
	- Can generate context-aware rewrites beyond simple regex transforms.
- Weaknesses:
	- Output may violate format constraints or over-edit code.
	- Requires strict validation and fallback to maintain reliability.

Observed discrepancy summary
- Heuristics were more consistent in this iteration's automated tests.
- Gemini paths needed strict parsing/validation controls to avoid unreliable output acceptance.
- Risk scoring generally aligned with cautious intuition after conservative policy updates, especially for auto-fix gating.

---

## 7) Human-in-the-loop decision

Scenario:
- A high-severity issue fix requires changing function signatures or control-flow structure (for example, adding multiple new branches and helper functions).

Trigger to require human review:
- If function signatures changed OR structural risk detected OR severity is high/critical, force `should_autofix = False`.

Where to implement:
- Primary: `reliability/risk_assessor.py` auto-fix policy.
- Secondary: `bughound_agent.py` strict fix validation to reject suspicious rewrites before risk scoring.

User-facing message:
- "BugHound generated a fix, but structural or high-severity changes were detected. Auto-apply is disabled; please review the diff manually."

---

## 8) Improvement idea

Add one lightweight execution-based guardrail for small snippets.

Proposed change:
- After generating a fix, run both original and fixed snippets on a tiny canned input set (when safe and deterministic), then compare outputs.

Why this is low complexity:
- It can be limited to pure function snippets and skipped for file/network operations.
- It does not require external infrastructure.

Why it measurably helps:
- Catches semantic regressions that static checks (line count, signature preservation, keyword checks) can miss.
- Reduces false confidence in fixes that look syntactically valid but alter behavior.
