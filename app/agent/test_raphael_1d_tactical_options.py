from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError
import inspect

import pytest

from app.agent.capability_registry import (
    Capability,
    CapabilityRegistry,
)
from app.agent.cognitive_contracts import (
    TacticalRisk,
    TacticalSituation,
    WorldStateSnapshot,
)
from app.agent.permissions import (
    PermissionLevel,
)
from app.agent.tactical_options import (
    ConfidenceBand,
    CostBand,
    OptionKind,
    OutcomeSimulation,
    TacticalOptionGenerator,
    TacticalOptionSeed,
)


STAMP = "2026-09-12T17:00:00+05:30"


def world():
    return WorldStateSnapshot(
        timestamp=STAMP,
        task_goal="Recover the editor safely.",
    )


def situation(
    *,
    uncertainties=(
        "Root cause is not verified.",
    ),
    capabilities=(
        "system_inspection",
        "application_control",
        "command_execution",
        "sensitive_observation",
    ),
):
    return TacticalSituation(
        goal="Recover the editor safely.",
        observed_state=(
            "desktop_evidence: Error dialog visible.",
        ),
        known_facts=(
            "Task evidence: Editor responsive.",
        ),
        uncertainties=uncertainties,
        constraints=(
            "Do not modify user files without authority.",
        ),
        available_capabilities=capabilities,
        world_state=world(),
    )


def registry():
    return CapabilityRegistry(
        [
            Capability(
                name="system_inspection",
                description="Inspect system state.",
                tools=(
                    "inspect_system",
                ),
                risk_level="normal",
            ),
            Capability(
                name="application_control",
                description="Launch applications.",
                tools=(
                    "open_app",
                ),
                risk_level="normal",
            ),
            Capability(
                name="command_execution",
                description="Run commands.",
                tools=(
                    "execute_command",
                ),
                risk_level="high",
            ),
            Capability(
                name="sensitive_observation",
                description="Read sensitive state.",
                tools=(
                    "get_current_location",
                ),
                risk_level="sensitive",
            ),
        ]
    )


def observe_seed(**overrides):
    values = dict(
        option_id="observe-system",
        kind=OptionKind.OBSERVE,
        objective="Inspect current system state.",
        rationale="More evidence may reduce uncertainty.",
        expected_outcome=(
            "Additional current system evidence becomes available."
        ),
        confidence_band=ConfidenceBand.HIGH,
        reversible=True,
        tool_name="inspect_system",
        capability="system_inspection",
        cost_band=CostBand.LOW,
        verification_requirements=(
            "Verify that fresh system evidence was returned.",
        ),
    )

    values.update(
        overrides
    )

    return TacticalOptionSeed(
        **values
    )


def act_seed(**overrides):
    values = dict(
        option_id="open-editor",
        kind=OptionKind.ACT,
        objective="Open the editor.",
        rationale="The requested application may need to be foregrounded.",
        expected_outcome="The editor may become available.",
        confidence_band=ConfidenceBand.MEDIUM,
        reversible=True,
        tool_name="open_app",
        capability="application_control",
        cost_band=CostBand.MEDIUM,
        failure_modes=(
            "The application may fail to open.",
        ),
        verification_requirements=(
            "Verify the foreground application identity.",
        ),
    )

    values.update(
        overrides
    )

    return TacticalOptionSeed(
        **values
    )


def dangerous_seed(**overrides):
    values = dict(
        option_id="dangerous-command",
        kind=OptionKind.ACT,
        objective="Run an explicitly proposed command.",
        rationale="A command was proposed as one candidate approach.",
        expected_outcome="The proposed command may change system state.",
        confidence_band=ConfidenceBand.LOW,
        reversible=False,
        tool_name="execute_command",
        capability="command_execution",
        cost_band=CostBand.HIGH,
        failure_modes=(
            "The command may fail or change unintended state.",
        ),
        recovery_notes=(
            "Recovery must be handled by an existing verified rollback path.",
        ),
        verification_requirements=(
            "Verify resulting state independently.",
        ),
    )

    values.update(
        overrides
    )

    return TacticalOptionSeed(
        **values
    )


def defer_seed(**overrides):
    values = dict(
        option_id="defer",
        kind=OptionKind.DEFER,
        objective="Defer external action.",
        rationale="Material uncertainty remains.",
        expected_outcome="No external action is proposed by this option.",
        confidence_band=ConfidenceBand.HIGH,
        reversible=True,
        cost_band=CostBand.MINIMAL,
    )

    values.update(
        overrides
    )

    return TacticalOptionSeed(
        **values
    )


def generator():
    return TacticalOptionGenerator(
        capability_registry=registry()
    )


def test_seed_is_zero_authority():
    seed = observe_seed()

    assert seed.authority == "NONE"


def test_seed_is_frozen():
    seed = observe_seed()

    with pytest.raises(
        FrozenInstanceError
    ):
        seed.objective = "changed"


def test_seed_flattens_text_fields():
    seed = observe_seed(
        objective="Inspect\nsystem\tstate.",
        assumptions=(
            "Provider\nreturns fresh data.",
        ),
    )

    assert seed.objective == (
        "Inspect system state."
    )

    assert seed.assumptions == (
        "Provider returns fresh data.",
    )


def test_seed_rejects_non_enum_kind():
    with pytest.raises(
        TypeError,
        match="OptionKind",
    ):
        observe_seed(
            kind="observe"
        )


def test_defer_seed_cannot_name_tool_or_capability():
    with pytest.raises(
        ValueError,
        match="cannot name",
    ):
        defer_seed(
            tool_name="inspect_system"
        )


def test_defer_seed_must_be_reversible():
    with pytest.raises(
        ValueError,
        match="must be reversible",
    ):
        defer_seed(
            reversible=False
        )


def test_action_seed_requires_tool_and_capability():
    with pytest.raises(
        ValueError,
        match="require both",
    ):
        observe_seed(
            tool_name=None
        )


def test_action_seed_requires_verification_requirement():
    with pytest.raises(
        ValueError,
        match="verification",
    ):
        observe_seed(
            verification_requirements=()
        )


@pytest.mark.parametrize(
    "kind",
    (
        OptionKind.ACT,
        OptionKind.RECOVER,
    ),
)
def test_act_and_recover_require_explicit_failure_mode(kind):
    with pytest.raises(
        ValueError,
        match="failure mode",
    ):
        act_seed(
            kind=kind,
            failure_modes=(),
        )


def test_irreversible_seed_requires_recovery_note():
    with pytest.raises(
        ValueError,
        match="recovery",
    ):
        dangerous_seed(
            recovery_notes=()
        )


def test_safe_observation_uses_canonical_safe_permission():
    result = generator().generate(
        situation(),
        (
            observe_seed(),
        ),
        available_tool_names=(
            "inspect_system",
        ),
    )[
        0
    ]

    assert (
        result.option.required_permission
        == PermissionLevel.SAFE
    )

    assert (
        result.option.risk
        == TacticalRisk.LOW
    )


def test_user_authorized_action_keeps_user_authorized_classification():
    result = generator().generate(
        situation(),
        (
            act_seed(),
        ),
        available_tool_names=(
            "open_app",
        ),
    )[
        0
    ]

    assert (
        result.option.required_permission
        == PermissionLevel.USER_AUTHORIZED
    )

    assert (
        result.option.risk
        == TacticalRisk.MODERATE
    )


def test_dangerous_action_is_critical_and_never_downgraded():
    result = generator().generate(
        situation(),
        (
            dangerous_seed(),
        ),
        available_tool_names=(
            "execute_command",
        ),
    )[
        0
    ]

    assert (
        result.option.required_permission
        == PermissionLevel.DANGEROUS
    )

    assert (
        result.option.risk
        == TacticalRisk.CRITICAL
    )

    assert (
        result.option.reversible
        is False
    )


def test_sensitive_capability_escalates_risk():
    seed = observe_seed(
        option_id="observe-location",
        tool_name="get_current_location",
        capability="sensitive_observation",
    )

    result = generator().generate(
        situation(),
        (
            seed,
        ),
        available_tool_names=(
            "get_current_location",
        ),
    )[
        0
    ]

    assert (
        result.option.required_permission
        == PermissionLevel.USER_AUTHORIZED
    )

    assert (
        result.option.risk
        == TacticalRisk.HIGH
    )


def test_irreversibility_sets_high_risk_floor():
    seed = act_seed(
        reversible=False,
        recovery_notes=(
            "Contain the changed state if verification fails.",
        ),
    )

    result = generator().generate(
        situation(),
        (
            seed,
        ),
        available_tool_names=(
            "open_app",
        ),
    )[
        0
    ]

    assert (
        result.option.risk
        == TacticalRisk.HIGH
    )


def test_unknown_capability_risk_metadata_fails_closed():
    broken = CapabilityRegistry(
        [
            Capability(
                name="future",
                description="Future capability.",
                tools=(
                    "inspect_system",
                ),
                risk_level="mystery",
            )
        ]
    )

    item = situation(
        capabilities=(
            "future",
        )
    )

    seed = observe_seed(
        capability="future"
    )

    with pytest.raises(
        ValueError,
        match="risk metadata",
    ):
        TacticalOptionGenerator(
            capability_registry=broken
        ).generate(
            item,
            (
                seed,
            ),
            available_tool_names=(
                "inspect_system",
            ),
        )


def test_tool_must_be_in_current_runtime_tool_set():
    with pytest.raises(
        ValueError,
        match="current runtime tool set",
    ):
        generator().generate(
            situation(),
            (
                observe_seed(),
            ),
            available_tool_names=(),
        )


def test_capability_must_be_currently_available():
    item = situation(
        capabilities=(
            "application_control",
        )
    )

    with pytest.raises(
        ValueError,
        match="TacticalSituation",
    ):
        generator().generate(
            item,
            (
                observe_seed(),
            ),
            available_tool_names=(
                "inspect_system",
            ),
        )


def test_tool_capability_ownership_mismatch_fails_closed():
    seed = observe_seed(
        capability="application_control"
    )

    with pytest.raises(
        ValueError,
        match="ownership",
    ):
        generator().generate(
            situation(),
            (
                seed,
            ),
            available_tool_names=(
                "inspect_system",
            ),
        )


def test_ambiguous_tool_ownership_fails_closed():
    ambiguous = CapabilityRegistry(
        [
            Capability(
                name="one",
                description="One.",
                tools=(
                    "inspect_system",
                ),
            ),
            Capability(
                name="two",
                description="Two.",
                tools=(
                    "inspect_system",
                ),
            ),
        ]
    )

    item = situation(
        capabilities=(
            "one",
            "two",
        )
    )

    seed = observe_seed(
        capability="one"
    )

    with pytest.raises(
        ValueError,
        match="ambiguous",
    ):
        TacticalOptionGenerator(
            capability_registry=ambiguous
        ).generate(
            item,
            (
                seed,
            ),
            available_tool_names=(
                "inspect_system",
            ),
        )


def test_unknown_tool_has_no_legacy_permission_fallback():
    custom = CapabilityRegistry(
        [
            Capability(
                name="future",
                description="Future.",
                tools=(
                    "future_tool",
                ),
            )
        ]
    )

    item = situation(
        capabilities=(
            "future",
        )
    )

    seed = observe_seed(
        tool_name="future_tool",
        capability="future",
    )

    with pytest.raises(
        ValueError,
        match="permission metadata",
    ):
        TacticalOptionGenerator(
            capability_registry=custom
        ).generate(
            item,
            (
                seed,
            ),
            available_tool_names=(
                "future_tool",
            ),
        )


def test_duplicate_option_ids_are_rejected():
    with pytest.raises(
        ValueError,
        match="unique",
    ):
        generator().generate(
            situation(),
            (
                observe_seed(),
                observe_seed(),
            ),
            available_tool_names=(
                "inspect_system",
            ),
        )


def test_multiple_options_preserve_seed_order_without_ranking():
    results = generator().generate(
        situation(),
        (
            act_seed(),
            observe_seed(),
            defer_seed(),
        ),
        available_tool_names=(
            "open_app",
            "inspect_system",
        ),
    )

    assert tuple(
        item.option.option_id
        for item
        in results
    ) == (
        "open-editor",
        "observe-system",
        "defer",
    )


@pytest.mark.parametrize(
    (
        "band",
        "score",
    ),
    (
        (
            ConfidenceBand.LOW,
            0.25,
        ),
        (
            ConfidenceBand.MEDIUM,
            0.50,
        ),
        (
            ConfidenceBand.HIGH,
            0.75,
        ),
    ),
)
def test_confidence_uses_only_coarse_canonical_scores(band, score):
    seed = observe_seed(
        confidence_band=band
    )

    result = generator().generate(
        situation(),
        (
            seed,
        ),
        available_tool_names=(
            "inspect_system",
        ),
    )[
        0
    ]

    assert (
        result.option.confidence
        == score
    )

    assert (
        result.simulation.confidence_score
        == score
    )


@pytest.mark.parametrize(
    (
        "band",
        "score",
    ),
    (
        (
            CostBand.MINIMAL,
            0.10,
        ),
        (
            CostBand.LOW,
            0.25,
        ),
        (
            CostBand.MEDIUM,
            0.50,
        ),
        (
            CostBand.HIGH,
            0.75,
        ),
    ),
)
def test_cost_uses_only_coarse_canonical_scores(band, score):
    seed = observe_seed(
        cost_band=band
    )

    result = generator().generate(
        situation(),
        (
            seed,
        ),
        available_tool_names=(
            "inspect_system",
        ),
    )[
        0
    ]

    assert (
        result.option.cost
        == score
    )


def test_defer_option_has_no_tool_or_capability_and_zero_cost():
    result = generator().generate(
        situation(),
        (
            defer_seed(),
        ),
    )[
        0
    ]

    assert result.tool_name is None
    assert result.option.capability is None

    assert (
        result.option.required_permission
        == PermissionLevel.SAFE
    )

    assert (
        result.option.risk
        == TacticalRisk.LOW
    )

    assert result.option.cost == 0.0


def test_simulation_carries_remaining_uncertainty_without_resolving_it():
    item = situation(
        uncertainties=(
            "Cause unknown.",
            "Target state unverified.",
        )
    )

    result = generator().generate(
        item,
        (
            observe_seed(),
        ),
        available_tool_names=(
            "inspect_system",
        ),
    )[
        0
    ]

    assert (
        result.simulation.remaining_uncertainties
        == item.uncertainties
    )

    assert (
        result.simulation.outcome_verified
        is False
    )

    assert (
        result.simulation.prediction_only
        is True
    )


def test_simulation_preserves_explicit_supporting_envelope():
    seed = act_seed(
        assumptions=(
            "Application identity is current.",
        ),
        failure_modes=(
            "Launch may fail.",
        ),
        recovery_notes=(
            "Return to the prior foreground application if needed.",
        ),
        verification_requirements=(
            "Verify the foreground application identity.",
        ),
    )

    result = generator().generate(
        situation(),
        (
            seed,
        ),
        available_tool_names=(
            "open_app",
        ),
    )[
        0
    ]

    simulation = result.simulation

    assert simulation.assumptions == (
        "Application identity is current.",
    )

    assert simulation.failure_modes == (
        "Launch may fail.",
    )

    assert simulation.recovery_notes == (
        "Return to the prior foreground application if needed.",
    )

    assert simulation.verification_requirements == (
        "Verify the foreground application identity.",
    )


def test_predicted_outcome_is_not_promoted_to_known_fact():
    predicted = (
        "Editor definitely opens and task is complete."
    )

    result = generator().generate(
        situation(),
        (
            act_seed(
                expected_outcome=predicted
            ),
        ),
        available_tool_names=(
            "open_app",
        ),
    )[
        0
    ]

    assert (
        result.simulation.predicted_outcome
        == predicted
    )

    assert (
        predicted
        not in situation().known_facts
    )

    assert (
        result.simulation.outcome_verified
        is False
    )


def test_no_tool_arguments_exist_on_seed_or_result():
    seed = act_seed()

    result = generator().generate(
        situation(),
        (
            seed,
        ),
        available_tool_names=(
            "open_app",
        ),
    )[
        0
    ]

    assert not hasattr(
        seed,
        "arguments",
    )

    assert not hasattr(
        result,
        "arguments",
    )

    assert not hasattr(
        result.option,
        "arguments",
    )


def test_generation_does_not_mutate_situation_or_registry():
    item = situation()
    reg = registry()

    item_before = deepcopy(
        item
    )

    names_before = reg.names()

    TacticalOptionGenerator(
        capability_registry=reg
    ).generate(
        item,
        (
            observe_seed(),
        ),
        available_tool_names=(
            "inspect_system",
        ),
    )

    assert item == item_before
    assert reg.names() == names_before


def test_every_generated_layer_remains_zero_authority():
    result = generator().generate(
        situation(),
        (
            dangerous_seed(),
        ),
        available_tool_names=(
            "execute_command",
        ),
    )[
        0
    ]

    assert result.authority == "NONE"
    assert result.option.authority == "NONE"
    assert result.simulation.authority == "NONE"


def test_dangerous_option_does_not_contain_approval_state():
    result = generator().generate(
        situation(),
        (
            dangerous_seed(),
        ),
        available_tool_names=(
            "execute_command",
        ),
    )[
        0
    ]

    for value in (
        result,
        result.option,
        result.simulation,
    ):
        for field_name in (
            "approved",
            "confirmed",
            "permission_granted",
            "authorized",
            "execute",
        ):
            assert not hasattr(
                value,
                field_name,
            )


def test_module_has_no_execution_or_confirmation_surface():
    import app.agent.tactical_options as module

    source = inspect.getsource(
        module
    )

    forbidden = (
        "ActionExecutor",
        "KumaAgent",
        "register_tool(",
        ".execute(",
        "request_confirmation(",
        "confirm_dangerous_action(",
        "explicitly_requests_dangerous_action(",
    )

    for marker in forbidden:
        assert marker not in source


def test_module_has_no_provider_sensor_memory_or_model_surface():
    import app.agent.tactical_options as module

    source = inspect.getsource(
        module
    )

    forbidden = (
        "app.memory.manager",
        "get_memory_context",
        "retrieve_memories",
        "app.realtime.runtime",
        "refresh_weather(",
        "get_current_location(",
        "web_search(",
        "fetch_webpage(",
        "pyautogui",
        "requests",
        "urllib",
        "ask_model(",
        "generate_content(",
    )

    for marker in forbidden:
        assert marker not in source


def test_module_uses_strict_permission_metadata_not_legacy_fallback():
    import app.agent.tactical_options as module

    source = inspect.getsource(
        module
    )

    assert (
        "require_explicit_permission"
        in source
    )

    assert (
        "get_permission_level"
        not in source
    )


def test_module_does_not_generate_decisions_or_choose_winner():
    import app.agent.tactical_options as module

    source = inspect.getsource(
        module
    )

    forbidden = (
        "TacticalDecision(",
        "chosen_option=",
        "rejected_options=",
        "best_option",
        "winner",
        "rank_options",
    )

    for marker in forbidden:
        assert marker not in source



def test_more_than_bounded_seed_count_is_rejected():
    seeds = tuple(
        defer_seed(
            option_id=f"defer-{index}"
        )
        for index in range(
            13
        )
    )

    with pytest.raises(
        ValueError,
        match="At most",
    ):
        generator().generate(
            situation(),
            seeds,
        )


def test_available_runtime_tool_set_is_not_truncated_to_option_limit():
    available = tuple(
        f"unused-tool-{index}"
        for index in range(
            20
        )
    ) + (
        "inspect_system",
    )

    result = generator().generate(
        situation(),
        (
            observe_seed(),
        ),
        available_tool_names=available,
    )

    assert (
        result[
            0
        ].tool_name
        == "inspect_system"
    )

def test_empty_seed_set_returns_no_options():
    assert (
        generator().generate(
            situation(),
            (),
        )
        == ()
    )
