from src.ham.agent_router import is_local_repo_operation_intent, route_agent_intent


def test_router_cursor_launch_explicit() -> None:
    out = route_agent_intent(
        "have Cursor implement the SDK adapter fix",
        default_project_id="project.demo-123",
    )
    assert out.intent == "agent_launch"
    assert out.provider == "cursor"
    assert out.task and "sdk adapter fix" in out.task.lower()


def test_router_factory_launch_explicit_blocked() -> None:
    out = route_agent_intent(
        "send this to Factory Droid to patch tests",
        default_project_id="project.demo-123",
    )
    assert out.intent == "agent_launch"
    assert out.provider == "factory"
    assert out.reason_code == "provider_not_implemented"


def test_router_preview_intent() -> None:
    out = route_agent_intent(
        "create an agent preview to update chat persistence",
        default_project_id="project.demo-123",
    )
    assert out.intent == "agent_preview"
    assert out.provider == "cursor"


def test_router_status_intent() -> None:
    out = route_agent_intent(
        "check status of that agent",
        default_project_id="project.demo-123",
    )
    assert out.intent == "agent_status"


def test_router_uses_project_mentioned_in_text() -> None:
    out = route_agent_intent("fire up an agent on project.alpha-123 to patch tests")
    assert out.intent == "agent_launch"
    assert "project" not in out.missing


def test_router_extracts_explicit_repo_ref_and_task() -> None:
    out = route_agent_intent(
        (
            "Launch a Cursor Cloud Agent for repo Code-Munkiz/ham on branch main. "
            "Task: update docs only."
        ),
        default_project_id=None,
    )
    assert out.intent == "agent_launch"
    assert out.provider == "cursor"
    assert out.repo_ref == "Code-Munkiz/ham"
    assert out.branch == "main"
    assert out.task and "update docs only" in out.task.lower()


def test_router_normal_chat_not_over_triggered() -> None:
    out = route_agent_intent("explain what a cloud is")
    assert out.intent == "normal_chat"


def test_local_repo_operation_intent_detected_for_git_and_gh() -> None:
    text = "cd /home/user/.hermes/hermes-agent\ngh auth status\ngit pull --rebase origin main\ngit push origin main"
    assert is_local_repo_operation_intent(text) is True
    out = route_agent_intent(text, default_project_id=None)
    assert out.intent == "normal_chat"
    assert out.reason_code == "local_repo_operation"


def test_local_repo_operation_not_triggered_for_cloud_agent_status() -> None:
    assert is_local_repo_operation_intent("check cloud agent status") is False
