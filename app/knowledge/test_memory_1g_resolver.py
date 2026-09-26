from __future__ import annotations

import inspect

import pytest

from app.agent.kuma_agent import KumaAgent
from app.knowledge import (
    KnowledgeDomain,
    KnowledgeResolver,
)


def _agent():
    return KumaAgent.__new__(
        KumaAgent
    )


@pytest.mark.parametrize(
    "user_text",
    (
        "What do you remember about me?",
        "What did I tell you about my editor?",
        "Do you remember my preferred editor?",
        "Recall my editor preference.",
    ),
)
def test_explicit_memory_read_requests_plan_memory(user_text):
    plan = KnowledgeResolver().plan(
        user_text
    )

    assert (
        plan.intent.domain
        == KnowledgeDomain.MEMORY
    )
    assert plan.provider_order == (
        "memory",
    )
    assert plan.requires_device_location is False
    assert plan.authority == "NONE"
    assert plan.intent.authority == "NONE"


@pytest.mark.parametrize(
    "user_text",
    (
        "What is my preferred editor?",
        "What's my favorite editor?",
        "Which editor do I prefer?",
        "What project am I working on?",
    ),
)
def test_conservative_personal_fact_queries_can_plan_memory(user_text):
    plan = KnowledgeResolver().plan(
        user_text
    )

    assert (
        plan.intent.domain
        == KnowledgeDomain.MEMORY
    )
    assert plan.provider_order == (
        "memory",
    )


@pytest.mark.parametrize(
    "user_text",
    (
        "Remember that I use VS Code.",
        "Remember this preference.",
        "Save this preference.",
        "Keep in mind that I use VS Code.",
        "Don't forget that I use VS Code.",
    ),
)
def test_memory_write_language_is_not_memory_read_routing(user_text):
    plan = KnowledgeResolver().plan(
        user_text
    )

    assert (
        plan.intent.domain
        != KnowledgeDomain.MEMORY
    )
    assert (
        "memory"
        not in plan.provider_order
    )


@pytest.mark.parametrize(
    "user_text",
    (
        "Forget my editor preference.",
        "Remove from memory my editor preference.",
        "Delete from memory my editor preference.",
    ),
)
def test_forget_language_is_not_memory_read_routing(user_text):
    plan = KnowledgeResolver().plan(
        user_text
    )

    assert (
        plan.intent.domain
        != KnowledgeDomain.MEMORY
    )
    assert (
        "memory"
        not in plan.provider_order
    )


def test_action_using_preference_is_not_memory_knowledge_authority():
    plan = KnowledgeResolver().plan(
        "Open the editor I prefer."
    )

    assert (
        plan.intent.domain
        != KnowledgeDomain.MEMORY
    )
    assert (
        "memory"
        not in plan.provider_order
    )


def test_fresh_public_fact_still_uses_web():
    plan = KnowledgeResolver().plan(
        "latest version of VS Code"
    )

    assert (
        plan.intent.domain
        == KnowledgeDomain.PUBLIC_WEB
    )
    assert plan.provider_order == (
        "web",
    )


def test_weather_routing_is_unchanged():
    plan = KnowledgeResolver().plan(
        "weather in Bengaluru tomorrow"
    )

    assert (
        plan.intent.domain
        == KnowledgeDomain.WEATHER
    )
    assert plan.provider_order == (
        "weather.forecast",
        "web",
    )


def test_unknown_conversation_remains_unknown():
    plan = KnowledgeResolver().plan(
        "hello brother"
    )

    assert (
        plan.intent.domain
        == KnowledgeDomain.UNKNOWN
    )
    assert plan.provider_order == ()


def test_memory_plan_never_triggers_agent_public_web_gate():
    agent = _agent()

    assert agent._knowledge_request_should_use_web(
        [
            {
                "role": "user",
                "content": "What is my preferred editor?",
            }
        ]
    ) is False


def test_memory_domain_is_planning_only_and_has_no_memory_runtime_dependency():
    from app.knowledge import resolver

    source = inspect.getsource(
        resolver
    )

    assert (
        KnowledgeDomain.MEMORY.value
        == "memory"
    )

    assert "app.memory" not in source
    assert "get_memory_context" not in source
    assert "retrieve_memories" not in source
    assert "sqlite3" not in source
    assert "register_tool(" not in source
    assert "execute_command" not in source
