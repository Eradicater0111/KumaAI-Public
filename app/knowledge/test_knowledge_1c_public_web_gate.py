from __future__ import annotations

import ast
from pathlib import Path

import app.agent.kuma_agent as kuma_agent_module
from app.agent.kuma_agent import KumaAgent
from app.knowledge import (
    KnowledgeDomain,
    KnowledgeResolver,
)


def _agent():
    return KumaAgent.__new__(
        KumaAgent
    )


def test_public_web_positive_intents():
    resolver = KnowledgeResolver()

    for request in (
        "latest OpenAI news",
        "today crypto currency value",
        "current Python release",
        "search the web for local AI models",
        "Bitcoin price",
    ):
        plan = resolver.plan(
            request
        )

        assert (
            plan.intent.domain
            == KnowledgeDomain.PUBLIC_WEB
        )

        assert (
            "web"
            in plan.provider_order
        )


def test_time_words_alone_do_not_force_public_web():
    resolver = KnowledgeResolver()

    for request in (
        "what should I focus on today?",
        "what do you think I should work on this week?",
        "open Chrome today",
        "tell me a joke today",
    ):
        plan = resolver.plan(
            request
        )

        assert (
            plan.intent.domain
            != KnowledgeDomain.PUBLIC_WEB
        )


def test_action_request_with_freshness_word_is_not_public_web():
    plan = KnowledgeResolver().plan(
        "open Chrome today"
    )

    assert (
        plan.intent.domain
        != KnowledgeDomain.PUBLIC_WEB
    )

    assert (
        "web"
        not in plan.provider_order
    )


def test_agent_web_gate_allows_public_web():
    agent = _agent()

    assert agent._knowledge_request_should_use_web(
        [
            {
                "role": "user",
                "content": "latest OpenAI news",
            }
        ]
    ) is True


def test_agent_web_gate_rejects_personal_advice_and_action():
    agent = _agent()

    for request in (
        "what should I focus on today?",
        "open Chrome today",
    ):
        assert agent._knowledge_request_should_use_web(
            [
                {
                    "role": "user",
                    "content": request,
                }
            ]
        ) is False


def test_agent_web_gate_preserves_weather_location_boundaries():
    agent = _agent()

    assert agent._knowledge_request_should_use_web(
        [
            {
                "role": "user",
                "content": "weather in Bengaluru tomorrow",
            }
        ]
    ) is True

    assert agent._knowledge_request_should_use_web(
        [
            {
                "role": "user",
                "content": "weather near me tomorrow",
            }
        ]
    ) is False


def test_agent_web_gate_rejects_post_tool_continuation():
    agent = _agent()

    assert agent._knowledge_request_should_use_web(
        [
            {
                "role": "user",
                "content": "latest OpenAI news",
            },
            {
                "role": "tool",
                "content": "evidence",
            },
        ]
    ) is False


def test_legacy_internet_router_is_semantically_gated():
    source = Path(
        kuma_agent_module.__file__
    ).read_text()

    assert (
        "KUMA KNOWLEDGE-1C — UNIFIED PUBLIC-WEB GATE"
        in source
    )

    tree = ast.parse(
        source
    )

    cls = next(
        node
        for node in tree.body
        if isinstance(
            node,
            ast.ClassDef,
        )
        and node.name == "KumaAgent"
    )

    method = next(
        node
        for node in cls.body
        if isinstance(
            node,
            ast.FunctionDef,
        )
        and node.name == "get_available_tools"
    )

    segment = ast.get_source_segment(
        source,
        method,
    )

    assert (
        "_knowledge_request_should_use_web(messages)"
        in segment
    )

    assert (
        "KUMA INTERNET → Current/public-web knowledge request."
        in segment
    )
