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
    TacticalDecision,
    TacticalDisposition,
    TacticalRisk,
    TacticalSituation,
    WorldStateSnapshot,
)
from app.agent.permissions import (
    PermissionLevel,
)
from app.agent.tactical_decision import (
    TacticalDecisionEngine,
)
from app.agent.tactical_execution_bridge import (
    HandoffDisposition,
    RaphaelExecutionBridge,
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


STAMP = "2026-09-12T18:45:00+05:30"


def world():
    return WorldStateSnapshot(
        timestamp=STAMP,
        task_goal="Inspect or recover safely.",
    )


def situation(
    *,
    uncertainties=(),
    capabilities=(
        "system_inspection",
        "application_control",
        "command_execution",
        "pointer_control",
    ),
):
    return TacticalSituation(
        goal="Inspect or recover safely.",
        observed_state=(
            "system_state: editor responsive",
        ),
        known_facts=(
            "Task evidence: runtime active.",
        ),
        uncertainties=uncertainties,
        constraints=(
            "Do not bypass authority.",
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
                description="Open applications.",
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
                name="pointer_control",
                description="Move pointer.",
                tools=(
                    "move_mouse",
                ),
                risk_level="normal",
            ),
        ]
    )


def option_seed(
    *,
    option_id,
    kind,
    tool_name,
    capability,
    confidence=ConfidenceBand.HIGH,
    cost=CostBand.LOW,
    reversible=True,
):
    failure_modes = (
        ()
        if kind == OptionKind.OBSERVE
        else (
            "The action may not achieve the intended state.",
        )
    )

    recovery_notes = (
        ()
        if reversible
        else (
            "Use a separately verified containment path.",
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


def inspect_seed():
    return option_seed(
        option_id="inspect",
        kind=OptionKind.OBSERVE,
        tool_name="inspect_system",
        capability="system_inspection",
    )


def open_seed():
    return option_seed(
        option_id="open-app",
        kind=OptionKind.ACT,
        tool_name="open_app",
        capability="application_control",
    )


def dangerous_seed():
    return option_seed(
        option_id="command",
        kind=OptionKind.ACT,
        tool_name="execute_command",
        capability="command_execution",
        confidence=ConfidenceBand.HIGH,
        cost=CostBand.HIGH,
        reversible=False,
    )


def gui_seed():
    return option_seed(
        option_id="move-pointer",
        kind=OptionKind.ACT,
        tool_name="move_mouse",
        capability="pointer_control",
    )


def candidate_for(
    item,
    seed,
):
    return TacticalOptionGenerator(
        capability_registry=registry()
    ).generate(
        item,
        (
            seed,
        ),
        available_tool_names=(
            seed.tool_name,
        ),
    )[0]


def action_decision_for(
    item,
    candidate,
):
    return TacticalDecision(
        disposition=(
            TacticalDisposition.ACTION_CANDIDATE
        ),
        reason=(
            "Grounded tactical candidate."
        ),
        confidence=(
            candidate.option.confidence
        ),
        chosen_option=(
            candidate.option
        ),
        rejected_options=(),
        remaining_uncertainties=(
            item.uncertainties
        ),
    )


def bridge(
    authorizer=lambda request, tool, arguments: True,
    *,
    reg=None,
):
    return RaphaelExecutionBridge(
        capability_registry=(
            reg
            if reg is not None
            else registry()
        ),
        current_request_authorizer=authorizer,
    )


def prepare(
    item,
    candidate,
    decision=None,
    *,
    authorizer=lambda request, tool, arguments: True,
    request="Inspect or recover safely.",
    arguments=None,
    available_tools=None,
    reg=None,
):
    if decision is None:
        decision = action_decision_for(
            item,
            candidate,
        )

    if arguments is None:
        arguments = {}

    if available_tools is None:
        available_tools = (
            candidate.tool_name,
        )

    return bridge(
        authorizer,
        reg=reg,
    ).prepare(
        situation=item,
        decision=decision,
        candidate=candidate,
        current_request=request,
        arguments=arguments,
        available_tool_names=available_tools,
    )


def test_safe_observation_can_prepare_generic_handoff():
    item = situation()
    candidate = candidate_for(
        item,
        inspect_seed(),
    )

    assessment = prepare(
        item,
        candidate,
    )

    assert (
        assessment.disposition
        == HandoffDisposition.FORWARD_TO_KUMA
    )

    assert (
        assessment.handoff.required_permission
        == PermissionLevel.SAFE
    )

    assert (
        assessment.handoff.requires_confirmation
        is False
    )


def test_user_authorized_action_can_prepare_generic_handoff():
    item = situation()
    candidate = candidate_for(
        item,
        open_seed(),
    )

    assessment = prepare(
        item,
        candidate,
        request="Open the app.",
        arguments={
            "app_name": "TextEdit",
        },
    )

    assert (
        assessment.disposition
        == HandoffDisposition.FORWARD_TO_KUMA
    )

    assert (
        assessment.handoff.required_permission
        == PermissionLevel.USER_AUTHORIZED
    )


def test_dangerous_handoff_preserves_confirmation_requirement():
    item = situation()
    candidate = candidate_for(
        item,
        dangerous_seed(),
    )

    assessment = prepare(
        item,
        candidate,
        request="Run the command echo SAFE_TEST.",
        arguments={
            "command": "echo SAFE_TEST",
        },
    )

    assert (
        assessment.disposition
        == HandoffDisposition.FORWARD_TO_KUMA
    )

    assert (
        assessment.handoff.required_permission
        == PermissionLevel.DANGEROUS
    )

    assert (
        assessment.handoff.requires_confirmation
        is True
    )

    assert assessment.authority == "NONE"
    assert assessment.handoff.authority == "NONE"


def test_dangerous_handoff_contains_no_approval_state():
    item = situation()
    candidate = candidate_for(
        item,
        dangerous_seed(),
    )

    handoff = prepare(
        item,
        candidate,
        request="Run the command echo SAFE_TEST.",
        arguments={
            "command": "echo SAFE_TEST",
        },
    ).handoff

    for field_name in (
        "approved",
        "confirmed",
        "authorized",
        "permission_granted",
        "executed",
        "verified",
    ):
        assert not hasattr(
            handoff,
            field_name,
        )


def test_non_action_candidate_decision_is_rejected():
    item = situation()
    candidate = candidate_for(
        item,
        inspect_seed(),
    )

    decision = TacticalDecision(
        disposition=TacticalDisposition.ADVISE,
        reason="Advice only.",
        confidence=candidate.option.confidence,
        chosen_option=candidate.option,
        rejected_options=(),
        remaining_uncertainties=item.uncertainties,
    )

    assessment = prepare(
        item,
        candidate,
        decision,
    )

    assert (
        assessment.disposition
        == HandoffDisposition.REJECTED
    )


@pytest.mark.parametrize(
    "disposition",
    (
        TacticalDisposition.ADVISE,
        TacticalDisposition.DEFER,
        TacticalDisposition.BLOCKED,
    ),
)
def test_non_execution_dispositions_never_forward(disposition):
    item = situation()
    candidate = candidate_for(
        item,
        inspect_seed(),
    )

    chosen = (
        candidate.option
        if disposition
        != TacticalDisposition.BLOCKED
        else None
    )

    decision = TacticalDecision(
        disposition=disposition,
        reason="Not an execution candidate.",
        confidence=0.75,
        chosen_option=chosen,
        rejected_options=(
            ()
            if chosen is not None
            else (
                candidate.option,
            )
        ),
        remaining_uncertainties=item.uncertainties,
    )

    assessment = prepare(
        item,
        candidate,
        decision,
    )

    assert (
        assessment.disposition
        == HandoffDisposition.REJECTED
    )

    assert assessment.handoff is None


def test_mismatched_chosen_candidate_is_rejected():
    item = situation()

    chosen = candidate_for(
        item,
        inspect_seed(),
    )

    supplied = candidate_for(
        item,
        open_seed(),
    )

    decision = action_decision_for(
        item,
        chosen,
    )

    assessment = prepare(
        item,
        supplied,
        decision,
    )

    assert (
        assessment.disposition
        == HandoffDisposition.REJECTED
    )


def test_decision_uncertainty_must_match_current_situation():
    item = situation(
        uncertainties=(
            "Current uncertainty.",
        )
    )

    candidate = candidate_for(
        item,
        inspect_seed(),
    )

    decision = replace(
        action_decision_for(
            item,
            candidate,
        ),
        remaining_uncertainties=(),
    )

    assessment = prepare(
        item,
        candidate,
        decision,
    )

    assert (
        assessment.disposition
        == HandoffDisposition.REJECTED
    )


def test_prediction_must_remain_unverified():
    item = situation()
    candidate = candidate_for(
        item,
        inspect_seed(),
    )

    object.__setattr__(
        candidate.simulation,
        "outcome_verified",
        True,
    )

    assessment = prepare(
        item,
        candidate,
    )

    assert (
        assessment.disposition
        == HandoffDisposition.REJECTED
    )


def test_prediction_only_flag_must_remain_true():
    item = situation()
    candidate = candidate_for(
        item,
        inspect_seed(),
    )

    object.__setattr__(
        candidate.simulation,
        "prediction_only",
        False,
    )

    assessment = prepare(
        item,
        candidate,
    )

    assert (
        assessment.disposition
        == HandoffDisposition.REJECTED
    )


def test_simulation_uncertainty_must_match_current_situation():
    item = situation(
        uncertainties=(
            "Unknown state.",
        )
    )

    candidate = candidate_for(
        item,
        inspect_seed(),
    )

    object.__setattr__(
        candidate.simulation,
        "remaining_uncertainties",
        (),
    )

    assessment = prepare(
        item,
        candidate,
    )

    assert (
        assessment.disposition
        == HandoffDisposition.REJECTED
    )


def test_tool_must_still_be_currently_available():
    item = situation()
    candidate = candidate_for(
        item,
        inspect_seed(),
    )

    assessment = prepare(
        item,
        candidate,
        available_tools=(),
    )

    assert (
        assessment.disposition
        == HandoffDisposition.REJECTED
    )


def test_capability_must_still_be_currently_available():
    original = situation()
    candidate = candidate_for(
        original,
        inspect_seed(),
    )

    changed = situation(
        capabilities=(
            "application_control",
        )
    )

    assessment = prepare(
        changed,
        candidate,
    )

    assert (
        assessment.disposition
        == HandoffDisposition.REJECTED
    )


def test_capability_registry_ownership_must_still_match():
    item = situation()
    candidate = candidate_for(
        item,
        inspect_seed(),
    )

    wrong_registry = CapabilityRegistry(
        [
            Capability(
                name="system_inspection",
                description="Wrong binding.",
                tools=(
                    "open_app",
                ),
            )
        ]
    )

    assessment = prepare(
        item,
        candidate,
        reg=wrong_registry,
    )

    assert (
        assessment.disposition
        == HandoffDisposition.REJECTED
    )


def test_ambiguous_tool_ownership_is_rejected():
    item = situation()
    candidate = candidate_for(
        item,
        inspect_seed(),
    )

    ambiguous = CapabilityRegistry(
        [
            Capability(
                name="system_inspection",
                description="One.",
                tools=(
                    "inspect_system",
                ),
            ),
            Capability(
                name="duplicate_owner",
                description="Two.",
                tools=(
                    "inspect_system",
                ),
            ),
        ]
    )

    assessment = prepare(
        item,
        candidate,
        reg=ambiguous,
    )

    assert (
        assessment.disposition
        == HandoffDisposition.REJECTED
    )


def test_permission_mismatch_is_rejected():
    item = situation()
    candidate = candidate_for(
        item,
        open_seed(),
    )

    tampered_option = replace(
        candidate.option,
        required_permission=(
            PermissionLevel.SAFE
        ),
    )

    tampered_candidate = replace(
        candidate,
        option=tampered_option,
    )

    decision = action_decision_for(
        item,
        tampered_candidate,
    )

    assessment = prepare(
        item,
        tampered_candidate,
        decision,
        request="Open the app.",
    )

    assert (
        assessment.disposition
        == HandoffDisposition.REJECTED
    )


def test_dangerous_risk_downgrade_is_rejected():
    item = situation()
    candidate = candidate_for(
        item,
        dangerous_seed(),
    )

    tampered = replace(
        candidate,
        option=replace(
            candidate.option,
            risk=TacticalRisk.HIGH,
        ),
    )

    decision = action_decision_for(
        item,
        tampered,
    )

    assessment = prepare(
        item,
        tampered,
        decision,
        request="Run the command.",
        arguments={
            "command": "echo test",
        },
    )

    assert (
        assessment.disposition
        == HandoffDisposition.REJECTED
    )


def test_irreversible_low_risk_candidate_is_rejected():
    item = situation()
    candidate = candidate_for(
        item,
        inspect_seed(),
    )

    tampered = replace(
        candidate,
        option=replace(
            candidate.option,
            reversible=False,
            risk=TacticalRisk.MODERATE,
        ),
    )

    decision = action_decision_for(
        item,
        tampered,
    )

    assessment = prepare(
        item,
        tampered,
        decision,
    )

    assert (
        assessment.disposition
        == HandoffDisposition.REJECTED
    )


def test_false_current_request_grounding_rejects_handoff():
    item = situation()
    candidate = candidate_for(
        item,
        open_seed(),
    )

    assessment = prepare(
        item,
        candidate,
        authorizer=lambda request, tool, arguments: False,
        request="Tell me about TextEdit.",
        arguments={
            "app_name": "TextEdit",
        },
    )

    assert (
        assessment.disposition
        == HandoffDisposition.REJECTED
    )

    assert assessment.handoff is None


def test_grounding_callback_exception_fails_closed():
    def broken(
        request,
        tool,
        arguments,
    ):
        raise RuntimeError(
            "synthetic grounding failure"
        )

    item = situation()
    candidate = candidate_for(
        item,
        open_seed(),
    )

    assessment = prepare(
        item,
        candidate,
        authorizer=broken,
        request="Open the app.",
    )

    assert (
        assessment.disposition
        == HandoffDisposition.REJECTED
    )


def test_grounding_callback_non_boolean_fails_closed():
    item = situation()
    candidate = candidate_for(
        item,
        open_seed(),
    )

    assessment = prepare(
        item,
        candidate,
        authorizer=lambda request, tool, arguments: "yes",
        request="Open the app.",
    )

    assert (
        assessment.disposition
        == HandoffDisposition.REJECTED
    )


def test_authorizer_receives_exact_current_request_tool_and_argument_copy():
    calls = []

    def authorizer(
        request,
        tool,
        arguments,
    ):
        calls.append(
            (
                request,
                tool,
                arguments,
            )
        )
        return True

    item = situation()
    candidate = candidate_for(
        item,
        open_seed(),
    )

    assessment = prepare(
        item,
        candidate,
        authorizer=authorizer,
        request="Open   the\napp.",
        arguments={
            "app_name": "TextEdit",
            "flags": [
                "foreground",
            ],
        },
    )

    assert (
        assessment.disposition
        == HandoffDisposition.FORWARD_TO_KUMA
    )

    assert calls == [
        (
            "Open   the\napp.",
            "open_app",
            {
                "app_name": "TextEdit",
                "flags": [
                    "foreground",
                ],
            },
        )
    ]


def test_arguments_are_deeply_immutable_inside_handoff():
    item = situation()
    candidate = candidate_for(
        item,
        open_seed(),
    )

    source = {
        "app_name": "TextEdit",
        "nested": {
            "items": [
                "one",
                "two",
            ],
        },
    }

    assessment = prepare(
        item,
        candidate,
        request="Open the app.",
        arguments=source,
    )

    handoff = assessment.handoff

    source[
        "app_name"
    ] = "Changed"

    source[
        "nested"
    ][
        "items"
    ].append(
        "three"
    )

    assert (
        handoff.arguments[
            "app_name"
        ]
        == "TextEdit"
    )

    assert (
        handoff.arguments[
            "nested"
        ][
            "items"
        ]
        == (
            "one",
            "two",
        )
    )

    with pytest.raises(
        TypeError
    ):
        handoff.arguments[
            "app_name"
        ] = "Changed"


def test_arguments_copy_returns_fresh_mutable_copy():
    item = situation()
    candidate = candidate_for(
        item,
        open_seed(),
    )

    handoff = prepare(
        item,
        candidate,
        request="Open the app.",
        arguments={
            "nested": {
                "items": [
                    "one",
                ],
            },
        },
    ).handoff

    first = handoff.arguments_copy()
    second = handoff.arguments_copy()

    first[
        "nested"
    ][
        "items"
    ].append(
        "changed"
    )

    assert second == {
        "nested": {
            "items": [
                "one",
            ],
        },
    }


def test_argument_digest_is_order_independent_for_mapping_keys():
    item = situation()
    candidate = candidate_for(
        item,
        open_seed(),
    )

    first = prepare(
        item,
        candidate,
        request="Open the app.",
        arguments={
            "b": 2,
            "a": 1,
        },
    ).handoff

    second = prepare(
        item,
        candidate,
        request="Open the app.",
        arguments={
            "a": 1,
            "b": 2,
        },
    ).handoff

    assert (
        first.arguments_digest
        == second.arguments_digest
    )


def test_request_digest_binds_handoff_to_current_request():
    item = situation()
    candidate = candidate_for(
        item,
        open_seed(),
    )

    handoff = prepare(
        item,
        candidate,
        request="Open the app.",
    ).handoff

    assert (
        handoff.matches_current_request(
            "Open the app."
        )
        is True
    )

    assert (
        handoff.matches_current_request(
            "Close the app."
        )
        is False
    )



def test_request_digest_does_not_rewrite_internal_whitespace():
    item = situation()
    candidate = candidate_for(
        item,
        open_seed(),
    )

    handoff = prepare(
        item,
        candidate,
        request="Open   the app.",
    ).handoff

    assert (
        handoff.matches_current_request(
            "Open   the app."
        )
        is True
    )

    assert (
        handoff.matches_current_request(
            "Open the app."
        )
        is False
    )

def test_unsupported_argument_type_is_rejected():
    item = situation()
    candidate = candidate_for(
        item,
        open_seed(),
    )

    with pytest.raises(
        TypeError,
        match="JSON-like",
    ):
        prepare(
            item,
            candidate,
            request="Open the app.",
            arguments={
                "bad": object(),
            },
        )


def test_non_string_argument_key_is_rejected():
    item = situation()
    candidate = candidate_for(
        item,
        open_seed(),
    )

    with pytest.raises(
        TypeError,
        match="keys must be strings",
    ):
        prepare(
            item,
            candidate,
            request="Open the app.",
            arguments={
                1: "bad",
            },
        )


def test_nan_argument_is_rejected_before_digest():
    item = situation()
    candidate = candidate_for(
        item,
        open_seed(),
    )

    with pytest.raises(
        ValueError
    ):
        prepare(
            item,
            candidate,
            request="Open the app.",
            arguments={
                "value": float(
                    "nan"
                ),
            },
        )


def test_physical_gui_tool_routes_to_existing_gui_authority_pipeline():
    item = situation()
    candidate = candidate_for(
        item,
        gui_seed(),
    )

    assessment = prepare(
        item,
        candidate,
        request="Move the mouse.",
        arguments={
            "x": 10,
            "y": 20,
        },
    )

    assert (
        assessment.disposition
        == HandoffDisposition.GUI_AUTHORITY_REQUIRED
    )

    assert assessment.handoff is None

    assert (
        "GUI authority/provenance"
        in assessment.reason
    )


def test_gui_route_still_requires_current_request_grounding_first():
    item = situation()
    candidate = candidate_for(
        item,
        gui_seed(),
    )

    assessment = prepare(
        item,
        candidate,
        authorizer=lambda request, tool, arguments: False,
        request="Tell me about mouse movement.",
        arguments={
            "x": 10,
            "y": 20,
        },
    )

    assert (
        assessment.disposition
        == HandoffDisposition.REJECTED
    )


def test_handoff_assessment_is_frozen():
    item = situation()
    candidate = candidate_for(
        item,
        inspect_seed(),
    )

    assessment = prepare(
        item,
        candidate,
    )

    with pytest.raises(
        FrozenInstanceError
    ):
        assessment.reason = "changed"


def test_handoff_is_frozen():
    item = situation()
    candidate = candidate_for(
        item,
        inspect_seed(),
    )

    handoff = prepare(
        item,
        candidate,
    ).handoff

    with pytest.raises(
        FrozenInstanceError
    ):
        handoff.tool_name = "changed"


def test_every_bridge_layer_remains_zero_authority():
    item = situation()
    candidate = candidate_for(
        item,
        dangerous_seed(),
    )

    assessment = prepare(
        item,
        candidate,
        request="Run the command.",
        arguments={
            "command": "echo test",
        },
    )

    assert assessment.authority == "NONE"
    assert assessment.handoff.authority == "NONE"
    assert candidate.authority == "NONE"
    assert candidate.option.authority == "NONE"
    assert candidate.simulation.authority == "NONE"


def test_module_has_no_executor_agent_mission_or_confirmation_imports():
    import app.agent.tactical_execution_bridge as module

    source = inspect.getsource(
        module
    )

    forbidden = (
        "from app.agent.executor",
        "from app.agent.kuma_agent",
        "from app.agent.mission_service",
        "from app.agent.kuma_mission_executor",
        "confirm_dangerous_action",
        "request_confirmation(",
        "confirmation_callback",
        ".execute(",
        "execute_mission_step(",
    )

    for marker in forbidden:
        assert marker not in source


def test_module_has_no_provider_memory_sensor_or_model_surface():
    import app.agent.tactical_execution_bridge as module

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


def test_prepare_signature_has_no_approval_or_executor_parameter():
    signature = inspect.signature(
        RaphaelExecutionBridge.prepare
    )

    forbidden = {
        "approved",
        "confirmed",
        "authorization",
        "executor",
        "confirmation_callback",
    }

    assert not (
        forbidden
        & set(
            signature.parameters
        )
    )


def test_current_request_authorizer_is_required_dependency():
    with pytest.raises(
        TypeError,
        match="callable",
    ):
        RaphaelExecutionBridge(
            capability_registry=registry(),
            current_request_authorizer=None,
        )


def test_unknown_runtime_tool_permission_fails_closed():
    item = situation(
        capabilities=(
            "future",
        )
    )

    future_registry = CapabilityRegistry(
        [
            Capability(
                name="future",
                description="Future capability.",
                tools=(
                    "future_tool",
                ),
            )
        ]
    )

    option = replace(
        candidate_for(
            situation(),
            inspect_seed(),
        ).option,
        option_id="future-option",
        capability="future",
        expected_outcome="Future prediction.",
    )

    simulation = OutcomeSimulation(
        option_id="future-option",
        predicted_outcome="Future prediction.",
        confidence_band=ConfidenceBand.HIGH,
        confidence_score=0.75,
        assumptions=(),
        remaining_uncertainties=item.uncertainties,
        failure_modes=(),
        recovery_notes=(),
        verification_requirements=(
            "Verify future outcome.",
        ),
    )

    candidate = SimulatedTacticalOption(
        kind=OptionKind.OBSERVE,
        option=option,
        simulation=simulation,
        tool_name="future_tool",
    )

    decision = action_decision_for(
        item,
        candidate,
    )

    assessment = prepare(
        item,
        candidate,
        decision,
        reg=future_registry,
        available_tools=(
            "future_tool",
        ),
    )

    assert (
        assessment.disposition
        == HandoffDisposition.REJECTED
    )

    assert (
        "permission metadata"
        in assessment.reason
    )
