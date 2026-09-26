from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

import app.agent.kuma_agent as kuma_agent_module
from app.agent.kuma_agent import KumaAgent
from app.knowledge import (
    KnowledgeDomain,
    KnowledgeIntent,
    KnowledgePlan,
    LocationScope,
    TemporalScope,
)


def _agent():
    return KumaAgent.__new__(
        KumaAgent
    )


def test_memory_read_plan_retrieves_bounded_memory_context():
    agent = _agent()

    with patch(
        "app.agent.kuma_agent.get_memory_context",
        return_value=(
            "Relevant long-term memories:\n"
            "- editor: VS Code"
        ),
    ) as memory_context:
        result = agent._memory_context_for_request(
            "What is my preferred editor?"
        )

    assert result == (
        "Relevant long-term memories:\n"
        "- editor: VS Code"
    )

    memory_context.assert_called_once_with(
        "What is my preferred editor?"
    )


@pytest.mark.parametrize(
    "user_text",
    (
        "hello brother",
        "latest Python release",
        "weather in Bengaluru tomorrow",
        "Remember that I use VS Code.",
        "Forget my editor preference.",
        "Open the editor I prefer.",
    ),
)
def test_non_memory_plans_never_query_long_term_memory(user_text):
    agent = _agent()

    with patch(
        "app.agent.kuma_agent.get_memory_context",
        return_value="should not be used",
    ) as memory_context:
        result = agent._memory_context_for_request(
            user_text
        )

    assert result == ""
    memory_context.assert_not_called()


def test_memory_provider_must_be_present_even_for_memory_domain():
    agent = _agent()

    plan = KnowledgePlan(
        intent=KnowledgeIntent(
            domain=KnowledgeDomain.MEMORY,
            temporal_scope=TemporalScope.UNSPECIFIED,
            location_scope=LocationScope.NONE,
            query="what do you remember",
        ),
        provider_order=(),
    )

    with patch.object(
        agent,
        "_knowledge_plan_for_request",
        return_value=plan,
    ):
        with patch(
            "app.agent.kuma_agent.get_memory_context",
            return_value="should not be used",
        ) as memory_context:
            result = agent._memory_context_for_request(
                "what do you remember"
            )

    assert result == ""
    memory_context.assert_not_called()


def test_memory_retrieval_failure_fails_closed_to_empty_context():
    agent = _agent()

    with patch(
        "app.agent.kuma_agent.get_memory_context",
        side_effect=RuntimeError(
            "embedding unavailable"
        ),
    ) as memory_context:
        result = agent._memory_context_for_request(
            "What do you remember about me?"
        )

    assert result == ""
    memory_context.assert_called_once()


def test_empty_memory_result_stays_empty():
    agent = _agent()

    with patch(
        "app.agent.kuma_agent.get_memory_context",
        return_value=None,
    ):
        assert (
            agent._memory_context_for_request(
                "What did I tell you about my editor?"
            )
            == ""
        )


def test_run_uses_resolver_gated_memory_helper_not_direct_retrieval():
    source = (
        Path(
            kuma_agent_module.__file__
        )
        .read_text()
    )

    import ast

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

    run_method = next(
        node
        for node in cls.body
        if isinstance(
            node,
            ast.FunctionDef,
        )
        and node.name == "run"
    )

    segment = ast.get_source_segment(
        source,
        run_method,
    )

    assert (
        "_memory_context_for_request("
        in segment
    )

    assert (
        "get_memory_context("
        not in segment
    )


def test_memory_helper_is_not_model_facing_tool_surface():
    source = (
        Path(
            kuma_agent_module.__file__
        )
        .read_text()
    )

    assert (
        'register_tool("_memory_context_for_request"'
        not in source
    )

    assert (
        "register_tool('_memory_context_for_request'"
        not in source
    )
