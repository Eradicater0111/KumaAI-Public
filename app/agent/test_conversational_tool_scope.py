from types import SimpleNamespace

from app.agent.kuma_agent import KumaAgent


def make_agent():
    agent = KumaAgent.__new__(
        KumaAgent
    )

    agent.tool_registry = {
        "analyze_screen": SimpleNamespace(
            name="analyze_screen"
        ),
        "inspect_system": SimpleNamespace(
            name="inspect_system"
        ),
        "click_vision": SimpleNamespace(
            name="click_vision"
        ),
        "type_text": SimpleNamespace(
            name="type_text"
        ),
    }

    agent._successful_actions = {}

    return agent


def user_message(text):
    return [
        {
            "role": "user",
            "content": text,
        }
    ]


def test_pure_conversation_exposes_zero_tools():
    agent = make_agent()

    tools = agent.get_available_tools(
        user_message(
            "Tell me a short joke."
        )
    )

    assert tools == []


def test_exact_output_request_exposes_zero_tools():
    agent = make_agent()

    tools = agent.get_available_tools(
        user_message(
            "Say exactly KUMA_TEST_123 "
            "and nothing else."
        )
    )

    assert tools == []


def test_math_question_exposes_zero_tools():
    agent = make_agent()

    tools = agent.get_available_tools(
        user_message(
            "What is 2 + 2?"
        )
    )

    assert tools == []


def test_screen_request_keeps_observation_scope():
    agent = make_agent()

    tools = agent.get_available_tools(
        user_message(
            "What's on my screen?"
        )
    )

    assert tools == [
        agent.tool_registry[
            "analyze_screen"
        ]
    ]


def test_system_request_keeps_system_scope():
    agent = make_agent()

    tools = agent.get_available_tools(
        user_message(
            "Inspect my system"
        )
    )

    assert tools == [
        agent.tool_registry[
            "inspect_system"
        ]
    ]


def test_explicit_ui_action_does_not_enter_conversation_fast_path():
    assert (
        KumaAgent
        ._is_clearly_conversational_request(
            "Click the Send button"
        )
        is False
    )


def test_explicit_app_action_does_not_enter_conversation_fast_path():
    assert (
        KumaAgent
        ._is_clearly_conversational_request(
            "Open Safari"
        )
        is False
    )


def test_general_advice_remains_conversation():
    assert (
        KumaAgent
        ._is_clearly_conversational_request(
            "How do I become more disciplined?"
        )
        is True
    )
