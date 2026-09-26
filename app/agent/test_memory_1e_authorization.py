from app.agent.kuma_agent import KumaAgent


def agent():
    return KumaAgent.__new__(KumaAgent)


def test_plain_preference_does_not_authorize_remember():
    assert not agent().explicitly_requests_tool_action(
        "I prefer VS Code.",
        "remember",
        {"category": "preferences", "key": "editor", "value": "VS Code"},
    )


def test_plain_project_fact_does_not_authorize_remember():
    assert not agent().explicitly_requests_tool_action(
        "KUMA is my desktop AI project.",
        "remember",
        {"category": "projects", "key": "kuma", "value": "desktop AI project"},
    )


def test_explicit_remember_request_authorizes_remember():
    assert agent().explicitly_requests_tool_action(
        "Remember that I prefer VS Code.",
        "remember",
        {"category": "preferences", "key": "editor", "value": "VS Code"},
    )


def test_keep_in_mind_is_explicit_authorization():
    assert agent().explicitly_requests_tool_action(
        "Keep in mind that KUMA is my desktop AI project.",
        "remember",
        {"category": "projects", "key": "kuma", "value": "desktop AI project"},
    )
