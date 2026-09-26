"""Exercise B8K3 dual-sensor evidence at the mission boundary.

The model proposes O0. Trusted runtime corroboration creates O1.
Visual verification, B8J/B8G evidence, desktop revalidation,
attestation, and execution must all bind to O1.
"""

from dataclasses import replace
import hashlib
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from app.agent.mission_service import MissionService
from app.agent.test_gui_action_grounding import (
    FakeCapabilityRegistry,
    MissionBoundaryKuma,
    SatisfiedGuiVerifier,
    runtime_tool_response,
)
from app.vision.gui_target_verifier import (
    GUI_TARGET_ATTESTATIONS,
    GuiTargetVerificationResult,
)


GOAL = "Click Settings."

# O0 is the exact screen observation proposed by the model.
ARGUMENTS = {
    "observation_id": "obs-1",
    "x": 100,
    "y": 200,
}

# O1 is created only by trusted B8K2 runtime corroboration.
FRESH_ARGUMENTS = {
    "observation_id": "obs-fresh",
    "x": 250,
    "y": 179,
}

TARGET_INTENT = {
    "role": "AXButton",
    "text": "Settings",
    "require_enabled": True,
    "require_positive_area": True,
}


def matching_result():
    return GuiTargetVerificationResult(
        status="satisfied",
        summary="Target matched.",
        evidence="Marker is on Settings.",
        **FRESH_ARGUMENTS,
        goal_sha256=hashlib.sha256(
            GOAL.encode()
        ).hexdigest(),
        image_sha256=hashlib.sha256(
            b"verified pixels"
        ).hexdigest(),
        target_region_sha256=hashlib.sha256(
            b"verified region"
        ).hexdigest(),
    )


def fresh_refresh_result():
    return SimpleNamespace(
        available=True,
        corroboration=SimpleNamespace(
            original_observation=object(),
            original_binding=object(),
            fresh_observation=object(),
            fresh_binding=object(),
            fresh_screen_observation_id=(
                FRESH_ARGUMENTS["observation_id"]
            ),
        ),
    )


def issued_production(*args):
    visual = args[-2]

    return SimpleNamespace(
        issued=True,
        production=SimpleNamespace(
            visual_verification=visual,
        ),
    )


def matched_consumption(visual, **kwargs):
    return SimpleNamespace(
        matched=True,
        consumption=SimpleNamespace(
            visual_verification=visual,
        ),
    )


def _matched_k4_point_derivation(
    *_args,
    **_kwargs,
):
    return SimpleNamespace(
        matched=True,
        screen_observation_id=(
            "obs-fresh"
        ),
        vision_point=(
            250,
            179,
        ),
    )


@patch(
    "app.agent.gui_target_point_derivation."
    "derive_correlated_structured_ui_target_point",
    new=_matched_k4_point_derivation,
)
def run_step(
    service,
    *,
    continuation_replay_context=None,
):
    # We mock only the read-only evidence acquisition/composition
    # surrounding safe_verify_gui_target. The real B8K3 helper and
    # the real safe verifier contract still execute.
    with patch(
        "app.agent.mission_service.chat",
        return_value=runtime_tool_response(
            "click_vision",
            ARGUMENTS,
        ),
    ), patch(
        "app.agent.gui_perception_refresh."
        "refresh_structured_ui_screen_context",
        return_value=fresh_refresh_result(),
    ), patch(
        "app.agent.gui_target_evidence_producer."
        "produce_structured_ui_visual_target_evidence",
        side_effect=issued_production,
    ), patch(
        "app.agent.gui_target_evidence_consumption."
        "consume_structured_ui_visual_target_evidence",
        side_effect=matched_consumption,
    ):
        return service._execute_single_mission_step(
            step_id="target-contract",
            objective=GOAL,
            success_criteria=[
                "Settings is visible.",
            ],
            verification_requirements=[
                "Verify Settings visually.",
            ],
            required_capabilities=[
                "mouse_control",
            ],
            planned_tool="click_vision",
            gui_target_intent=dict(
                TARGET_INTENT
            ),
            gui_authority="explicit_goal",
            gui_authority_goal=GOAL,
            continuation_replay_context=(
                continuation_replay_context
            ),
        )


@pytest.fixture
def service():
    GUI_TARGET_ATTESTATIONS.clear()

    kuma = MissionBoundaryKuma(
        FakeCapabilityRegistry()
    )

    kuma.request_confirmation = Mock(
        return_value=True
    )

    service = MissionService(kuma)

    service.gui_objective_verifier = (
        SatisfiedGuiVerifier()
    )

    service.gui_target_verifier = Mock()

    yield service

    GUI_TARGET_ATTESTATIONS.clear()


@pytest.mark.parametrize(
    "changes",
    [
        {
            "goal_sha256": hashlib.sha256(
                b"Click Delete."
            ).hexdigest()
        },
        {
            "observation_id":
                "previous-observation"
        },
        {"x": 101},
        {"y": 201},
        {"x": 100.0},
        {"y": 200.0},
        {"image_sha256": ""},
        {
            "image_sha256":
                "not-a-sha256-digest"
        },
        {"image_sha256": "z" * 64},
        {"target_region_sha256": ""},
        {
            "target_region_sha256":
                "not-a-sha256-digest"
        },
        {
            "target_region_sha256":
                "z" * 64
        },
        {"summary": None},
        {"evidence": []},
        {"evidence": " "},
        {"status": "probably"},
    ],
)
def test_mismatched_or_malformed_evidence_blocks_before_authority(
    service,
    changes,
):
    service.gui_target_verifier.verify.return_value = (
        replace(
            matching_result(),
            **changes,
        )
    )

    with patch(
        "app.agent.mission_service."
        "GUI_TARGET_ATTESTATIONS.issue"
    ) as issue:
        result = run_step(service)

    assert not result.success
    assert not result.verified
    assert result.recovery_action == "escalate"
    assert service.kuma.executor.calls == []

    service.kuma.request_confirmation.assert_not_called()
    issue.assert_not_called()


@pytest.mark.parametrize(
    "value",
    [
        None,
        {"satisfied": True},
        SimpleNamespace(
            **vars(
                matching_result()
            ),
            satisfied=True,
        ),
    ],
)
def test_invalid_verifier_return_fails_closed(
    service,
    value,
):
    service.gui_target_verifier.verify.return_value = (
        value
    )

    result = run_step(service)

    assert not result.success
    assert result.recovery_action == "escalate"
    assert service.kuma.executor.calls == []

    service.kuma.request_confirmation.assert_not_called()


def test_verifier_exception_becomes_blocked_result(
    service,
):
    service.gui_target_verifier.verify.side_effect = (
        RuntimeError(
            "verifier unavailable"
        )
    )

    result = run_step(service)

    assert not result.success
    assert result.recovery_action == "escalate"
    assert service.kuma.executor.calls == []

    service.kuma.request_confirmation.assert_not_called()


def test_exact_evidence_reaches_execution_without_extra_confirmation(
    service,
):
    service.gui_target_verifier.verify.return_value = (
        matching_result()
    )

    with patch.object(
        service,
        "_revalidate_vision_click_desktop_context",
        return_value=(True, ""),
    ) as desktop_context_gate:

        result = run_step(service)

    assert result.success, result.error
    assert result.verified

    assert len(
        service.kuma.executor.calls
    ) == 1

    execution_call = (
        service.kuma.executor.calls[0]
    )

    assert execution_call[0] == "click_vision"

    arguments = execution_call[1]

    # K4 replaces model x0/y0 with the trusted executable
    # point derived from fresh structured target geometry.
    assert arguments["x"] == FRESH_ARGUMENTS["x"]
    assert arguments["y"] == FRESH_ARGUMENTS["y"]

    # Only observation identity is trusted-runtime rebound.
    assert (
        arguments["observation_id"]
        == FRESH_ARGUMENTS[
            "observation_id"
        ]
    )

    service.gui_target_verifier.verify.assert_called_once_with(
        goal=GOAL,
        observation_id=FRESH_ARGUMENTS[
            "observation_id"
        ],
        x=FRESH_ARGUMENTS["x"],
        y=FRESH_ARGUMENTS["y"],
    )

    desktop_context_gate.assert_called_once_with(
        FRESH_ARGUMENTS[
            "observation_id"
        ]
    )

    service.kuma.request_confirmation.assert_not_called()

    # Fake executor does not consume the physical attestation;
    # MissionService must still clear it after execution.
    with pytest.raises(ValueError):
        GUI_TARGET_ATTESTATIONS.claim(
            **FRESH_ARGUMENTS,
            button="left",
            clicks=1,
        )

def test_rebound_executable_arguments_are_replay_checked(
    service,
):
    """O0 may differ while trusted O1 still exactly replays old execution."""

    service.gui_target_verifier.verify.return_value = (
        matching_result()
    )

    replay_context = {
        "known": True,
        "tool": "click_vision",
        # Previous durable action provenance contains the
        # arguments that actually executed: fresh O1.
        "arguments": dict(
            FRESH_ARGUMENTS
        ),
    }

    with patch.object(
        service,
        "_revalidate_vision_click_desktop_context",
        return_value=(True, ""),
    ) as desktop_context_gate, patch(
        "app.agent.mission_service."
        "GUI_TARGET_ATTESTATIONS.issue"
    ) as issue:

        result = run_step(
            service,
            continuation_replay_context=(
                replay_context
            ),
        )

    assert not result.success
    assert not result.verified

    assert result.recovery_action == "escalate"

    assert (
        "exactly replay"
        in result.error
    )

    # The returned blocked arguments are the executable O1
    # arguments, proving the second guard ran after rebinding.
    assert result.arguments == FRESH_ARGUMENTS

    # B8K4 visual verification happened against O1,x1,y1 exactly once.
    service.gui_target_verifier.verify.assert_called_once_with(
        goal=GOAL,
        observation_id=FRESH_ARGUMENTS[
            "observation_id"
        ],
        x=FRESH_ARGUMENTS["x"],
        y=FRESH_ARGUMENTS["y"],
    )

    # Replay must stop the pipeline before every downstream
    # authority / physical-execution boundary.
    desktop_context_gate.assert_not_called()
    service.kuma.request_confirmation.assert_not_called()
    issue.assert_not_called()

    assert service.kuma.executor.calls == []
