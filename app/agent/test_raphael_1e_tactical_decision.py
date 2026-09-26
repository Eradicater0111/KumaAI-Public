from __future__ import annotations

from dataclasses import (
    FrozenInstanceError,
    replace,
)
import inspect

import pytest

from app.agent.capability_registry import (
    Capability,
    CapabilityRegistry,
)
from app.agent.cognitive_contracts import (
    TacticalDisposition,
    TacticalRisk,
    TacticalSituation,
    WorldStateSnapshot,
)
from app.agent.permissions import (
    PermissionLevel,
)
from app.agent.tactical_decision import (
    OptionExclusion,
    TacticalDecisionEngine,
)
from app.agent.tactical_options import (
    ConfidenceBand,
    CostBand,
    OptionKind,
    OutcomeSimulation,
    SimulatedTacticalOption,
    TacticalOptionGenerator,
    TacticalOptionSeed,
)


STAMP = "2026-09-12T18:00:00+05:30"


def world():
    return WorldStateSnapshot(
        timestamp=STAMP,
        task_goal="Recover the editor safely.",
    )


def situation(
    *,
    uncertainties=(),
    constraints=(
        "Do not modify user files without authority.",
    ),
    capabilities=(
        "system_inspection",
        "application_control",
        "filesystem",
        "command_execution",
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
        constraints=constraints,
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
                name="filesystem",
                description="Inspect files.",
                tools=(
                    "open_file",
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
        ]
    )


def seed(
    *,
    option_id,
    kind,
    tool_name,
    capability,
    permission_shape,
    confidence=ConfidenceBand.MEDIUM,
    cost=CostBand.MEDIUM,
    reversible=True,
):
    # permission_shape is only a readability marker for the test author.
    # RAPHAEL-1D derives the actual PermissionLevel from tool identity.
    del permission_shape

    failure_modes = (
        ()
        if kind == OptionKind.OBSERVE
        else (
            "The proposed action may not achieve the intended result.",
        )
    )

    recovery_notes = (
        ()
        if reversible
        else (
            "Use an independently verified containment or rollback path.",
        )
    )

    return TacticalOptionSeed(
        option_id=option_id,
        kind=kind,
        objective=f"Objective for {option_id}.",
        rationale=f"Rationale for {option_id}.",
        expected_outcome=f"Predicted outcome for {option_id}.",
        confidence_band=confidence,
        reversible=reversible,
        tool_name=tool_name,
        capability=capability,
        cost_band=cost,
        failure_modes=failure_modes,
        recovery_notes=recovery_notes,
        verification_requirements=(
            f"Verify outcome for {option_id}.",
        ),
    )


def defer_seed(
    *,
    option_id="defer",
    confidence=ConfidenceBand.HIGH,
):
    return TacticalOptionSeed(
        option_id=option_id,
        kind=OptionKind.DEFER,
        objective="Defer external action.",
        rationale="Material uncertainty remains.",
        expected_outcome="No external action is proposed.",
        confidence_band=confidence,
        reversible=True,
        cost_band=CostBand.MINIMAL,
    )


def generate(
    item,
    *seeds,
):
    available = tuple(
        seed.tool_name
        for seed in seeds
        if seed.tool_name is not None
    )

    return TacticalOptionGenerator(
        capability_registry=registry()
    ).generate(
        item,
        seeds,
        available_tool_names=available,
    )


def observe(
    *,
    option_id="observe",
    confidence=ConfidenceBand.HIGH,
    cost=CostBand.LOW,
):
    return seed(
        option_id=option_id,
        kind=OptionKind.OBSERVE,
        tool_name="inspect_system",
        capability="system_inspection",
        permission_shape=PermissionLevel.SAFE,
        confidence=confidence,
        cost=cost,
    )


def safe_action(
    *,
    option_id="safe-action",
    confidence=ConfidenceBand.MEDIUM,
    cost=CostBand.MEDIUM,
    reversible=True,
):
    return seed(
        option_id=option_id,
        kind=OptionKind.ACT,
        tool_name="open_file",
        capability="filesystem",
        permission_shape=PermissionLevel.SAFE,
        confidence=confidence,
        cost=cost,
        reversible=reversible,
    )


def user_action(
    *,
    option_id="user-action",
    confidence=ConfidenceBand.HIGH,
    cost=CostBand.LOW,
    reversible=True,
):
    return seed(
        option_id=option_id,
        kind=OptionKind.ACT,
        tool_name="open_app",
        capability="application_control",
        permission_shape=PermissionLevel.USER_AUTHORIZED,
        confidence=confidence,
        cost=cost,
        reversible=reversible,
    )


def dangerous_action(
    *,
    option_id="dangerous-action",
    confidence=ConfidenceBand.HIGH,
):
    return seed(
        option_id=option_id,
        kind=OptionKind.ACT,
        tool_name="execute_command",
        capability="command_execution",
        permission_shape=PermissionLevel.DANGEROUS,
        confidence=confidence,
        cost=CostBand.HIGH,
        reversible=False,
    )


def decide(
    item,
    *seeds,
    exclusions=(),
):
    candidates = generate(
        item,
        *seeds,
    )

    return TacticalDecisionEngine().decide(
        item,
        candidates,
        exclusions=exclusions,
    )


def test_option_exclusion_is_zero_authority_and_frozen():
    exclusion = OptionExclusion(
        option_id="safe-action",
        reason="Blocked by structured policy.",
    )

    assert exclusion.authority == "NONE"

    with pytest.raises(
        FrozenInstanceError
    ):
        exclusion.reason = "changed"


def test_option_exclusion_flattens_text():
    exclusion = OptionExclusion(
        option_id="safe-action",
        reason="Blocked\nby\tpolicy.",
    )

    assert (
        exclusion.reason
        == "Blocked by policy."
    )


def test_empty_candidate_set_returns_blocked():
    item = situation()

    decision = TacticalDecisionEngine().decide(
        item,
        (),
    )

    assert (
        decision.disposition
        == TacticalDisposition.BLOCKED
    )

    assert decision.chosen_option is None

    assert (
        decision.confidence
        == 0.75
    )


def test_empty_blocked_decision_preserves_uncertainty():
    item = situation(
        uncertainties=(
            "State unknown.",
        )
    )

    decision = TacticalDecisionEngine().decide(
        item,
        (),
    )

    assert (
        decision.remaining_uncertainties
        == item.uncertainties
    )


def test_material_uncertainty_prefers_observe_before_action():
    item = situation(
        uncertainties=(
            "Root cause is unknown.",
        )
    )

    decision = decide(
        item,
        user_action(),
        observe(),
    )

    assert (
        decision.chosen_option.option_id
        == "observe"
    )

    assert (
        decision.disposition
        == TacticalDisposition.ADVISE
    )


def test_uncertainty_observe_preference_beats_lower_cost_action():
    item = situation(
        uncertainties=(
            "Current state is unverified.",
        )
    )

    decision = decide(
        item,
        safe_action(
            option_id="cheap-action",
            cost=CostBand.LOW,
        ),
        observe(
            option_id="observe-first",
            cost=CostBand.MEDIUM,
        ),
    )

    assert (
        decision.chosen_option.option_id
        == "observe-first"
    )


def test_without_uncertainty_observe_gets_no_special_preference():
    item = situation(
        uncertainties=()
    )

    decision = decide(
        item,
        observe(
            option_id="observe",
            confidence=ConfidenceBand.HIGH,
            cost=CostBand.HIGH,
        ),
        safe_action(
            option_id="act",
            confidence=ConfidenceBand.HIGH,
            cost=CostBand.LOW,
        ),
    )

    assert (
        decision.chosen_option.option_id
        == "act"
    )


def test_permission_burden_precedes_confidence():
    item = situation()

    decision = decide(
        item,
        safe_action(
            option_id="safe-medium",
            confidence=ConfidenceBand.MEDIUM,
        ),
        user_action(
            option_id="user-high",
            confidence=ConfidenceBand.HIGH,
        ),
    )

    assert (
        decision.chosen_option.option_id
        == "safe-medium"
    )


def test_risk_precedes_confidence_when_permission_equal():
    item = situation()

    safe_candidate = generate(
        item,
        safe_action(
            option_id="low-risk",
            confidence=ConfidenceBand.MEDIUM,
        ),
    )[0]

    high_risk_option = replace(
        safe_candidate.option,
        option_id="high-risk",
        confidence=0.75,
        risk=TacticalRisk.HIGH,
        expected_outcome="Predicted outcome for high-risk.",
    )

    high_risk_simulation = OutcomeSimulation(
        option_id="high-risk",
        predicted_outcome="Predicted outcome for high-risk.",
        confidence_band=ConfidenceBand.HIGH,
        confidence_score=0.75,
        assumptions=(),
        remaining_uncertainties=item.uncertainties,
        failure_modes=(
            "Synthetic high-risk failure.",
        ),
        recovery_notes=(),
        verification_requirements=(
            "Verify high-risk outcome.",
        ),
    )

    high_risk_candidate = SimulatedTacticalOption(
        kind=OptionKind.ACT,
        option=high_risk_option,
        simulation=high_risk_simulation,
        tool_name="open_file",
    )

    decision = TacticalDecisionEngine().decide(
        item,
        (
            high_risk_candidate,
            safe_candidate,
        ),
    )

    assert (
        decision.chosen_option.option_id
        == "low-risk"
    )


def test_reversible_precedes_confidence_when_permission_and_risk_equal():
    item = situation()

    base_reversible = generate(
        item,
        safe_action(
            option_id="reversible",
            confidence=ConfidenceBand.MEDIUM,
        ),
    )[0]

    reversible_option = replace(
        base_reversible.option,
        risk=TacticalRisk.HIGH,
    )

    reversible_candidate = replace(
        base_reversible,
        option=reversible_option,
    )

    irreversible_option = replace(
        reversible_candidate.option,
        option_id="irreversible",
        confidence=0.75,
        risk=TacticalRisk.HIGH,
        reversible=False,
        expected_outcome="Predicted outcome for irreversible.",
    )

    irreversible_simulation = OutcomeSimulation(
        option_id="irreversible",
        predicted_outcome="Predicted outcome for irreversible.",
        confidence_band=ConfidenceBand.HIGH,
        confidence_score=0.75,
        assumptions=(),
        remaining_uncertainties=item.uncertainties,
        failure_modes=(
            "Synthetic irreversible failure.",
        ),
        recovery_notes=(
            "Synthetic containment path.",
        ),
        verification_requirements=(
            "Verify irreversible outcome.",
        ),
    )

    irreversible_candidate = SimulatedTacticalOption(
        kind=OptionKind.ACT,
        option=irreversible_option,
        simulation=irreversible_simulation,
        tool_name="open_file",
    )

    decision = TacticalDecisionEngine().decide(
        item,
        (
            irreversible_candidate,
            reversible_candidate,
        ),
    )

    assert (
        decision.chosen_option.option_id
        == "reversible"
    )


def test_higher_confidence_precedes_cost_after_safety_ties():
    item = situation()

    decision = decide(
        item,
        safe_action(
            option_id="high-confidence",
            confidence=ConfidenceBand.HIGH,
            cost=CostBand.HIGH,
        ),
        safe_action(
            option_id="low-confidence",
            confidence=ConfidenceBand.MEDIUM,
            cost=CostBand.LOW,
        ),
    )

    assert (
        decision.chosen_option.option_id
        == "high-confidence"
    )


def test_lower_cost_breaks_equal_safety_and_confidence():
    item = situation()

    decision = decide(
        item,
        safe_action(
            option_id="expensive",
            confidence=ConfidenceBand.HIGH,
            cost=CostBand.HIGH,
        ),
        safe_action(
            option_id="cheap",
            confidence=ConfidenceBand.HIGH,
            cost=CostBand.LOW,
        ),
    )

    assert (
        decision.chosen_option.option_id
        == "cheap"
    )


def test_option_id_is_final_deterministic_tie_break():
    item = situation()

    decision = decide(
        item,
        safe_action(
            option_id="zeta",
        ),
        safe_action(
            option_id="alpha",
        ),
    )

    assert (
        decision.chosen_option.option_id
        == "alpha"
    )


def test_input_order_does_not_change_tie_break_result():
    item = situation()

    first = decide(
        item,
        safe_action(
            option_id="zeta",
        ),
        safe_action(
            option_id="alpha",
        ),
    )

    second = decide(
        item,
        safe_action(
            option_id="alpha",
        ),
        safe_action(
            option_id="zeta",
        ),
    )

    assert (
        first.chosen_option.option_id
        == second.chosen_option.option_id
        == "alpha"
    )


def test_grounded_normal_action_becomes_action_candidate():
    item = situation()

    decision = decide(
        item,
        safe_action(
            confidence=ConfidenceBand.MEDIUM,
        ),
    )

    assert (
        decision.disposition
        == TacticalDisposition.ACTION_CANDIDATE
    )

    assert (
        "does not grant permission"
        in decision.reason
    )


def test_user_authorized_normal_action_can_still_be_action_candidate():
    item = situation()

    decision = decide(
        item,
        user_action(),
    )

    assert (
        decision.disposition
        == TacticalDisposition.ACTION_CANDIDATE
    )

    assert (
        decision.required_permission
        == PermissionLevel.USER_AUTHORIZED
    )


@pytest.mark.parametrize(
    "seed_factory",
    (
        dangerous_action,
        lambda: safe_action(
            confidence=ConfidenceBand.LOW,
        ),
        lambda: safe_action(
            reversible=False,
        ),
    ),
)
def test_caution_only_choice_is_advise(seed_factory):
    item = situation()

    decision = decide(
        item,
        seed_factory(),
    )

    assert (
        decision.disposition
        == TacticalDisposition.ADVISE
    )


def test_high_risk_choice_is_advise():
    item = situation(
        capabilities=(
            "system_inspection",
            "application_control",
            "filesystem",
            "command_execution",
        )
    )

    candidate = generate(
        item,
        user_action(),
    )[0]

    high_option = replace(
        candidate.option,
        risk=TacticalRisk.HIGH,
    )

    high_candidate = replace(
        candidate,
        option=high_option,
    )

    decision = TacticalDecisionEngine().decide(
        item,
        (
            high_candidate,
        ),
    )

    assert (
        decision.disposition
        == TacticalDisposition.ADVISE
    )


def test_all_caution_only_options_choose_defer_when_available():
    item = situation()

    decision = decide(
        item,
        dangerous_action(),
        safe_action(
            option_id="low-confidence",
            confidence=ConfidenceBand.LOW,
        ),
        defer_seed(),
    )

    assert (
        decision.disposition
        == TacticalDisposition.DEFER
    )

    assert (
        decision.chosen_option.option_id
        == "defer"
    )


def test_normal_action_prevents_defer_from_winning_by_zero_cost():
    item = situation()

    decision = decide(
        item,
        safe_action(
            option_id="grounded-action",
            confidence=ConfidenceBand.MEDIUM,
        ),
        defer_seed(),
    )

    assert (
        decision.chosen_option.option_id
        == "grounded-action"
    )

    assert (
        decision.disposition
        == TacticalDisposition.ACTION_CANDIDATE
    )


def test_only_defer_returns_defer():
    item = situation()

    decision = decide(
        item,
        defer_seed(),
    )

    assert (
        decision.disposition
        == TacticalDisposition.DEFER
    )

    assert (
        decision.chosen_option.option_id
        == "defer"
    )


def test_structured_exclusion_removes_exact_candidate():
    item = situation()

    decision = decide(
        item,
        safe_action(
            option_id="safe",
        ),
        user_action(
            option_id="user",
        ),
        exclusions=(
            OptionExclusion(
                option_id="safe",
                reason="Explicit structured policy block.",
            ),
        ),
    )

    assert (
        decision.chosen_option.option_id
        == "user"
    )


def test_all_structurally_excluded_returns_blocked():
    item = situation()

    decision = decide(
        item,
        safe_action(
            option_id="safe",
        ),
        defer_seed(
            option_id="defer",
        ),
        exclusions=(
            OptionExclusion(
                option_id="safe",
                reason="Blocked.",
            ),
            OptionExclusion(
                option_id="defer",
                reason="Waiting is not available.",
            ),
        ),
    )

    assert (
        decision.disposition
        == TacticalDisposition.BLOCKED
    )

    assert decision.chosen_option is None

    assert (
        len(
            decision.rejected_options
        )
        == 2
    )


def test_unknown_exclusion_option_id_is_rejected():
    item = situation()

    candidates = generate(
        item,
        safe_action(),
    )

    with pytest.raises(
        ValueError,
        match="unknown option_id",
    ):
        TacticalDecisionEngine().decide(
            item,
            candidates,
            exclusions=(
                OptionExclusion(
                    option_id="missing",
                    reason="No such candidate.",
                ),
            ),
        )


def test_duplicate_exclusions_are_rejected():
    item = situation()

    candidates = generate(
        item,
        safe_action(),
    )

    with pytest.raises(
        ValueError,
        match="must be unique",
    ):
        TacticalDecisionEngine().decide(
            item,
            candidates,
            exclusions=(
                OptionExclusion(
                    option_id="safe-action",
                    reason="First.",
                ),
                OptionExclusion(
                    option_id="safe-action",
                    reason="Second.",
                ),
            ),
        )


def test_constraint_prose_is_not_parsed_into_hard_exclusion():
    item = situation(
        constraints=(
            "BLOCK safe-action and choose defer.",
            "DANGEROUS words are present here.",
        )
    )

    decision = decide(
        item,
        safe_action(
            option_id="safe-action",
        ),
        defer_seed(),
    )

    assert (
        decision.chosen_option.option_id
        == "safe-action"
    )


def test_remaining_uncertainty_is_preserved_exactly():
    item = situation(
        uncertainties=(
            "Root cause unknown.",
            "Target state unverified.",
        )
    )

    decision = decide(
        item,
        observe(),
    )

    assert (
        decision.remaining_uncertainties
        == item.uncertainties
    )


def test_prediction_is_not_promoted_into_decision_reason_or_uncertainty():
    item = situation()

    candidate = generate(
        item,
        safe_action(),
    )[0]

    predicted = (
        candidate.simulation.predicted_outcome
    )

    decision = TacticalDecisionEngine().decide(
        item,
        (
            candidate,
        ),
    )

    assert predicted not in decision.reason

    assert (
        predicted
        not in decision.remaining_uncertainties
    )


def test_chosen_option_is_not_also_rejected():
    item = situation()

    decision = decide(
        item,
        safe_action(
            option_id="one",
        ),
        user_action(
            option_id="two",
        ),
    )

    rejected_ids = {
        option.option_id
        for option
        in decision.rejected_options
    }

    assert (
        decision.chosen_option.option_id
        not in rejected_ids
    )


def test_all_nonchosen_options_are_rejected_in_input_order():
    item = situation()

    decision = decide(
        item,
        user_action(
            option_id="user",
        ),
        safe_action(
            option_id="chosen",
        ),
        dangerous_action(
            option_id="danger",
        ),
    )

    assert tuple(
        option.option_id
        for option
        in decision.rejected_options
    ) == (
        "user",
        "danger",
    )


def test_decision_confidence_reuses_chosen_option_confidence():
    item = situation()

    decision = decide(
        item,
        safe_action(
            confidence=ConfidenceBand.HIGH,
        ),
    )

    assert (
        decision.confidence
        == decision.chosen_option.confidence
        == 0.75
    )


def test_dangerous_choice_preserves_permission_burden_without_authorizing():
    item = situation()

    decision = decide(
        item,
        dangerous_action(),
    )

    assert (
        decision.required_permission
        == PermissionLevel.DANGEROUS
    )

    assert (
        decision.disposition
        == TacticalDisposition.ADVISE
    )

    assert decision.authority == "NONE"


def test_every_decision_remains_zero_authority():
    item = situation(
        uncertainties=(
            "Unknown.",
        )
    )

    decision = decide(
        item,
        observe(),
        safe_action(),
    )

    assert decision.authority == "NONE"

    assert (
        decision.chosen_option.authority
        == "NONE"
    )


def test_tampered_verified_simulation_is_rejected():
    item = situation()

    candidate = generate(
        item,
        safe_action(),
    )[0]

    object.__setattr__(
        candidate.simulation,
        "outcome_verified",
        True,
    )

    with pytest.raises(
        ValueError,
        match="prediction-only",
    ):
        TacticalDecisionEngine().decide(
            item,
            (
                candidate,
            ),
        )


def test_tampered_prediction_only_flag_is_rejected():
    item = situation()

    candidate = generate(
        item,
        safe_action(),
    )[0]

    object.__setattr__(
        candidate.simulation,
        "prediction_only",
        False,
    )

    with pytest.raises(
        ValueError,
        match="prediction-only",
    ):
        TacticalDecisionEngine().decide(
            item,
            (
                candidate,
            ),
        )


def test_simulation_uncertainty_must_match_situation():
    item = situation(
        uncertainties=(
            "Known uncertainty.",
        )
    )

    candidate = generate(
        item,
        safe_action(),
    )[0]

    object.__setattr__(
        candidate.simulation,
        "remaining_uncertainties",
        (),
    )

    with pytest.raises(
        ValueError,
        match="uncertainty",
    ):
        TacticalDecisionEngine().decide(
            item,
            (
                candidate,
            ),
        )


def test_prediction_must_match_tactical_option_expected_outcome():
    item = situation()

    candidate = generate(
        item,
        safe_action(),
    )[0]

    object.__setattr__(
        candidate.simulation,
        "predicted_outcome",
        "Tampered prediction.",
    )

    with pytest.raises(
        ValueError,
        match="predicted outcome",
    ):
        TacticalDecisionEngine().decide(
            item,
            (
                candidate,
            ),
        )


def test_confidence_must_match_simulation_envelope():
    item = situation()

    candidate = generate(
        item,
        safe_action(),
    )[0]

    object.__setattr__(
        candidate.simulation,
        "confidence_score",
        0.75,
    )

    with pytest.raises(
        ValueError,
        match="confidence",
    ):
        TacticalDecisionEngine().decide(
            item,
            (
                candidate,
            ),
        )


def test_candidate_capability_must_still_be_currently_available():
    base = situation()

    candidate = generate(
        base,
        safe_action(),
    )[0]

    changed = situation(
        capabilities=(
            "system_inspection",
        )
    )

    # Keep simulation uncertainty compatible with changed situation.
    assert (
        candidate.simulation.remaining_uncertainties
        == changed.uncertainties
    )

    with pytest.raises(
        ValueError,
        match="currently available",
    ):
        TacticalDecisionEngine().decide(
            changed,
            (
                candidate,
            ),
        )



def test_dangerous_risk_downgrade_is_rejected():
    item = situation()

    candidate = generate(
        item,
        dangerous_action(),
    )[0]

    downgraded = replace(
        candidate,
        option=replace(
            candidate.option,
            risk=TacticalRisk.HIGH,
        ),
    )

    with pytest.raises(
        ValueError,
        match="dangerous candidate risk",
    ):
        TacticalDecisionEngine().decide(
            item,
            (
                downgraded,
            ),
        )


def test_irreversible_low_risk_tamper_is_rejected():
    item = situation()

    candidate = generate(
        item,
        safe_action(),
    )[0]

    tampered = replace(
        candidate,
        option=replace(
            candidate.option,
            reversible=False,
            risk=TacticalRisk.LOW,
        ),
    )

    with pytest.raises(
        ValueError,
        match="irreversible candidate risk",
    ):
        TacticalDecisionEngine().decide(
            item,
            (
                tampered,
            ),
        )


def test_defer_policy_tamper_is_rejected():
    item = situation()

    candidate = generate(
        item,
        defer_seed(),
    )[0]

    tampered = replace(
        candidate,
        option=replace(
            candidate.option,
            cost=0.25,
        ),
    )

    with pytest.raises(
        ValueError,
        match="DEFER candidate",
    ):
        TacticalDecisionEngine().decide(
            item,
            (
                tampered,
            ),
        )

def test_duplicate_candidate_ids_are_rejected():
    item = situation()

    candidate = generate(
        item,
        safe_action(),
    )[0]

    with pytest.raises(
        ValueError,
        match="must be unique",
    ):
        TacticalDecisionEngine().decide(
            item,
            (
                candidate,
                candidate,
            ),
        )


def test_more_than_bounded_candidate_count_is_rejected():
    item = situation()

    base_candidate = generate(
        item,
        defer_seed(
            option_id="base-defer",
        ),
    )[0]

    # Construct an overbound 1E input from otherwise valid zero-authority
    # candidates without asking RAPHAEL-1D to exceed its own 12-option limit.
    candidates = tuple(
        replace(
            base_candidate,
            option=replace(
                base_candidate.option,
                option_id=f"over-{index}",
            ),
            simulation=replace(
                base_candidate.simulation,
                option_id=f"over-{index}",
            ),
        )
        for index
        in range(
            13
        )
    )

    with pytest.raises(
        ValueError,
        match="At most",
    ):
        TacticalDecisionEngine().decide(
            item,
            candidates,
        )


def test_wrong_candidate_type_is_rejected():
    with pytest.raises(
        TypeError,
        match="SimulatedTacticalOption",
    ):
        TacticalDecisionEngine().decide(
            situation(),
            (
                object(),
            ),
        )


def test_module_has_no_execution_confirmation_or_argument_surface():
    import app.agent.tactical_decision as module

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
        "tool_arguments",
        "arguments=",
    )

    for marker in forbidden:
        assert marker not in source


def test_module_has_no_provider_memory_sensor_or_model_surface():
    import app.agent.tactical_decision as module

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


def test_module_does_not_import_registry_or_runtime_permission_lookup():
    import app.agent.tactical_decision as module

    source = inspect.getsource(
        module
    )

    assert (
        "CapabilityRegistry"
        not in source
    )

    assert (
        "get_permission_level"
        not in source
    )

    assert (
        "require_explicit_permission"
        not in source
    )


def test_module_does_not_parse_constraint_keywords():
    import app.agent.tactical_decision as module

    source = inspect.getsource(
        module
    )

    forbidden = (
        'if "blocked" in',
        'if "dangerous" in',
        'if "do not" in',
        "constraint.lower(",
        "constraints.lower(",
    )

    lower_source = source.lower()

    for marker in forbidden:
        assert marker.lower() not in lower_source


def test_module_uses_transparent_lexicographic_key():
    import app.agent.tactical_decision as module

    source = inspect.getsource(
        module
    )

    assert "_candidate_key" in source

    assert "_PERMISSION_ORDER" in source

    assert "_RISK_ORDER" in source

    assert "best_option" not in source

    assert "weighted_score" not in source


def test_decision_never_exposes_approval_state():
    item = situation()

    decision = decide(
        item,
        dangerous_action(),
    )

    for field_name in (
        "approved",
        "confirmed",
        "permission_granted",
        "authorized",
        "execute",
    ):
        assert not hasattr(
            decision,
            field_name,
        )
