import hashlib
import inspect
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from app.agent.mission_service import (
    MissionService,
)
from app.agent.tool_result import (
    ToolResult,
)
from app.vision.gui_target_verifier import (
    GUI_SEMANTIC_TARGET_ATTESTATIONS,
    GUI_TARGET_ATTESTATIONS,
    GuiTargetVerificationResult,
)


GOAL = "Move the cursor to Settings."

MODEL_ARGUMENTS = {
    "observation_id": "obs-old",
    "x": 100,
    "y": 200,
}

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


class MoveCapabilityRegistry:

    def tools_for(
        self,
        capability,
    ):
        if capability == "mouse_control":
            return (
                "move_mouse",
                "move_mouse_vision",
                "click",
                "click_vision",
            )

        return ()


class RecordingExecutor:

    def __init__(self):
        self.calls = []
        self.tool_registry = {}

    def execute(
        self,
        *,
        tool_name,
        arguments,
        approved=False,
    ):
        self.calls.append(
            (
                tool_name,
                dict(arguments),
                approved,
            )
        )

        return SimpleNamespace(
            success=True,
            result=ToolResult.ok(
                "trusted move issued"
            ),
            error="",
        )


class MissionKuma:

    def __init__(self):

        self.model = "test-model"

        self.capability_registry = (
            MoveCapabilityRegistry()
        )

        self.tool_registry = {
            "move_mouse": (
                lambda x, y, duration=0.15:
                None
            ),
            "move_mouse_vision": (
                lambda x, y, observation_id, duration=0.15:
                None
            ),
            "click": (
                lambda x, y, button="left", clicks=1:
                None
            ),
            "click_vision": (
                lambda x, y, observation_id,
                button="left", clicks=1:
                None
            ),
        }

        self.executor = RecordingExecutor()

        self.executor.tool_registry = (
            self.tool_registry
        )

        self.request_confirmation = Mock(
            return_value=False
        )

    @staticmethod
    def normalize_tool_arguments(
        user_message,
        tool_name,
        arguments,
    ):
        return dict(
            arguments
        )

    def validate_tool_arguments(
        self,
        tool_name,
        arguments,
    ):
        function = self.tool_registry.get(
            tool_name
        )

        if function is None:
            return (
                False,
                f"Unknown tool: {tool_name}",
            )

        try:
            inspect.signature(
                function
            ).bind(
                **arguments
            )
        except Exception as error:
            return (
                False,
                str(error),
            )

        return True, ""


def runtime_response(
    arguments,
):
    return SimpleNamespace(
        message=SimpleNamespace(
            tool_calls=[
                SimpleNamespace(
                    function=SimpleNamespace(
                        name=(
                            "move_mouse_vision"
                        ),
                        arguments=dict(
                            arguments
                        ),
                    )
                )
            ]
        )
    )


def matching_result():

    return GuiTargetVerificationResult(
        status="satisfied",
        summary="Target matched.",
        evidence=(
            "Marker is on Settings."
        ),
        observation_id=(
            FRESH_ARGUMENTS[
                "observation_id"
            ]
        ),
        x=FRESH_ARGUMENTS["x"],
        y=FRESH_ARGUMENTS["y"],
        goal_sha256=hashlib.sha256(
            GOAL.encode()
        ).hexdigest(),
        image_sha256=hashlib.sha256(
            b"fresh verified pixels"
        ).hexdigest(),
        target_region_sha256=(
            hashlib.sha256(
                b"fresh target region"
            ).hexdigest()
        ),
    )


def refresh_result():

    return SimpleNamespace(
        available=True,
        corroboration=SimpleNamespace(
            original_observation=object(),
            original_binding=object(),
            fresh_observation=object(),
            fresh_binding=object(),
            fresh_screen_observation_id=(
                FRESH_ARGUMENTS[
                    "observation_id"
                ]
            ),
        ),
    )


def derived_point(
    *_args,
    **_kwargs,
):

    return SimpleNamespace(
        matched=True,
        screen_observation_id=(
            FRESH_ARGUMENTS[
                "observation_id"
            ]
        ),
        vision_point=(
            FRESH_ARGUMENTS["x"],
            FRESH_ARGUMENTS["y"],
        ),
    )


def issued_production(
    *args,
):

    visual = args[-2]

    return SimpleNamespace(
        issued=True,
        production=SimpleNamespace(
            visual_verification=visual,
        ),
    )


def matched_consumption(
    visual,
    **kwargs,
):

    return SimpleNamespace(
        matched=True,
        consumption=SimpleNamespace(
            visual_verification=visual,
        ),
    )


@pytest.fixture(
    autouse=True
)
def clear_attestations():

    GUI_SEMANTIC_TARGET_ATTESTATIONS.clear()
    GUI_TARGET_ATTESTATIONS.clear()

    yield

    GUI_SEMANTIC_TARGET_ATTESTATIONS.clear()
    GUI_TARGET_ATTESTATIONS.clear()


def run_move(
    service,
    *,
    arguments=None,
    continuation_replay_context=None,
):

    arguments = (
        dict(MODEL_ARGUMENTS)
        if arguments is None
        else dict(arguments)
    )

    with (
        patch(
            "app.agent.mission_service.chat",
            return_value=(
                runtime_response(
                    arguments
                )
            ),
        ),
        patch(
            "app.agent.gui_perception_refresh."
            "refresh_structured_ui_screen_context",
            return_value=(
                refresh_result()
            ),
        ),
        patch(
            "app.agent.gui_target_point_derivation."
            "derive_correlated_structured_ui_target_point",
            new=derived_point,
        ),
        patch(
            "app.agent.gui_target_evidence_producer."
            "produce_structured_ui_visual_target_evidence",
            side_effect=(
                issued_production
            ),
        ),
        patch(
            "app.agent.gui_target_evidence_consumption."
            "consume_structured_ui_visual_target_evidence",
            side_effect=(
                matched_consumption
            ),
        ),
        patch(
            "app.agent.mission_service."
            "verify_result",
            return_value=True,
        ),
        patch(
            "app.agent.mission_service."
            "verification_report",
            return_value=(
                "trusted move verified"
            ),
        ),
    ):

        return (
            service._execute_single_mission_step(
                step_id=(
                    "trusted-pointer-move"
                ),
                objective=GOAL,
                success_criteria=[
                    "Pointer reaches Settings."
                ],
                verification_requirements=[],
                required_capabilities=[
                    "mouse_control"
                ],
                planned_tool=(
                    "move_mouse_vision"
                ),
                gui_target_intent=dict(
                    TARGET_INTENT
                ),
                gui_authority=(
                    "explicit_goal"
                ),
                gui_authority_goal=GOAL,
                continuation_replay_context=(
                    continuation_replay_context
                ),
            )
        )


def test_mission_rebinds_model_point_and_issues_target_only_attestation():

    kuma = MissionKuma()

    service = MissionService(
        kuma
    )

    service.gui_target_verifier = Mock()

    verified = matching_result()

    service.gui_target_verifier.verify.return_value = (
        verified
    )

    with (
        patch.object(
            service,
            "_revalidate_vision_move_desktop_context",
            return_value=(
                True,
                "",
            ),
        ) as desktop_gate,
        patch.object(
            GUI_SEMANTIC_TARGET_ATTESTATIONS,
            "issue",
            wraps=(
                GUI_SEMANTIC_TARGET_ATTESTATIONS.issue
            ),
        ) as semantic_issue,
        patch.object(
            GUI_TARGET_ATTESTATIONS,
            "issue",
            wraps=(
                GUI_TARGET_ATTESTATIONS.issue
            ),
        ) as click_issue,
    ):

        result = run_move(
            service
        )

    assert result.success, result.error
    assert result.verified

    assert len(
        kuma.executor.calls
    ) == 1

    tool_name, arguments, approved = (
        kuma.executor.calls[0]
    )

    assert (
        tool_name
        == "move_mouse_vision"
    )

    assert (
        arguments["observation_id"]
        == FRESH_ARGUMENTS[
            "observation_id"
        ]
    )

    assert (
        arguments["x"],
        arguments["y"],
    ) == (
        FRESH_ARGUMENTS["x"],
        FRESH_ARGUMENTS["y"],
    )

    assert (
        arguments["x"],
        arguments["y"],
    ) != (
        MODEL_ARGUMENTS["x"],
        MODEL_ARGUMENTS["y"],
    )

    assert approved is False

    service.gui_target_verifier.verify.assert_called_once_with(
        goal=GOAL,
        observation_id=(
            FRESH_ARGUMENTS[
                "observation_id"
            ]
        ),
        x=FRESH_ARGUMENTS["x"],
        y=FRESH_ARGUMENTS["y"],
    )

    desktop_gate.assert_called_once_with(
        FRESH_ARGUMENTS[
            "observation_id"
        ]
    )

    semantic_issue.assert_called_once_with(
        result=verified,
    )

    click_issue.assert_not_called()

    kuma.request_confirmation.assert_not_called()

    # Fake executor does not consume the physical receipt.
    # MissionService must clear it in finally.
    with pytest.raises(
        ValueError,
        match=(
            "No semantic target "
            "attestation is active"
        ),
    ):
        GUI_SEMANTIC_TARGET_ATTESTATIONS.claim(
            observation_id=(
                FRESH_ARGUMENTS[
                    "observation_id"
                ]
            ),
            x=FRESH_ARGUMENTS["x"],
            y=FRESH_ARGUMENTS["y"],
        )


def test_nondefault_duration_reaches_exact_confirmation_boundary():

    kuma = MissionKuma()

    kuma.request_confirmation.return_value = (
        False
    )

    service = MissionService(
        kuma
    )

    service.gui_target_verifier = Mock()

    service.gui_target_verifier.verify.return_value = (
        matching_result()
    )

    proposed = {
        **MODEL_ARGUMENTS,
        "duration": 0.5,
    }

    with patch.object(
        service,
        "_revalidate_vision_move_desktop_context",
    ) as desktop_gate:

        result = run_move(
            service,
            arguments=proposed,
        )

    assert not result.success

    assert (
        "were not grounded"
        in result.error
    )

    assert (
        "not explicitly approved"
        in result.error
    )

    kuma.request_confirmation.assert_called_once()

    desktop_gate.assert_not_called()

    assert kuma.executor.calls == []


def test_executable_replay_guard_uses_fresh_move_target():

    kuma = MissionKuma()

    service = MissionService(
        kuma
    )

    service.gui_target_verifier = Mock()

    service.gui_target_verifier.verify.return_value = (
        matching_result()
    )

    replay = {
        "known": True,
        "tool": "move_mouse_vision",
        "arguments": dict(
            FRESH_ARGUMENTS
        ),
    }

    with (
        patch.object(
            service,
            "_revalidate_vision_move_desktop_context",
        ) as desktop_gate,
        patch.object(
            GUI_SEMANTIC_TARGET_ATTESTATIONS,
            "issue",
        ) as issue,
    ):

        result = run_move(
            service,
            continuation_replay_context=replay,
        )

    assert not result.success

    assert (
        "exactly replay"
        in result.error
    )

    assert (
        result.arguments
        == FRESH_ARGUMENTS
    )

    desktop_gate.assert_not_called()
    issue.assert_not_called()

    assert kuma.executor.calls == []
