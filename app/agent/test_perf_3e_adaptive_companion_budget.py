from __future__ import annotations

import ast
from pathlib import Path

import app.agent.kuma_agent as kuma_agent_module
from app.agent.kuma_agent import KumaAgent


def _source():
    return Path(
        kuma_agent_module.__file__
    ).read_text()


def test_modifier_composition_direct_suffixes():
    cases = (
        (
            "give me lamb base soup",
            "for cold",
            "give me lamb base soup for cold",
        ),
        (
            "give me lamb base soup",
            "for fever",
            "give me lamb base soup for fever",
        ),
        (
            "make me a workout routine",
            "without squats",
            "make me a workout routine without squats",
        ),
        (
            "give me chicken soup",
            "with more protein",
            "give me chicken soup with more protein",
        ),
        (
            "write me a meal plan",
            "using eggs and chicken",
            "write me a meal plan using eggs and chicken",
        ),
    )

    for previous, current, expected in cases:
        assert (
            KumaAgent._resolve_companion_modifier_request(
                previous,
                current,
            )
            == expected
        )


def test_modifier_composition_instruction_suffixes():
    cases = (
        (
            "give me lamb base soup",
            "make it spicy",
            "give me lamb base soup. make it spicy",
        ),
        (
            "give me lamb base soup",
            "add ginger",
            "give me lamb base soup. add ginger",
        ),
        (
            "write me a message",
            "make it shorter",
            "write me a message. make it shorter",
        ),
    )

    for previous, current, expected in cases:
        assert (
            KumaAgent._resolve_companion_modifier_request(
                previous,
                current,
            )
            == expected
        )


def test_non_modifier_does_not_get_forced_into_previous_request():
    assert (
        KumaAgent._resolve_companion_modifier_request(
            "give me lamb base soup",
            "tell me a joke",
        )
        == ""
    )


def test_budget_contract_survives():
    assert (
        KumaAgent._companion_response_token_budget(
            "tell me a joke"
        )
        == 64
    )

    assert (
        KumaAgent._companion_response_token_budget(
            "I have a cold and feel tired today"
        )
        == 96
    )

    assert (
        KumaAgent._companion_response_token_budget(
            "What do you think I should focus on this week?"
        )
        == 128
    )

    assert (
        KumaAgent._companion_response_token_budget(
            "give me lamb base soup for cold"
        )
        == 256
    )

    assert (
        KumaAgent._companion_response_token_budget(
            "give me a detailed chicken soup recipe"
        )
        == 320
    )


def test_r5_runtime_contract_present():
    source = _source()

    assert (
        "KUMA PERF-3E R5 — DETERMINISTIC FOLLOW-UP COMPOSITION"
        in source
    )

    assert (
        "_resolve_companion_modifier_request("
        in source
    )

    assert (
        "companion_effective_request = current_request"
        in source
    )

    assert (
        "resolved_modifier_request ="
        in source
    )

    assert (
        "KUMA CONTINUITY → "
        in source
    )

    assert (
        "Resolved modifier follow-up:"
        in source
    )

    assert (
        '"content": companion_effective_request'
        in source
    )

    assert (
        "_last_companion_request = ("
        in source
    )

    # Verify the semantic assignment with AST instead of depending on
    # one-line source formatting:
    #
    #     companion_effective_request = (
    #         resolved_modifier_request
    #     )
    #
    tree = ast.parse(source)

    assignments = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue

        if len(node.targets) != 1:
            continue

        target = node.targets[0]

        if not (
            isinstance(target, ast.Name)
            and target.id == "companion_effective_request"
        ):
            continue

        if not (
            isinstance(node.value, ast.Name)
            and node.value.id == "resolved_modifier_request"
        ):
            continue

        assignments.append(node)

    assert len(assignments) == 1



def test_previous_perf_markers_survive():
    source = _source()

    for marker in (
        "KUMA PERF-3A — OLLAMA CONTEXT LOCK",
        "KUMA PERF-3A OLLAMA METRICS",
        "KUMA PERF-3B — COMPACT WEB SYNTHESIS",
        "KUMA PERF-3C — DEDICATED LOCAL SYNTHESIS MODEL",
        "KUMA PERF-3E — ADAPTIVE COMPANION RESPONSE BUDGET",
        "KUMA PERF-3E R3 — COMPLETION / CONTINUITY / ADVICE ROUTING",
        "KUMA PERF-3E R4 — COMPACT ADVICE + MODIFIER INHERITANCE",
    ):
        assert marker in source


def test_personal_advice_compact_path_survives():
    source = _source()

    for token in (
        "KUMA PERF-3E R4 COMPACT PERSONAL-ADVICE PATH",
        "personal_advice_compact_path = True",
        "KUMA ADVICE FAST PATH",
        "2 model messages, 0 tools.",
    ):
        assert token in source
