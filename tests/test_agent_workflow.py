from bughound_agent import BugHoundAgent
from llm_client import MockClient


class ProseWrappedJsonClient:
    def complete(self, system_prompt: str, user_prompt: str) -> str:
        if "Return ONLY valid JSON" in system_prompt:
            return (
                "Here are issues: "
                '[{"type":"Code Quality","severity":"Low","msg":"Use logging instead of print statements."}]'
            )
        return "def f():\n    logging.info('hi')\n    return True\n"


class InvalidFixClient:
    def complete(self, system_prompt: str, user_prompt: str) -> str:
        if "Return ONLY valid JSON" in system_prompt:
            return '[{"type":"Code Quality","severity":"Low","msg":"Use logging instead of print statements."}]'
        return "def f(:\n    return True\n"


class RenamingFixClient:
    def complete(self, system_prompt: str, user_prompt: str) -> str:
        if "Return ONLY valid JSON" in system_prompt:
            return '[{"type":"Code Quality","severity":"Low","msg":"Use logging instead of print statements."}]'
        return "import logging\n\ndef renamed(a, b):\n    logging.info('changed')\n    return a + b\n"


class OverEditingFixClient:
    def complete(self, system_prompt: str, user_prompt: str) -> str:
        if "Return ONLY valid JSON" in system_prompt:
            return '[{"type":"Code Quality","severity":"Low","msg":"Use logging instead of print statements."}]'
        return (
            "import logging\n"
            "\n"
            "def f():\n"
            "    logging.info('hi')\n"
            "    x = 1\n"
            "    y = 2\n"
            "    z = x + y\n"
            "    a = z * 2\n"
            "    b = a - 3\n"
            "    c = b / 2\n"
            "    d = c + 7\n"
            "    e = d * 5\n"
            "    f1 = e - 11\n"
            "    g = f1 + 13\n"
            "    h = g * 17\n"
            "    i = h - 19\n"
            "    j = i / 23\n"
            "    k = j + 29\n"
            "    l = k * 31\n"
            "    return l > 0\n"
        )


def test_workflow_runs_in_offline_mode_and_returns_shape():
    agent = BugHoundAgent(client=None)  # heuristic-only
    code = "def f():\n    print('hi')\n    return True\n"
    result = agent.run(code)

    assert isinstance(result, dict)
    assert "issues" in result
    assert "fixed_code" in result
    assert "risk" in result
    assert "logs" in result

    assert isinstance(result["issues"], list)
    assert isinstance(result["fixed_code"], str)
    assert isinstance(result["risk"], dict)
    assert isinstance(result["logs"], list)
    assert len(result["logs"]) > 0


def test_offline_mode_detects_print_issue():
    agent = BugHoundAgent(client=None)
    code = "def f():\n    print('hi')\n    return True\n"
    result = agent.run(code)

    assert any(issue.get("type") == "Code Quality" for issue in result["issues"])


def test_offline_mode_proposes_logging_fix_for_print():
    agent = BugHoundAgent(client=None)
    code = "def f():\n    print('hi')\n    return True\n"
    result = agent.run(code)

    fixed = result["fixed_code"]
    assert "logging" in fixed
    assert "logging.info(" in fixed


def test_mock_client_forces_llm_fallback_to_heuristics_for_analysis():
    # MockClient returns non-JSON for analyzer prompts, so agent should fall back.
    agent = BugHoundAgent(client=MockClient())
    code = "def f():\n    print('hi')\n    return True\n"
    result = agent.run(code)

    assert any(issue.get("type") == "Code Quality" for issue in result["issues"])
    # Ensure we logged the fallback path
    assert any("Falling back to heuristics" in entry.get("message", "") for entry in result["logs"])


def test_strict_mode_rejects_prose_wrapped_json_and_falls_back():
    agent = BugHoundAgent(client=ProseWrappedJsonClient(), strict_mode=True)
    code = "def f():\n    print('hi')\n    return True\n"
    result = agent.run(code)

    assert any(issue.get("type") == "Code Quality" for issue in result["issues"])
    assert any("not parseable JSON" in entry.get("message", "") for entry in result["logs"])


def test_relaxed_mode_accepts_prose_wrapped_json():
    agent = BugHoundAgent(client=ProseWrappedJsonClient(), strict_mode=False)
    code = "def f():\n    print('hi')\n    return True\n"
    result = agent.run(code)

    assert result["issues"] == [
        {
            "type": "Code Quality",
            "severity": "Low",
            "msg": "Use logging instead of print statements.",
        }
    ]
    assert not any("not parseable JSON" in entry.get("message", "") for entry in result["logs"])


def test_strict_mode_rejects_invalid_llm_fix_and_uses_heuristic_fixer():
    agent = BugHoundAgent(client=InvalidFixClient(), strict_mode=True)
    code = "def f():\n    print('hi')\n    return True\n"
    result = agent.run(code)

    assert "logging.info(" in result["fixed_code"]
    assert any("failed strict validation" in entry.get("message", "") for entry in result["logs"])


def test_strict_mode_rejects_function_renaming_to_limit_scope_creep():
    agent = BugHoundAgent(client=RenamingFixClient(), strict_mode=True)
    code = "def add(a, b):\n    print(a + b)\n    return a + b\n"
    result = agent.run(code)

    assert "def add(a, b):" in result["fixed_code"]
    assert "def renamed(" not in result["fixed_code"]
    assert any("failed strict validation" in entry.get("message", "") for entry in result["logs"])


def test_strict_mode_rejects_excessive_low_severity_rewrite():
    agent = BugHoundAgent(client=OverEditingFixClient(), strict_mode=True)
    code = "def f():\n    print('hi')\n    return True\n"
    result = agent.run(code)

    assert "logging.info(" in result["fixed_code"]
    assert any("failed strict validation" in entry.get("message", "") for entry in result["logs"])
