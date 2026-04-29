from src.ham.agent_router import route_agent_intent


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


def test_router_normal_chat_not_over_triggered() -> None:
    out = route_agent_intent("explain what a cloud is")
    assert out.intent == "normal_chat"
