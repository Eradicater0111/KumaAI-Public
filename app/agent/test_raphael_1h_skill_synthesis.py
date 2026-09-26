from __future__ import annotations

from dataclasses import FrozenInstanceError
import inspect
import json

import pytest

from app.agent.capability_registry import (
    Capability,
    CapabilityRegistry,
)
from app.agent.skill_registry import (
    SkillDefinition,
    SkillRegistry,
)
from app.agent.skill_synthesis import (
    ExperienceSource,
    SkillSynthesisDisposition,
    SkillSynthesisProposal,
    SkillSynthesizer,
    VerifiedExperience,
    VerifiedExperienceStep,
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
                description="Read public web evidence.",
                tools=(
                    "web_search",
                    "fetch_webpage",
                ),
            ),
        ]
    )


def step(
    *,
    step_id,
    objective,
    capability,
    criterion,
    requirement,
    outcome,
    evidence,
    reversible=True,
    effect_started=False,
    source=ExperienceSource.MISSION_VERIFICATION,
    success=True,
    verified=True,
    effect_known=True,
):
    return VerifiedExperienceStep(
        step_id=step_id,
        objective=objective,
        capabilities_used=(
            capability,
        ) if capability else (),
        success_criteria=(
            criterion,
        ),
        verification_requirements=(
            requirement,
        ),
        verified_outcome=outcome,
        verification_evidence=evidence,
        source=source,
        reversible=reversible,
        effect_started=effect_started,
        success=success,
        verified=verified,
        effect_known=effect_known,
    )


def experience(
    *,
    uncertainties=(),
    second_capability="application_control",
):
    return VerifiedExperience(
        goal="Inspect state and open the editor.",
        steps=(
            step(
                step_id="inspect",
                objective="Inspect current system state.",
                capability="system_inspection",
                criterion="Fresh system state is available.",
                requirement="Verify fresh inspection evidence.",
                outcome="System state was inspected successfully.",
                evidence="Independent inspection result was verified.",
                reversible=True,
                effect_started=False,
            ),
            step(
                step_id="open",
                objective="Open the editor.",
                capability=second_capability,
                criterion="The editor is open.",
                requirement="Verify the editor is visible and responsive.",
                outcome="The editor opened successfully.",
                evidence="Post-action state verification confirmed the editor.",
                reversible=True,
                effect_started=True,
            ),
        ),
        failures_recoveries=(
            "No recovery was required.",
        ),
        remaining_uncertainties=uncertainties,
    )


def valid_payload():
    return {
        "skill_id": "inspect_then_open",
        "description": "Inspect current state before opening the editor.",
        "required_capabilities": [
            "system_inspection",
            "application_control",
        ],
        "preconditions": [
            "The target editor identity is known.",
        ],
        "expected_outcomes": [
            "System state was inspected successfully.",
            "The editor opened successfully.",
        ],
        "failure_modes": [
            "Inspection evidence may be insufficient.",
            "The editor may fail to open.",
        ],
        "verification_requirements": [
            "Verify fresh inspection evidence.",
            "Verify the editor is visible and responsive.",
        ],
        "remaining_uncertainties": [],
        "phases": [
            {
                "phase_id": "inspect",
                "objective": "Inspect current state.",
                "dependencies": [],
                "required_capabilities": [
                    "system_inspection",
                ],
                "success_criteria": [
                    "Fresh system state is available.",
                ],
                "verification_requirements": [
                    "Verify fresh inspection evidence.",
                ],
                "evidence_step_ids": [
                    "inspect",
                ],
            },
            {
                "phase_id": "open",
                "objective": "Open the editor after inspection.",
                "dependencies": [
                    "inspect",
                ],
                "required_capabilities": [
                    "application_control",
                ],
                "success_criteria": [
                    "The editor is open.",
                ],
                "verification_requirements": [
                    "Verify the editor is visible and responsive.",
                ],
                "evidence_step_ids": [
                    "open",
                ],
            },
        ],
    }


def response(payload=None):
    if payload is None:
        payload = valid_payload()

    return json.dumps(
        payload
    )


def synthesizer(
    model_call=None,
    *,
    registry=None,
):
    if model_call is None:
        model_call = lambda messages: response()

    return SkillSynthesizer(
        capability_registry=(
            registry
            if registry is not None
            else capability_registry()
        ),
        model_call=model_call,
    )


def test_verified_experience_step_is_frozen_and_zero_authority():
    item = experience().steps[0]

    assert item.authority == "NONE"

    with pytest.raises(
        FrozenInstanceError
    ):
        item.objective = "changed"


def test_verified_experience_is_frozen_and_zero_authority():
    item = experience()

    assert item.authority == "NONE"

    with pytest.raises(
        FrozenInstanceError
    ):
        item.goal = "changed"


def test_verified_step_rejects_failed_action():
    with pytest.raises(
        ValueError,
        match="successful execution",
    ):
        step(
            step_id="failed",
            objective="Failed.",
            capability="system_inspection",
            criterion="Done.",
            requirement="Verify.",
            outcome="Failed.",
            evidence="Evidence.",
            success=False,
        )


def test_verified_step_rejects_unverified_action():
    with pytest.raises(
        ValueError,
        match="verified outcome",
    ):
        step(
            step_id="unverified",
            objective="Unverified.",
            capability="system_inspection",
            criterion="Done.",
            requirement="Verify.",
            outcome="Unknown.",
            evidence="Weak evidence.",
            verified=False,
        )


def test_verified_step_rejects_unknown_effect_state():
    with pytest.raises(
        ValueError,
        match="known effect state",
    ):
        step(
            step_id="unknown-effect",
            objective="Unknown effect.",
            capability="system_inspection",
            criterion="Done.",
            requirement="Verify.",
            outcome="Unknown.",
            evidence="Evidence.",
            effect_known=False,
        )


def test_prediction_source_cannot_be_used_as_verified_experience_source():
    with pytest.raises(
        TypeError,
        match="ExperienceSource",
    ):
        step(
            step_id="prediction",
            objective="Prediction.",
            capability="system_inspection",
            criterion="Done.",
            requirement="Verify.",
            outcome="Predicted.",
            evidence="Prediction only.",
            source="raphael_prediction",
        )


def test_single_verified_action_is_not_reusable_skill_experience():
    only = step(
        step_id="only",
        objective="Only one action.",
        capability="system_inspection",
        criterion="Observed.",
        requirement="Verify observation.",
        outcome="Observed successfully.",
        evidence="Verified observation.",
    )

    with pytest.raises(
        ValueError,
        match="at least two verified steps",
    ):
        VerifiedExperience(
            goal="One action.",
            steps=(
                only,
            ),
        )


def test_experience_requires_unique_step_ids():
    first = step(
        step_id="same",
        objective="One.",
        capability="system_inspection",
        criterion="One done.",
        requirement="Verify one.",
        outcome="One outcome.",
        evidence="One evidence.",
    )

    second = step(
        step_id="same",
        objective="Two.",
        capability="application_control",
        criterion="Two done.",
        requirement="Verify two.",
        outcome="Two outcome.",
        evidence="Two evidence.",
    )

    with pytest.raises(
        ValueError,
        match="step IDs must be unique",
    ):
        VerifiedExperience(
            goal="Duplicate IDs.",
            steps=(
                first,
                second,
            ),
        )


def test_capabilities_used_are_deterministic_first_seen_union():
    item = experience()

    assert item.capabilities_used == (
        "system_inspection",
        "application_control",
    )


def test_experience_reversible_is_derived_from_steps():
    item = experience()
    assert item.reversible is True

    irreversible = VerifiedExperience(
        goal=item.goal,
        steps=(
            item.steps[0],
            step(
                step_id="open-irreversible",
                objective="Irreversible action.",
                capability="application_control",
                criterion="Action complete.",
                requirement="Verify action.",
                outcome="Irreversible outcome verified.",
                evidence="Independent evidence.",
                reversible=False,
                effect_started=True,
            ),
        ),
    )

    assert irreversible.reversible is False


def test_unresolved_experience_uncertainty_fails_before_model_call():
    calls = []

    def model_call(messages):
        calls.append(messages)
        return response()

    proposal = synthesizer(
        model_call
    ).synthesize(
        experience(
            uncertainties=(
                "Final application identity remains uncertain.",
            )
        )
    )

    assert (
        proposal.disposition
        == SkillSynthesisDisposition.INSUFFICIENT
    )
    assert proposal.evidence_sufficient is False
    assert proposal.skill is None
    assert calls == []


def test_unknown_experience_capability_fails_before_model_call():
    calls = []

    def model_call(messages):
        calls.append(messages)
        return response()

    proposal = synthesizer(
        model_call
    ).synthesize(
        experience(
            second_capability="invented_capability",
        )
    )

    assert (
        proposal.disposition
        == SkillSynthesisDisposition.INSUFFICIENT
    )
    assert calls == []


def test_valid_verified_experience_produces_proposal():
    proposal = synthesizer().synthesize(
        experience()
    )

    assert (
        proposal.disposition
        == SkillSynthesisDisposition.PROPOSED
    )
    assert proposal.evidence_sufficient is True
    assert isinstance(
        proposal.skill,
        SkillDefinition,
    )
    assert proposal.authority == "NONE"
    assert proposal.skill.authority == "NONE"


def test_proposed_skill_is_not_registered_anywhere_automatically():
    capabilities = capability_registry()

    external_registry = SkillRegistry(
        capabilities
    )

    proposal = synthesizer(
        registry=capabilities
    ).synthesize(
        experience()
    )

    assert proposal.skill is not None
    assert external_registry.ids() == ()


def test_proposed_skill_provenance_is_set_by_synthesizer():
    proposal = synthesizer().synthesize(
        experience()
    )

    assert proposal.skill.provenance.startswith(
        "raphael-1h-model-proposal:"
    )


def test_reversibility_is_derived_from_experience_not_model_output():
    payload = valid_payload()

    assert "reversible" not in payload

    base = experience()

    irreversible = VerifiedExperience(
        goal=base.goal,
        steps=(
            base.steps[0],
            step(
                step_id="open",
                objective="Open the editor.",
                capability="application_control",
                criterion="The editor is open.",
                requirement="Verify the editor is visible and responsive.",
                outcome="The editor opened successfully.",
                evidence="Post-action state verification confirmed the editor.",
                reversible=False,
                effect_started=True,
            ),
        ),
    )

    proposal = synthesizer().synthesize(
        irreversible
    )

    assert proposal.skill.reversible is False


def test_model_receives_only_bounded_verified_evidence_and_capability_names():
    calls = []

    def model_call(messages):
        calls.append(messages)
        return response()

    synthesizer(
        model_call
    ).synthesize(
        experience()
    )

    assert len(calls) == 1
    assert len(calls[0]) == 2

    user_payload = json.loads(
        calls[0][1][
            "content"
        ]
    )

    assert set(
        user_payload
    ) == {
        "canonical_capabilities",
        "required_output_schema",
        "verified_experience",
    }

    assert "tool_registry" not in calls[0][1]["content"]
    assert "permission" not in user_payload["verified_experience"]


def test_prompt_explicitly_forbids_tool_permission_authority_and_code_invention():
    calls = []

    def model_call(messages):
        calls.append(messages)
        return response()

    synthesizer(
        model_call
    ).synthesize(
        experience()
    )

    system = calls[0][0][
        "content"
    ].lower()

    for marker in (
        "do not invent tools",
        "permissions",
        "authority",
        "code",
        "do not request or execute tools",
        "do not claim the proposal is installed or registered",
    ):
        assert marker in system


def test_empty_model_response_is_rejected():
    proposal = synthesizer(
        lambda messages: ""
    ).synthesize(
        experience()
    )

    assert (
        proposal.disposition
        == SkillSynthesisDisposition.REJECTED
    )
    assert proposal.evidence_sufficient is True
    assert proposal.skill is None


def test_model_exception_is_rejected_fail_closed():
    def broken(messages):
        raise RuntimeError(
            "synthetic model failure"
        )

    proposal = synthesizer(
        broken
    ).synthesize(
        experience()
    )

    assert (
        proposal.disposition
        == SkillSynthesisDisposition.REJECTED
    )
    assert proposal.skill is None


def test_non_json_model_response_is_rejected():
    proposal = synthesizer(
        lambda messages: "not json"
    ).synthesize(
        experience()
    )

    assert (
        proposal.disposition
        == SkillSynthesisDisposition.REJECTED
    )


def test_non_object_json_response_is_rejected():
    proposal = synthesizer(
        lambda messages: "[]"
    ).synthesize(
        experience()
    )

    assert (
        proposal.disposition
        == SkillSynthesisDisposition.REJECTED
    )


def test_extra_top_level_key_is_rejected():
    payload = valid_payload()
    payload["tool_name"] = "open_app"

    proposal = synthesizer(
        lambda messages: response(
            payload
        )
    ).synthesize(
        experience()
    )

    assert (
        proposal.disposition
        == SkillSynthesisDisposition.REJECTED
    )


def test_missing_top_level_key_is_rejected():
    payload = valid_payload()
    del payload[
        "failure_modes"
    ]

    proposal = synthesizer(
        lambda messages: response(
            payload
        )
    ).synthesize(
        experience()
    )

    assert (
        proposal.disposition
        == SkillSynthesisDisposition.REJECTED
    )


def test_extra_phase_key_is_rejected():
    payload = valid_payload()
    payload[
        "phases"
    ][0][
        "planned_tool"
    ] = "inspect_system"

    proposal = synthesizer(
        lambda messages: response(
            payload
        )
    ).synthesize(
        experience()
    )

    assert (
        proposal.disposition
        == SkillSynthesisDisposition.REJECTED
    )


def test_unknown_evidence_step_reference_is_rejected():
    payload = valid_payload()
    payload[
        "phases"
    ][0][
        "evidence_step_ids"
    ] = [
        "missing"
    ]

    proposal = synthesizer(
        lambda messages: response(
            payload
        )
    ).synthesize(
        experience()
    )

    assert (
        proposal.disposition
        == SkillSynthesisDisposition.REJECTED
    )


def test_phase_requires_at_least_one_evidence_reference():
    payload = valid_payload()
    payload[
        "phases"
    ][0][
        "evidence_step_ids"
    ] = []

    proposal = synthesizer(
        lambda messages: response(
            payload
        )
    ).synthesize(
        experience()
    )

    assert (
        proposal.disposition
        == SkillSynthesisDisposition.REJECTED
    )


def test_model_cannot_expand_skill_capabilities_beyond_experience():
    payload = valid_payload()
    payload[
        "required_capabilities"
    ].append(
        "web_research"
    )

    proposal = synthesizer(
        lambda messages: response(
            payload
        )
    ).synthesize(
        experience()
    )

    assert (
        proposal.disposition
        == SkillSynthesisDisposition.REJECTED
    )


def test_phase_capability_must_be_supported_by_cited_step():
    payload = valid_payload()
    payload[
        "phases"
    ][0][
        "required_capabilities"
    ] = [
        "application_control"
    ]

    payload[
        "required_capabilities"
    ] = [
        "application_control",
    ]

    proposal = synthesizer(
        lambda messages: response(
            payload
        )
    ).synthesize(
        experience()
    )

    assert (
        proposal.disposition
        == SkillSynthesisDisposition.REJECTED
    )


def test_phase_success_criteria_must_be_copied_from_cited_evidence():
    payload = valid_payload()
    payload[
        "phases"
    ][0][
        "success_criteria"
    ] = [
        "The system is definitely perfect.",
    ]

    proposal = synthesizer(
        lambda messages: response(
            payload
        )
    ).synthesize(
        experience()
    )

    assert (
        proposal.disposition
        == SkillSynthesisDisposition.REJECTED
    )


def test_phase_verification_requirements_must_be_copied_from_evidence():
    payload = valid_payload()
    payload[
        "phases"
    ][0][
        "verification_requirements"
    ] = [
        "Trust the model output.",
    ]

    proposal = synthesizer(
        lambda messages: response(
            payload
        )
    ).synthesize(
        experience()
    )

    assert (
        proposal.disposition
        == SkillSynthesisDisposition.REJECTED
    )


def test_skill_expected_outcomes_must_be_copied_from_verified_outcomes():
    payload = valid_payload()
    payload[
        "expected_outcomes"
    ] = [
        "The editor will always open in future.",
    ]

    proposal = synthesizer(
        lambda messages: response(
            payload
        )
    ).synthesize(
        experience()
    )

    assert (
        proposal.disposition
        == SkillSynthesisDisposition.REJECTED
    )


def test_skill_verification_requirements_must_be_copied_from_experience():
    payload = valid_payload()
    payload[
        "verification_requirements"
    ] = [
        "Assume success if no exception appears.",
    ]

    proposal = synthesizer(
        lambda messages: response(
            payload
        )
    ).synthesize(
        experience()
    )

    assert (
        proposal.disposition
        == SkillSynthesisDisposition.REJECTED
    )


def test_skill_required_capabilities_must_equal_phase_union():
    payload = valid_payload()
    payload[
        "required_capabilities"
    ] = [
        "system_inspection",
    ]

    proposal = synthesizer(
        lambda messages: response(
            payload
        )
    ).synthesize(
        experience()
    )

    assert (
        proposal.disposition
        == SkillSynthesisDisposition.REJECTED
    )


def test_1g_dependency_validation_still_applies_to_synthesized_skill():
    payload = valid_payload()
    payload[
        "phases"
    ][0][
        "dependencies"
    ] = [
        "open"
    ]

    payload[
        "phases"
    ][1][
        "dependencies"
    ] = [
        "inspect"
    ]

    proposal = synthesizer(
        lambda messages: response(
            payload
        )
    ).synthesize(
        experience()
    )

    assert (
        proposal.disposition
        == SkillSynthesisDisposition.REJECTED
    )


def test_1g_skill_capability_validation_still_applies():
    capabilities = CapabilityRegistry(
        [
            Capability(
                name="system_inspection",
                description="Inspect.",
                tools=(
                    "inspect_system",
                ),
            ),
        ]
    )

    proposal = synthesizer(
        registry=capabilities
    ).synthesize(
        experience()
    )

    assert (
        proposal.disposition
        == SkillSynthesisDisposition.INSUFFICIENT
    )


def test_remaining_model_uncertainties_are_preserved_on_proposal():
    payload = valid_payload()
    payload[
        "remaining_uncertainties"
    ] = [
        "This procedure has only been observed in one application context.",
    ]

    proposal = synthesizer(
        lambda messages: response(
            payload
        )
    ).synthesize(
        experience()
    )

    assert (
        proposal.disposition
        == SkillSynthesisDisposition.PROPOSED
    )

    assert proposal.remaining_uncertainties == (
        "This procedure has only been observed in one application context.",
    )


def test_proposal_digest_is_stable_for_same_experience():
    item = experience()

    first = synthesizer().synthesize(
        item
    )

    second = synthesizer().synthesize(
        item
    )

    assert (
        first.evidence_digest
        == second.evidence_digest
    )


def test_proposal_digest_changes_when_verified_evidence_changes():
    first_experience = experience()

    changed = VerifiedExperience(
        goal=first_experience.goal,
        steps=(
            first_experience.steps[0],
            step(
                step_id="open",
                objective="Open the editor.",
                capability="application_control",
                criterion="The editor is open.",
                requirement="Verify the editor is visible and responsive.",
                outcome="The editor opened successfully.",
                evidence="A different verified evidence record.",
                effect_started=True,
            ),
        ),
    )

    first = synthesizer().synthesize(
        first_experience
    )

    second = synthesizer().synthesize(
        changed
    )

    assert (
        first.evidence_digest
        != second.evidence_digest
    )


def test_proposal_has_no_installation_authority_surface():
    proposal = synthesizer().synthesize(
        experience()
    )

    for name in (
        "installable",
        "installed",
        "registered",
        "approved",
        "authorized",
        "permission_granted",
        "execute",
        "tool_name",
        "arguments",
    ):
        assert not hasattr(
            proposal,
            name,
        )


def test_synthesizer_has_no_register_install_execute_method():
    engine = synthesizer()

    for name in (
        "register",
        "install",
        "execute",
        "run_tool",
        "approve",
        "authorize",
        "persist",
    ):
        assert not hasattr(
            engine,
            name,
        )


def test_model_call_is_required_dependency():
    with pytest.raises(
        TypeError,
        match="model_call",
    ):
        SkillSynthesizer(
            capability_registry=capability_registry(),
            model_call=None,
        )


def test_capability_registry_is_required_dependency():
    with pytest.raises(
        TypeError,
        match="CapabilityRegistry",
    ):
        SkillSynthesizer(
            capability_registry=object(),
            model_call=lambda messages: response(),
        )


def test_tampered_experience_authority_fails_closed_before_model_call():
    item = experience()
    object.__setattr__(
        item,
        "authority",
        "AUTHORIZED",
    )

    calls = []

    proposal = synthesizer(
        lambda messages: calls.append(
            messages
        )
    ).synthesize(
        item
    )

    assert (
        proposal.disposition
        == SkillSynthesisDisposition.INSUFFICIENT
    )
    assert calls == []


def test_tampered_step_authority_fails_closed_before_model_call():
    item = experience()
    object.__setattr__(
        item.steps[0],
        "authority",
        "AUTHORIZED",
    )

    calls = []

    proposal = synthesizer(
        lambda messages: calls.append(
            messages
        )
    ).synthesize(
        item
    )

    assert (
        proposal.disposition
        == SkillSynthesisDisposition.INSUFFICIENT
    )
    assert calls == []


def test_synthesis_proposal_is_frozen():
    proposal = synthesizer().synthesize(
        experience()
    )

    with pytest.raises(
        FrozenInstanceError
    ):
        proposal.reason = "changed"


def test_module_has_no_task_or_mission_state_dependency():
    import app.agent.skill_synthesis as module

    source = inspect.getsource(
        module
    )

    for marker in (
        "from app.agent.task_state",
        "from app.agent.mission_state",
        "TaskState(",
        "MissionState(",
    ):
        assert marker not in source


def test_module_has_no_executor_permission_tool_registration_or_confirmation_surface():
    import app.agent.skill_synthesis as module

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


def test_module_has_no_provider_memory_sensor_network_or_persistence_surface():
    import app.agent.skill_synthesis as module

    source = inspect.getsource(
        module
    )

    forbidden = (
        "ollama",
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
    import app.agent.skill_synthesis as module

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


def test_skill_output_schema_contains_no_runtime_tool_permission_or_code_fields():
    fields = set(
        SkillSynthesizer._TOP_KEYS
    )

    phase_fields = set(
        SkillSynthesizer._PHASE_KEYS
    )

    forbidden = {
        "tool",
        "tool_name",
        "planned_tool",
        "arguments",
        "permission",
        "required_permission",
        "approved",
        "authorized",
        "code",
        "source_code",
        "script",
    }

    assert not (
        forbidden
        & fields
    )

    assert not (
        forbidden
        & phase_fields
    )


def test_ephemeral_1g_validation_does_not_mutate_capability_registry():
    capabilities = capability_registry()

    before_names = set(
        capabilities.names()
    )

    before_all = tuple(
        capabilities.all()
    )

    proposal = synthesizer(
        registry=capabilities
    ).synthesize(
        experience()
    )

    assert (
        proposal.disposition
        == SkillSynthesisDisposition.PROPOSED
    )

    assert set(
        capabilities.names()
    ) == before_names

    assert tuple(
        capabilities.all()
    ) == before_all


def test_failure_recovery_notes_can_inform_prompt_but_do_not_become_authority():
    calls = []

    def model_call(messages):
        calls.append(messages)
        return response()

    proposal = synthesizer(
        model_call
    ).synthesize(
        experience()
    )

    assert (
        "No recovery was required."
        in calls[0][1]["content"]
    )
    assert proposal.authority == "NONE"


def test_proposed_skill_phase_and_proposal_all_remain_zero_authority():
    proposal = synthesizer().synthesize(
        experience()
    )

    assert proposal.authority == "NONE"
    assert proposal.skill.authority == "NONE"

    assert all(
        phase.authority == "NONE"
        for phase
        in proposal.skill.phases
    )
