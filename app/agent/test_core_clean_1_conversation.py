from __future__ import annotations

import app.agent.kuma_agent as kuma_agent_module
from app.agent.kuma_agent import KumaAgent


def _agent(messages=None):
    agent = KumaAgent.__new__(KumaAgent)
    agent.messages = list(messages or [])
    return agent


def test_build_context_keeps_dialogue_and_current_user_once():
    agent = _agent([
        {"role": "system", "content": "system"},
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hey"},
        {"role": "user", "content": "current"},
    ])

    context = agent.build_context_messages("current", max_messages=6)

    assert context == [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hey"},
        {"role": "user", "content": "current"},
    ]


def test_build_context_filters_stale_assistant_screen_claims():
    agent = _agent([
        {"role": "system", "content": "system"},
        {"role": "user", "content": "screen?"},
        {"role": "assistant", "content": "ACTIVE_APPLICATION: Safari"},
    ])

    context = agent.build_context_messages("hello", max_messages=6)

    assert context == [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "screen?"},
        {"role": "user", "content": "hello"},
    ]


def test_agent_is_single_persistence_owner(monkeypatch):
    saved = []
    monkeypatch.setattr(
        kuma_agent_module,
        "save_message",
        lambda role, content: saved.append((role, content)),
    )

    agent = _agent([
        {"role": "system", "content": "system"},
        {"role": "user", "content": "hello"},
    ])

    result = agent._save_and_return("hey")

    assert result == "hey"
    assert saved == [("assistant", "hey")]
    assert agent.messages[-1] == {"role": "assistant", "content": "hey"}


def test_history_loader_collapses_legacy_double_writes(monkeypatch):
    monkeypatch.setattr(
        kuma_agent_module,
        "get_recent_messages",
        lambda limit=12: [
            ("user", "one"),
            ("user", "one"),
            ("assistant", "two"),
            ("assistant", "two"),
        ],
    )

    agent = _agent([{"role": "system", "content": "system"}])
    agent.load_conversation_history()

    assert agent.messages == [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "one"},
        {"role": "assistant", "content": "two"},
    ]


def test_window_does_not_write_conversation_messages():
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    source = (root / "app" / "ui" / "window.py").read_text()
    assert "save_message(" not in source
