from __future__ import annotations

from app.agent.kuma_agent import KumaAgent


def _agent():
    return KumaAgent.__new__(
        KumaAgent
    )


def test_exact_pending_web_continuation_is_accepted_once():
    agent = _agent()

    agent._pending_grounded_web_query = (
        "weather in Bengaluru"
    )

    accepted = (
        agent._consume_grounded_web_continuation(
            "Bengaluru",
            "web_search",
            {
                "query": "weather in Bengaluru",
                "max_results": 5,
            },
        )
    )

    assert accepted is True

    # One-shot token must be consumed.
    assert (
        agent._consume_grounded_web_continuation(
            "Bengaluru",
            "web_search",
            {
                "query": "weather in Bengaluru",
            },
        )
        is False
    )


def test_pending_web_continuation_rejects_wrong_query():
    agent = _agent()

    agent._pending_grounded_web_query = (
        "weather in Bengaluru"
    )

    assert (
        agent._consume_grounded_web_continuation(
            "Bengaluru",
            "web_search",
            {
                "query": "latest bank passwords",
            },
        )
        is False
    )


def test_pending_web_continuation_never_authorizes_other_tools():
    agent = _agent()

    agent._pending_grounded_web_query = (
        "weather in Bengaluru"
    )

    assert (
        agent._consume_grounded_web_continuation(
            "Bengaluru",
            "open_app",
            {
                "app_name": "Terminal",
            },
        )
        is False
    )

    assert (
        agent._pending_grounded_web_query
        == "weather in Bengaluru"
    )


def test_empty_current_message_cannot_use_pending_continuation():
    agent = _agent()

    agent._pending_grounded_web_query = (
        "weather in Bengaluru"
    )

    assert (
        agent._consume_grounded_web_continuation(
            "",
            "web_search",
            {
                "query": "weather in Bengaluru",
            },
        )
        is False
    )

    assert (
        agent._pending_grounded_web_query
        == ""
    )
