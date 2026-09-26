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
from app.agent.skill_registry import (
    SkillDefinition,
    SkillPhase,
    SkillRegistry,
)
from app.agent.skill_synthesis import (
    SkillSynthesisDisposition,
    SkillSynthesisProposal,
)
from app.agent.skill_validation import (
    SkillEvolutionDisposition,
    SkillEvolutionProposal,
    SkillEvolutionReviewer,
    SkillSandboxValidator,
    SkillScenarioDisposition,
    SkillScenarioEvidence,
    SkillScenarioKind,
    SkillValidationDisposition,
    SkillValidationEvidence,
    SkillValidationScenario,
    skill_definition_digest,
)


EVIDENCE_DIGEST = (
    "1" * 64
)


def capability_registry():
    return CapabilityRegistry(
        [
            Capability(
                name="system_inspection",
                description="Inspect system state.",
                tools=(
                    "inspect_system",
                ),
            ),
            Capability(
                name="application_control",
                description="Open applications.",
                tools=(
                    "open_app",
                ),
            ),
            Capability(
                name="web_research",
                description="Research public evidence.",
                tools=(
                    "web_search",
                ),
            ),
        ]
    )


def skill(
    *,
    reversible=True,
    preconditions=(
        "The target editor identity is known.",
    ),
    failure_modes=(
        "Inspection evidence may be insufficient.",
        "The editor may fail to open.",
    ),
):
    return SkillDefinition(
        skill_id="inspect_then_open",
        description="Inspect current state before opening the editor.",
        phases=(
            SkillPhase(
                phase_id="inspect",
                objective="Inspect current state.",
                dependencies=(),
                required_capabilities=(
                    "system_inspection",
                ),
                success_criteria=(
                    "Fresh system state is available.",
                ),
                verification_requirements=(
                    "Verify fresh inspection evidence.",
                ),
            ),
            SkillPhase(
                phase_id="open",
                objective="Open the editor after inspection.",
                dependencies=(
                    "inspect",
                ),
                required_capabilities=(
                    "application_control",
                ),
                success_criteria=(
                    "The editor is open.",
                ),
                verification_requirements=(
                    "Verify the editor is visible and responsive.",
                ),
            ),
        ),
        required_capabilities=(
            "system_inspection",
            "application_control",
        ),
        preconditions=preconditions,
        expected_outcomes=(
            "System state was inspected successfully.",
            "The editor opened successfully.",
        ),
        failure_modes=failure_modes,
        verification_requirements=(
            "Verify fresh inspection evidence.",
            "Verify the editor is visible and responsive.",
        ),
        reversible=reversible,
        provenance="raphael-1h-model-proposal:test",
    )


def proposal(
    *,
    item=None,
):
    if item is None:
        item = skill()

    return SkillSynthesisProposal(
        disposition=(
            SkillSynthesisDisposition.PROPOSED
        ),
        reason=(
            "Bounded zero-authority test proposal."
        ),
        evidence_digest=(
            EVIDENCE_DIGEST
        ),
        evidence_step_ids=(
            "inspect",
            "open",
        ),
        evidence_sufficient=True,
        remaining_uncertainties=(),
        skill=item,
    )


def complete_observations():
    return {
        "satisfied_preconditions": (
            "The target editor identity is known.",
        ),
        "observed_success_criteria": (
            "Fresh system state is available.",
            "The editor is open.",
        ),
        "satisfied_verification_requirements": (
            "Verify fresh inspection evidence.",
            "Verify the editor is visible and responsive.",
        ),
        "observed_outcomes": (
            "System state was inspected successfully.",
            "The editor opened successfully.",
        ),
    }


def replay_scenario(
    *,
    scenario_id="source-replay",
    available_capabilities=(
        "system_inspection",
        "application_control",
    ),
    source_digest=EVIDENCE_DIGEST,
    context_constraints=(),
    **overrides,
):
    values = complete_observations()
    values.update(
        overrides
    )

    return SkillValidationScenario(
        scenario_id=scenario_id,
        kind=(
            SkillScenarioKind.VERIFIED_REPLAY
        ),
        available_capabilities=(
            available_capabilities
        ),
        source_evidence_digest=(
            source_digest
        ),
        context_constraints=(
            context_constraints
        ),
        **values,
    )


def synthetic_scenario(
    *,
    scenario_id="synthetic-normal",
    available_capabilities=(
        "system_inspection",
        "application_control",
    ),
    context_constraints=(
        "The editor must be installed locally.",
    ),
    **overrides,
):
    values = complete_observations()
    values.update(
        overrides
    )

    return SkillValidationScenario(
        scenario_id=scenario_id,
        kind=(
            SkillScenarioKind.SYNTHETIC
        ),
        available_capabilities=(
            available_capabilities
        ),
        context_constraints=(
            context_constraints
        ),
        **values,
    )


def validator():
    return SkillSandboxValidator(
        capability_registry()
    )


def validated_evidence():
    return validator().validate(
        proposal(),
        (
            replay_scenario(),
            synthetic_scenario(),
        ),
    )


def rejected_evidence():
    return validator().validate(
        proposal(),
        (
            replay_scenario(),
            synthetic_scenario(
                scenario_id="missing-app-control",
                available_capabilities=(
                    "system_inspection",
                ),
            ),
        ),
    )


def test_validation_scenario_is_frozen_and_zero_authority():
    item = synthetic_scenario()

    assert item.authority == "NONE"

    with pytest.raises(
        FrozenInstanceError
    ):
        item.scenario_id = "changed"


def test_replay_scenario_requires_sha256_source_digest():
    with pytest.raises(
        ValueError,
        match="source_evidence_digest",
    ):
        replay_scenario(
            source_digest="bad",
        )


def test_synthetic_scenario_cannot_claim_verified_digest():
    with pytest.raises(
        ValueError,
        match="cannot claim",
    ):
        SkillValidationScenario(
            scenario_id="synthetic",
            kind=SkillScenarioKind.SYNTHETIC,
            available_capabilities=(
                "system_inspection",
            ),
            satisfied_preconditions=(),
            observed_success_criteria=(
                "Criterion.",
            ),
            satisfied_verification_requirements=(
                "Verification.",
            ),
            observed_outcomes=(
                "Outcome.",
            ),
            source_evidence_digest=(
                EVIDENCE_DIGEST
            ),
        )


def test_scenario_requires_nonempty_observation_surfaces():
    with pytest.raises(
        ValueError,
        match="requires success",
    ):
        SkillValidationScenario(
            scenario_id="empty",
            kind=SkillScenarioKind.SYNTHETIC,
            available_capabilities=(),
            satisfied_preconditions=(),
            observed_success_criteria=(),
            satisfied_verification_requirements=(),
            observed_outcomes=(),
        )


def test_skill_digest_is_stable():
    item = skill()

    assert (
        skill_definition_digest(
            item
        )
        == skill_definition_digest(
            item
        )
    )


def test_skill_digest_changes_when_skill_changes():
    first = skill()

    second = skill(
        preconditions=(
            "The target editor identity is known.",
            "The editor must be installed locally.",
        )
    )

    assert (
        skill_definition_digest(
            first
        )
        != skill_definition_digest(
            second
        )
    )


def test_validator_requires_capability_registry():
    with pytest.raises(
        TypeError,
        match="CapabilityRegistry",
    ):
        SkillSandboxValidator(
            object()
        )


def test_validator_requires_proposed_skill():
    rejected = SkillSynthesisProposal(
        disposition=(
            SkillSynthesisDisposition.REJECTED
        ),
        reason="Rejected test proposal.",
        evidence_digest=(
            EVIDENCE_DIGEST
        ),
        evidence_step_ids=(
            "inspect",
        ),
        evidence_sufficient=True,
        remaining_uncertainties=(),
        skill=None,
    )

    with pytest.raises(
        ValueError,
        match="PROPOSED",
    ):
        validator().validate(
            rejected,
            (
                synthetic_scenario(),
            ),
        )


def test_validator_requires_at_least_one_scenario():
    with pytest.raises(
        ValueError,
        match="at least one scenario",
    ):
        validator().validate(
            proposal(),
            (),
        )


def test_validator_rejects_duplicate_scenario_ids():
    with pytest.raises(
        ValueError,
        match="scenario IDs must be unique",
    ):
        validator().validate(
            proposal(),
            (
                synthetic_scenario(
                    scenario_id="same",
                ),
                synthetic_scenario(
                    scenario_id="same",
                ),
            ),
        )


def test_verified_replay_must_bind_to_proposal_evidence_digest():
    with pytest.raises(
        ValueError,
        match="does not match",
    ):
        validator().validate(
            proposal(),
            (
                replay_scenario(
                    source_digest=(
                        "2" * 64
                    ),
                ),
            ),
        )


def test_unknown_scenario_capability_fails_closed():
    with pytest.raises(
        ValueError,
        match="absent from",
    ):
        validator().validate(
            proposal(),
            (
                synthetic_scenario(
                    available_capabilities=(
                        "system_inspection",
                        "application_control",
                        "invented_capability",
                    ),
                ),
            ),
        )


def test_replay_plus_synthetic_full_coverage_validates():
    result = validated_evidence()

    assert (
        result.disposition
        == SkillValidationDisposition.VALIDATED
    )
    assert result.all_passed is True
    assert result.replay_covered is True
    assert result.synthetic_covered is True
    assert result.authority == "NONE"


def test_only_replay_coverage_is_inconclusive():
    result = validator().validate(
        proposal(),
        (
            replay_scenario(),
        ),
    )

    assert (
        result.disposition
        == SkillValidationDisposition.INCONCLUSIVE
    )
    assert result.all_passed is True


def test_only_synthetic_coverage_is_inconclusive():
    result = validator().validate(
        proposal(),
        (
            synthetic_scenario(),
        ),
    )

    assert (
        result.disposition
        == SkillValidationDisposition.INCONCLUSIVE
    )
    assert result.all_passed is True


def test_missing_capability_rejects_scenario():
    result = rejected_evidence()

    assert (
        result.disposition
        == SkillValidationDisposition.REJECTED
    )

    failed = result.scenario_results[1]

    assert failed.missing_capabilities == (
        "application_control",
    )
    assert failed.passed is False


def test_unmet_precondition_rejects_scenario():
    result = validator().validate(
        proposal(),
        (
            replay_scenario(),
            synthetic_scenario(
                satisfied_preconditions=(),
            ),
        ),
    )

    assert (
        result.disposition
        == SkillValidationDisposition.REJECTED
    )

    assert result.scenario_results[1].unmet_preconditions == (
        "The target editor identity is known.",
    )


def test_missing_success_criterion_rejects_scenario():
    result = validator().validate(
        proposal(),
        (
            replay_scenario(),
            synthetic_scenario(
                observed_success_criteria=(
                    "Fresh system state is available.",
                ),
            ),
        ),
    )

    assert (
        result.scenario_results[1]
        .missing_success_criteria
        == (
            "The editor is open.",
        )
    )


def test_missing_verification_requirement_rejects_scenario():
    result = validator().validate(
        proposal(),
        (
            replay_scenario(),
            synthetic_scenario(
                satisfied_verification_requirements=(
                    "Verify fresh inspection evidence.",
                ),
            ),
        ),
    )

    assert (
        result.scenario_results[1]
        .missing_verification_requirements
        == (
            "Verify the editor is visible and responsive.",
        )
    )


def test_missing_expected_outcome_rejects_scenario():
    result = validator().validate(
        proposal(),
        (
            replay_scenario(),
            synthetic_scenario(
                observed_outcomes=(
                    "System state was inspected successfully.",
                ),
            ),
        ),
    )

    assert (
        result.scenario_results[1]
        .missing_expected_outcomes
        == (
            "The editor opened successfully.",
        )
    )


def test_scenario_evidence_is_frozen_and_zero_authority():
    result = validated_evidence().scenario_results[0]

    assert result.authority == "NONE"

    with pytest.raises(
        FrozenInstanceError
    ):
        result.disposition = (
            SkillScenarioDisposition.FAILED
        )


def test_validation_evidence_is_frozen_and_zero_authority():
    result = validated_evidence()

    assert result.authority == "NONE"

    with pytest.raises(
        FrozenInstanceError
    ):
        result.reason = "changed"


def test_validation_digest_is_stable_for_same_inputs():
    first = validated_evidence()
    second = validated_evidence()

    assert (
        first.validation_digest
        == second.validation_digest
    )


def test_validation_digest_changes_when_scenario_changes():
    first = validated_evidence()

    second = validator().validate(
        proposal(),
        (
            replay_scenario(),
            synthetic_scenario(
                scenario_id="different-id",
            ),
        ),
    )

    assert (
        first.validation_digest
        != second.validation_digest
    )


def test_failure_observations_are_deterministic():
    result = rejected_evidence()

    assert result.failure_observations == (
        "Scenario 'missing-app-control' lacked required "
        "capability 'application_control'.",
    )


def test_context_constraints_are_carried_only_as_evolution_constraints():
    result = validated_evidence()

    assert result.evolution_constraints == (
        "The editor must be installed locally.",
    )


def test_validation_does_not_mutate_capability_registry():
    capabilities = capability_registry()

    before_names = set(
        capabilities.names()
    )

    before_all = tuple(
        capabilities.all()
    )

    engine = SkillSandboxValidator(
        capabilities
    )

    engine.validate(
        proposal(),
        (
            replay_scenario(),
            synthetic_scenario(),
        ),
    )

    assert set(
        capabilities.names()
    ) == before_names

    assert tuple(
        capabilities.all()
    ) == before_all


def test_validation_does_not_register_skill_into_external_registry():
    capabilities = capability_registry()

    external = SkillRegistry(
        capabilities
    )

    SkillSandboxValidator(
        capabilities
    ).validate(
        proposal(),
        (
            replay_scenario(),
            synthetic_scenario(),
        ),
    )

    assert external.ids() == ()


def test_synthetic_pass_does_not_claim_verified_reality():
    result = validator().validate(
        proposal(),
        (
            synthetic_scenario(),
        ),
    )

    assert (
        result.scenario_results[0].kind
        == SkillScenarioKind.SYNTHETIC
    )

    assert (
        result.disposition
        == SkillValidationDisposition.INCONCLUSIVE
    )


def test_evolution_reviewer_requires_capability_registry():
    with pytest.raises(
        TypeError,
        match="CapabilityRegistry",
    ):
        SkillEvolutionReviewer(
            object()
        )


def test_validated_skill_without_candidate_returns_no_change():
    result = SkillEvolutionReviewer(
        capability_registry()
    ).review(
        proposal(),
        validated_evidence(),
        None,
    )

    assert (
        result.disposition
        == SkillEvolutionDisposition.NO_CHANGE
    )
    assert result.evolved_skill is None
    assert result.authority == "NONE"


def test_failed_validation_without_candidate_is_rejected():
    result = SkillEvolutionReviewer(
        capability_registry()
    ).review(
        proposal(),
        rejected_evidence(),
        None,
    )

    assert (
        result.disposition
        == SkillEvolutionDisposition.REJECTED
    )


def test_fully_validated_skill_cannot_be_silently_changed():
    candidate = skill(
        preconditions=(
            "The target editor identity is known.",
            "The editor must be installed locally.",
        )
    )

    result = SkillEvolutionReviewer(
        capability_registry()
    ).review(
        proposal(),
        validated_evidence(),
        candidate,
    )

    assert (
        result.disposition
        == SkillEvolutionDisposition.REJECTED
    )


def test_evolution_rejects_skill_id_change():
    candidate = replace(
        skill(),
        skill_id="different",
    )

    result = SkillEvolutionReviewer(
        capability_registry()
    ).review(
        proposal(),
        rejected_evidence(),
        candidate,
    )

    assert (
        result.disposition
        == SkillEvolutionDisposition.REJECTED
    )


def test_evolution_rejects_phase_add_remove_or_reorder():
    original = skill()

    candidate = replace(
        original,
        phases=tuple(
            reversed(
                original.phases
            )
        ),
    )

    result = SkillEvolutionReviewer(
        capability_registry()
    ).review(
        proposal(
            item=original
        ),
        validator().validate(
            proposal(
                item=original
            ),
            (
                replay_scenario(),
                synthetic_scenario(
                    available_capabilities=(
                        "system_inspection",
                    ),
                ),
            ),
        ),
        candidate,
    )

    assert (
        result.disposition
        == SkillEvolutionDisposition.REJECTED
    )


def test_evolution_rejects_new_skill_capability():
    original = skill()

    candidate = replace(
        original,
        required_capabilities=(
            "system_inspection",
            "application_control",
            "web_research",
        ),
    )

    result = SkillEvolutionReviewer(
        capability_registry()
    ).review(
        proposal(
            item=original
        ),
        rejected_evidence(),
        candidate,
    )

    assert (
        result.disposition
        == SkillEvolutionDisposition.REJECTED
    )


def test_evolution_rejects_new_expected_outcome():
    original = skill()

    candidate = replace(
        original,
        expected_outcomes=(
            *original.expected_outcomes,
            "The editor will always open in future.",
        ),
    )

    result = SkillEvolutionReviewer(
        capability_registry()
    ).review(
        proposal(
            item=original
        ),
        rejected_evidence(),
        candidate,
    )

    assert (
        result.disposition
        == SkillEvolutionDisposition.REJECTED
    )


def test_evolution_rejects_new_skill_verification_requirement():
    original = skill()

    candidate = replace(
        original,
        verification_requirements=(
            *original.verification_requirements,
            "Trust the model.",
        ),
    )

    result = SkillEvolutionReviewer(
        capability_registry()
    ).review(
        proposal(
            item=original
        ),
        rejected_evidence(),
        candidate,
    )

    assert (
        result.disposition
        == SkillEvolutionDisposition.REJECTED
    )


def test_evolution_rejects_removed_precondition():
    original = skill()

    candidate = replace(
        original,
        preconditions=(),
    )

    result = SkillEvolutionReviewer(
        capability_registry()
    ).review(
        proposal(
            item=original
        ),
        rejected_evidence(),
        candidate,
    )

    assert (
        result.disposition
        == SkillEvolutionDisposition.REJECTED
    )


def test_evolution_accepts_new_precondition_only_from_context_constraint():
    original = skill()

    validation = validator().validate(
        proposal(
            item=original
        ),
        (
            replay_scenario(),
            synthetic_scenario(
                scenario_id="capability-gap",
                available_capabilities=(
                    "system_inspection",
                ),
                context_constraints=(
                    "The editor must be installed locally.",
                ),
            ),
        ),
    )

    candidate = replace(
        original,
        preconditions=(
            *original.preconditions,
            "The editor must be installed locally.",
        ),
    )

    result = SkillEvolutionReviewer(
        capability_registry()
    ).review(
        proposal(
            item=original
        ),
        validation,
        candidate,
    )

    assert (
        result.disposition
        == SkillEvolutionDisposition.PROPOSED
    )

    assert result.evolved_skill is candidate
    assert result.authority == "NONE"


def test_evolution_rejects_invented_new_precondition():
    original = skill()

    candidate = replace(
        original,
        preconditions=(
            *original.preconditions,
            "The moon must be full.",
        ),
    )

    result = SkillEvolutionReviewer(
        capability_registry()
    ).review(
        proposal(
            item=original
        ),
        rejected_evidence(),
        candidate,
    )

    assert (
        result.disposition
        == SkillEvolutionDisposition.REJECTED
    )


def test_evolution_accepts_failure_mode_from_validation_observation():
    original = skill()

    validation = rejected_evidence()

    candidate = replace(
        original,
        failure_modes=(
            *original.failure_modes,
            validation.failure_observations[0],
        ),
    )

    result = SkillEvolutionReviewer(
        capability_registry()
    ).review(
        proposal(
            item=original
        ),
        validation,
        candidate,
    )

    assert (
        result.disposition
        == SkillEvolutionDisposition.PROPOSED
    )


def test_evolution_rejects_invented_failure_mode():
    original = skill()

    candidate = replace(
        original,
        failure_modes=(
            *original.failure_modes,
            "Imaginary failure with no validation evidence.",
        ),
    )

    result = SkillEvolutionReviewer(
        capability_registry()
    ).review(
        proposal(
            item=original
        ),
        rejected_evidence(),
        candidate,
    )

    assert (
        result.disposition
        == SkillEvolutionDisposition.REJECTED
    )


def test_evolution_cannot_upgrade_irreversible_to_reversible():
    original = skill(
        reversible=False,
    )

    original_proposal = proposal(
        item=original
    )

    validation = validator().validate(
        original_proposal,
        (
            replay_scenario(),
            synthetic_scenario(
                available_capabilities=(
                    "system_inspection",
                ),
            ),
        ),
    )

    candidate = replace(
        original,
        reversible=True,
    )

    result = SkillEvolutionReviewer(
        capability_registry()
    ).review(
        original_proposal,
        validation,
        candidate,
    )

    assert (
        result.disposition
        == SkillEvolutionDisposition.REJECTED
    )


def test_evolution_may_make_reversibility_more_conservative():
    original = skill(
        reversible=True,
    )

    original_proposal = proposal(
        item=original
    )

    validation = validator().validate(
        original_proposal,
        (
            replay_scenario(),
            synthetic_scenario(
                available_capabilities=(
                    "system_inspection",
                ),
            ),
        ),
    )

    candidate = replace(
        original,
        reversible=False,
    )

    result = SkillEvolutionReviewer(
        capability_registry()
    ).review(
        original_proposal,
        validation,
        candidate,
    )

    assert (
        result.disposition
        == SkillEvolutionDisposition.PROPOSED
    )


def test_evolution_rejects_new_phase_capability():
    # Keep the candidate structurally valid under RAPHAEL-1G.
    #
    # The original skill already declares web_research globally,
    # but its inspect phase does not use it. The evolved candidate
    # then expands only that phase's capability set. This allows the
    # request to reach RAPHAEL-1I's phase-level non-expansion gate
    # instead of being rejected earlier by SkillDefinition itself.
    original = replace(
        skill(),
        required_capabilities=(
            "system_inspection",
            "application_control",
            "web_research",
        ),
    )

    changed_phase = replace(
        original.phases[0],
        required_capabilities=(
            "system_inspection",
            "web_research",
        ),
    )

    candidate = replace(
        original,
        phases=(
            changed_phase,
            original.phases[1],
        ),
    )

    original_proposal = proposal(
        item=original
    )

    validation = validator().validate(
        original_proposal,
        (
            replay_scenario(),
            synthetic_scenario(
                available_capabilities=(
                    "system_inspection",
                    "application_control",
                ),
            ),
        ),
    )

    result = SkillEvolutionReviewer(
        capability_registry()
    ).review(
        original_proposal,
        validation,
        candidate,
    )

    assert (
        result.disposition
        == SkillEvolutionDisposition.REJECTED
    )

    assert (
        "phase capabilities"
        in result.reason
    )

def test_evolution_rejects_new_phase_success_criterion():
    original = skill()

    changed_phase = replace(
        original.phases[0],
        success_criteria=(
            *original.phases[0].success_criteria,
            "The machine is definitely healthy forever.",
        ),
    )

    candidate = replace(
        original,
        phases=(
            changed_phase,
            original.phases[1],
        ),
    )

    result = SkillEvolutionReviewer(
        capability_registry()
    ).review(
        proposal(
            item=original
        ),
        rejected_evidence(),
        candidate,
    )

    assert (
        result.disposition
        == SkillEvolutionDisposition.REJECTED
    )


def test_evolution_rejects_new_phase_verification_requirement():
    original = skill()

    changed_phase = replace(
        original.phases[0],
        verification_requirements=(
            *original.phases[0].verification_requirements,
            "Assume it worked.",
        ),
    )

    candidate = replace(
        original,
        phases=(
            changed_phase,
            original.phases[1],
        ),
    )

    result = SkillEvolutionReviewer(
        capability_registry()
    ).review(
        proposal(
            item=original
        ),
        rejected_evidence(),
        candidate,
    )

    assert (
        result.disposition
        == SkillEvolutionDisposition.REJECTED
    )


def test_evolution_rejects_removed_phase_dependency():
    original = skill()

    changed_open = replace(
        original.phases[1],
        dependencies=(),
    )

    candidate = replace(
        original,
        phases=(
            original.phases[0],
            changed_open,
        ),
    )

    result = SkillEvolutionReviewer(
        capability_registry()
    ).review(
        proposal(
            item=original
        ),
        rejected_evidence(),
        candidate,
    )

    assert (
        result.disposition
        == SkillEvolutionDisposition.REJECTED
    )


def test_evolution_proposal_is_frozen_and_zero_authority():
    validation = rejected_evidence()

    original = skill()

    candidate = replace(
        original,
        failure_modes=(
            *original.failure_modes,
            validation.failure_observations[0],
        ),
    )

    result = SkillEvolutionReviewer(
        capability_registry()
    ).review(
        proposal(
            item=original
        ),
        validation,
        candidate,
    )

    assert result.authority == "NONE"

    with pytest.raises(
        FrozenInstanceError
    ):
        result.reason = "changed"


def test_validation_evidence_tampering_breaks_proposal_binding():
    original = proposal()

    validation = validated_evidence()

    object.__setattr__(
        validation,
        "skill_digest",
        "2" * 64,
    )

    result = SkillEvolutionReviewer(
        capability_registry()
    ).review(
        original,
        validation,
        None,
    )

    assert (
        result.disposition
        == SkillEvolutionDisposition.REJECTED
    )


def test_tampered_original_authority_is_rejected_by_validator():
    original = proposal()

    object.__setattr__(
        original,
        "authority",
        "AUTHORIZED",
    )

    with pytest.raises(
        ValueError,
        match="authority",
    ):
        validator().validate(
            original,
            (
                synthetic_scenario(),
            ),
        )


def test_tampered_skill_authority_is_rejected_by_validator():
    original = proposal()

    object.__setattr__(
        original.skill,
        "authority",
        "AUTHORIZED",
    )

    with pytest.raises(
        ValueError,
        match="authority",
    ):
        validator().validate(
            original,
            (
                synthetic_scenario(),
            ),
        )


def test_validator_has_no_execute_or_register_surface():
    engine = validator()

    for name in (
        "execute",
        "run_tool",
        "register",
        "install",
        "authorize",
        "approve",
        "persist",
    ):
        assert not hasattr(
            engine,
            name,
        )


def test_evolution_reviewer_has_no_generate_execute_or_register_surface():
    engine = SkillEvolutionReviewer(
        capability_registry()
    )

    for name in (
        "generate",
        "synthesize",
        "execute",
        "run_tool",
        "register",
        "install",
        "authorize",
        "approve",
        "persist",
    ):
        assert not hasattr(
            engine,
            name,
        )


def test_module_has_no_native_repair_sandbox_or_subprocess_surface():
    import app.agent.skill_validation as module

    source = inspect.getsource(
        module
    )

    forbidden = (
        "repair_execution_sandbox",
        "RepairExecutionSandbox",
        "import subprocess",
        "subprocess.",
        "sandbox-exec",
        "_run_contained_python",
        "repair_workspace",
        "RepairWorkspace",
    )

    for marker in forbidden:
        assert marker not in source


def test_module_has_no_executor_permission_tool_registration_or_confirmation_surface():
    import app.agent.skill_validation as module

    source = inspect.getsource(
        module
    )

    forbidden = (
        "from app.agent.executor",
        "from app.agent.permissions",
        "PermissionLevel",
        "require_explicit_permission",
        "register_tool(",
        "TOOL_PERMISSIONS",
        "from app.agent.kuma_agent",
        "from app.agent.mission_service",
        ".execute(",
        "execute_mission_step(",
        "request_confirmation(",
        "confirmation_callback",
    )

    for marker in forbidden:
        assert marker not in source


def test_module_has_no_model_provider_memory_sensor_network_or_persistence_surface():
    import app.agent.skill_validation as module

    source = inspect.getsource(
        module
    )

    forbidden = (
        "ollama",
        "model_call",
        "generate_content(",
        "ask_model(",
        "app.memory",
        "get_memory_context",
        "retrieve_memories",
        "app.realtime",
        "get_current_location(",
        "web_search(",
        "fetch_webpage(",
        "requests",
        "urllib",
        "pyautogui",
        "sqlite",
        "write_text(",
        "write_bytes(",
        "open(",
    )

    for marker in forbidden:
        assert marker not in source


def test_module_has_no_dynamic_code_execution_surface():
    import app.agent.skill_validation as module

    source = inspect.getsource(
        module
    )

    for marker in (
        "exec(",
        "eval(",
        "compile(",
        "importlib",
        "pickle",
        "marshal",
    ):
        assert marker not in source


def test_validation_and_evolution_outputs_have_no_authorization_surface():
    validation = validated_evidence()

    evolution = SkillEvolutionReviewer(
        capability_registry()
    ).review(
        proposal(),
        validation,
        None,
    )

    for item in (
        validation,
        evolution,
    ):
        for name in (
            "approved",
            "authorized",
            "permission_granted",
            "registered",
            "installed",
            "tool_name",
            "arguments",
            "execute",
        ):
            assert not hasattr(
                item,
                name,
            )
