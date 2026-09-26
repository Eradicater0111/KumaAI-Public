from types import SimpleNamespace

import app.agent.kuma_agent as kuma_agent_module
from app.agent.kuma_agent import KumaAgent


def make_agent():
    agent = KumaAgent.__new__(
        KumaAgent
    )

    agent.model = "test-model"

    agent.messages = [
        {
            "role": "system",
            "content": "You are KUMA.",
        },
        {
            "role": "assistant",
            "content": "Earlier context.",
        },
        {
            "role": "user",
            "content": (
                "Say exactly KUMA_TEST_123 "
                "and nothing else."
            ),
        },
    ]

    return agent


def test_blocked_tool_recovery_uses_zero_tools(
    monkeypatch,
):
    agent = make_agent()

    captured = {}

    def fake_chat(
        **kwargs,
    ):
        captured.update(
            kwargs
        )

        return SimpleNamespace(
            message=SimpleNamespace(
                content="KUMA_TEST_123"
            )
        )

    monkeypatch.setattr(
        kuma_agent_module,
        "chat",
        fake_chat,
    )

    result = (
        agent
        ._recover_conversational_response_after_blocked_tool(
            user_message=(
                "Say exactly KUMA_TEST_123 "
                "and nothing else."
            ),
            blocked_tool_name="click_vision",
        )
    )

    assert result == "KUMA_TEST_123"

    assert captured[
        "tools"
    ] == []

    assert captured[
        "think"
    ] is False

    assert (
        captured[
            "messages"
        ][-1]
        == {
            "role": "user",
            "content": (
                "Say exactly KUMA_TEST_123 "
                "and nothing else."
            ),
        }
    )


def test_blocked_tool_recovery_drops_tool_call_context(
    monkeypatch,
):
    agent = make_agent()

    agent.messages.append(
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "function": {
                        "name": "click_vision",
                    }
                }
            ],
        }
    )

    captured = {}

    def fake_chat(
        **kwargs,
    ):
        captured.update(
            kwargs
        )

        return SimpleNamespace(
            message=SimpleNamespace(
                content="safe answer"
            )
        )

    monkeypatch.setattr(
        kuma_agent_module,
        "chat",
        fake_chat,
    )

    result = (
        agent
        ._recover_conversational_response_after_blocked_tool(
            user_message="hello",
            blocked_tool_name="click_vision",
        )
    )

    assert result == "safe answer"

    assert all(
        not message.get(
            "tool_calls"
        )
        for message in captured[
            "messages"
        ]
    )


def test_canned_greeting_fallback_removed():
    from pathlib import Path

    source = (
        Path(__file__)
        .with_name(
            "kuma_agent.py"
        )
        .read_text()
    )

    assert (
        "I'm here. How can I help?"
        not in source
    )
