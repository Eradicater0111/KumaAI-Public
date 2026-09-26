from __future__ import annotations

import unittest
import hashlib
from types import SimpleNamespace
from unittest.mock import patch

from app.agent.goal_plan import GoalStep
from app.agent.mission_service import MissionService
from app.vision.gui_objective_verifier import (
    GuiObjectiveVerificationResult,
)

from app.vision.gui_target_verifier import (
    GUI_TARGET_ATTESTATIONS,
    GuiTargetVerificationResult,
    TARGET_STATUS_SATISFIED,
    TARGET_STATUS_UNKNOWN,
)

from app.agent.gui_action_grounding import (
    gui_tool_names_for_capabilities,
    validate_planned_tool_binding,
    validate_runtime_gui_tool_binding,
)


class FakeCapabilityRegistry:

    def __init__(self):
        self.mapping = {
            "mouse_control": [
                "move_mouse",
                "click",
                "click_vision",
            ],
            "keyboard_control": [
                "type_text",
                "press_key",
            ],
            "screen_navigation": [
                "scroll",
            ],
            "screen_vision": [
                "screenshot_screen",
                "analyze_screen",
            ],
            "filesystem": [
                "list_files",
                "open_file",
            ],
        }

    def tools_for(
        self,
        capability,
    ):
        return list(
            self.mapping.get(
                capability,
                [],
            )
        )


class RecordingExecutor:

    def __init__(
        self,
    ):
        self.calls = []

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
            result="ACTION_OK",
            error="",
        )


class MissionBoundaryKuma:

    def __init__(
        self,
        registry,
    ):
        self.model = "test-model"
        self.capability_registry = registry

        self.tool_registry = {
            "move_mouse": lambda x, y, duration=0.15: None,
            "click": lambda x, y, button="left", clicks=1: None,
            "click_vision": (
                lambda x, y, observation_id,
                button="left", clicks=1: None
            ),
        }

        self.executor = (
            RecordingExecutor()
        )

    @staticmethod
    def normalize_tool_arguments(
        _user_message,
        _tool_name,
        arguments,
    ):
        return dict(
            arguments
        )

    @staticmethod
    def validate_tool_arguments(
        _tool_name,
        _arguments,
    ):
        return True, ""

    @staticmethod
    def request_confirmation(
        _tool_name,
        _arguments,
    ):
        return False


class SatisfiedGuiVerifier:

    def verify_current_screen(
        self,
        **_kwargs,
    ):
        return GuiObjectiveVerificationResult(
            known=True,
            satisfied=True,
            summary=(
                "Expected GUI state is visible."
            ),
            evidence=(
                "The target state is visibly present."
            ),
        )


class FixedTargetVerifier:

    def __init__(
        self,
        result,
    ):
        self.result = result
        self.calls = []

    def verify(
        self,
        **kwargs,
    ):
        self.calls.append(
            dict(kwargs)
        )

        return self.result


def runtime_tool_response(
    tool_name,
    arguments,
):
    return SimpleNamespace(
        message=SimpleNamespace(
            tool_calls=[
                SimpleNamespace(
                    function=SimpleNamespace(
                        name=tool_name,
                        arguments=dict(
                            arguments
                        ),
                    )
                )
            ]
        )
    )


class TestMissionServiceGuiGrounding(
    unittest.TestCase
):

    def setUp(
        self,
    ):
        GUI_TARGET_ATTESTATIONS.clear()

        self.registry = (
            FakeCapabilityRegistry()
        )

        self.kuma = MissionBoundaryKuma(
            self.registry
        )

        self.service = MissionService(
            self.kuma
        )

        self.service.gui_objective_verifier = (
            SatisfiedGuiVerifier()
        )

    def tearDown(
        self,
    ):
        GUI_TARGET_ATTESTATIONS.clear()

    def test_runtime_gui_tool_substitution_never_reaches_executor(
        self
    ):
        with patch(
            "app.agent.mission_service.chat",
            return_value=runtime_tool_response(
                "click",
                {
                    "x": 100,
                    "y": 200,
                },
            ),
        ):
            result = (
                self.service._execute_single_mission_step(
                    step_id="step-substitute",
                    objective=(
                        "Click the visible target using the "
                        "trusted screen observation."
                    ),
                    success_criteria=[
                        "The target opens.",
                    ],
                    verification_requirements=[
                        "Verify the opened state visually.",
                    ],
                    required_capabilities=[
                        "mouse_control",
                    ],
                    planned_tool="click_vision",
                    gui_authority="explicit_goal",
                )
            )

        self.assertFalse(
            result.success
        )

        self.assertFalse(
            result.verified
        )

        self.assertEqual(
            result.recovery_action,
            "escalate",
        )

        self.assertIn(
            "does not match",
            result.error,
        )

        self.assertEqual(
            self.kuma.executor.calls,
            [],
        )

    def test_runtime_gui_argument_substitution_never_reaches_executor(
        self
    ):
        with patch(
            "app.agent.mission_service.chat",
            return_value=runtime_tool_response(
                "click",
                {
                    "x": 300,
                    "y": 400,
                },
            ),
        ), patch.object(
            self.kuma,
            "request_confirmation",
            return_value=False,
        ) as mock_confirmation:

            result = (
                self.service._execute_single_mission_step(
                    step_id="step-argument-substitution",
                    objective=(
                        "Click the approved coordinate."
                    ),
                    success_criteria=[
                        "The approved coordinate is clicked.",
                    ],
                    verification_requirements=[
                        "Verify the intended GUI outcome.",
                    ],
                    required_capabilities=[
                        "mouse_control",
                    ],
                    planned_tool="click",
                    gui_authority="explicit_goal",
                    gui_authority_goal=(
                        "Click at 100, 200."
                    ),
                )
            )

        self.assertFalse(
            result.success
        )

        self.assertFalse(
            result.verified
        )

        self.assertEqual(
            result.recovery_action,
            "escalate",
        )

        self.assertIn(
            "not grounded",
            result.error,
        )

        # Argument substitution must stop before physical
        # execution.
        self.assertEqual(
            self.kuma.executor.calls,
            [],
        )

        # The exact changed argument set was presented to
        # the human confirmation boundary once.
        mock_confirmation.assert_called_once()

        confirmation_tool, confirmation_args = (
            mock_confirmation.call_args.args
        )

        self.assertEqual(
            confirmation_tool,
            "mission_gui_argument_authority",
        )

        self.assertEqual(
            confirmation_args[
                "authority_scope"
            ],
            "exact_normalized_gui_arguments",
        )

        self.assertEqual(
            confirmation_args[
                "planned_tool"
            ],
            "click",
        )

        self.assertEqual(
            confirmation_args[
                "arguments"
            ][
                "x"
            ],
            300,
        )

        self.assertEqual(
            confirmation_args[
                "arguments"
            ][
                "y"
            ],
            400,
        )

    def test_satisfied_semantic_vision_target_reaches_executor(
        self
    ):
        target_result = GuiTargetVerificationResult(
            status=TARGET_STATUS_SATISFIED,
            summary="Settings target matched.",
            evidence="Marker is on Settings.",
            observation_id="obs-fresh",
            x=250,
            y=179,
            goal_sha256=hashlib.sha256(b"Click Settings.").hexdigest(),
            image_sha256=hashlib.sha256(b"verified pixels").hexdigest(),
            target_region_sha256=hashlib.sha256(b"verified region").hexdigest(),
        )

        target_verifier = FixedTargetVerifier(
            target_result
        )

        self.service.gui_target_verifier = (
            target_verifier
        )

        with patch(
            "app.agent.mission_service.chat",
            return_value=runtime_tool_response(
                "click_vision",
                {
                    "x": 100,
                    "y": 200,
                    "observation_id": "obs-1",
                },
            ),
        ), patch(
            "app.agent.gui_perception_refresh."
            "refresh_structured_ui_screen_context",
            return_value=SimpleNamespace(
                available=True,
                corroboration=SimpleNamespace(
                    original_observation=object(),
                    original_binding=object(),
                    fresh_observation=object(),
                    fresh_binding=object(),
                    fresh_screen_observation_id=(
                        "obs-fresh"
                    ),
                ),
            ),
        ), patch(
            "app.agent.gui_target_point_derivation."
            "derive_correlated_structured_ui_target_point",
            return_value=SimpleNamespace(
                matched=True,
                screen_observation_id=(
                    "obs-fresh"
                ),
                vision_point=(
                    250,
                    179,
                ),
            ),
        ), patch(
            "app.agent.gui_target_evidence_producer."
            "produce_structured_ui_visual_target_evidence",
            side_effect=lambda *args: SimpleNamespace(
                issued=True,
                production=SimpleNamespace(
                    visual_verification=args[-2],
                ),
            ),
        ), patch(
            "app.agent.gui_target_evidence_consumption."
            "consume_structured_ui_visual_target_evidence",
            side_effect=lambda visual, **kwargs: (
                SimpleNamespace(
                    matched=True,
                    consumption=SimpleNamespace(
                        visual_verification=visual,
                    ),
                )
            ),
        ), patch.object(
            self.service,
            "_revalidate_vision_click_desktop_context",
            return_value=(True, ""),
        ) as desktop_context_gate, patch.object(
            self.kuma,
            "request_confirmation",
            wraps=self.kuma.request_confirmation,
        ) as mock_confirmation:

            result = (
                self.service._execute_single_mission_step(
                    step_id="step-semantic-match",
                    objective=(
                        "Click the Settings target."
                    ),
                    success_criteria=[
                        "The Settings panel is visible.",
                    ],
                    verification_requirements=[
                        "Verify Settings visually.",
                    ],
                    required_capabilities=[
                        "mouse_control",
                    ],
                    planned_tool="click_vision",
                    gui_target_intent={
                        "role": "AXButton",
                        "text": "Settings",
                        "require_enabled": True,
                        "require_positive_area": True,
                    },
                    gui_authority="explicit_goal",
                    gui_authority_goal=(
                        "Click Settings."
                    ),
                )
            )

        self.assertTrue(
            result.success,
            result.error,
        )

        self.assertTrue(
            result.verified
        )

        self.assertEqual(
            len(
                self.kuma.executor.calls
            ),
            1,
        )

        self.assertEqual(
            self.kuma.executor.calls[0][0],
            "click_vision",
        )

        self.assertEqual(
            len(
                target_verifier.calls
            ),
            1,
        )

        self.assertEqual(
            target_verifier.calls[0],
            {
                "goal": "Click Settings.",
                "observation_id": "obs-fresh",
                "x": 250,
                "y": 179,
            },
        )

        desktop_context_gate.assert_called_once_with(
            "obs-fresh"
        )

        self.assertEqual(
            self.kuma.executor.calls[0][1]["x"],
            250,
        )

        self.assertEqual(
            self.kuma.executor.calls[0][1]["y"],
            179,
        )

        self.assertEqual(
            self.kuma.executor.calls[0][1][
                "observation_id"
            ],
            "obs-fresh",
        )

        # Ordinary semantic single-left click should not
        # need raw-coordinate confirmation.
        mock_confirmation.assert_not_called()

        # Fake executor does not consume the physical
        # attestation, so MissionService must clean it.
        with self.assertRaises(
            ValueError
        ):
            GUI_TARGET_ATTESTATIONS.claim(
                observation_id="obs-fresh",
                x=250,
                y=179,
                button="left",
                clicks=1,
            )

    def test_unknown_semantic_vision_target_never_reaches_executor(
        self
    ):
        target_result = GuiTargetVerificationResult(
            status=TARGET_STATUS_UNKNOWN,
            summary="Target identity is ambiguous.",
            evidence="Marker may be near multiple controls.",
            observation_id="obs-fresh",
            x=250,
            y=179,
            goal_sha256=hashlib.sha256(b"Click Settings.").hexdigest(),
            image_sha256=hashlib.sha256(b"verified pixels").hexdigest(),
            target_region_sha256=hashlib.sha256(b"verified region").hexdigest(),
        )

        target_verifier = FixedTargetVerifier(
            target_result
        )

        self.service.gui_target_verifier = (
            target_verifier
        )

        with patch(
            "app.agent.mission_service.chat",
            return_value=runtime_tool_response(
                "click_vision",
                {
                    "x": 100,
                    "y": 200,
                    "observation_id": "obs-1",
                },
            ),
        ), patch(
            "app.agent.gui_perception_refresh."
            "refresh_structured_ui_screen_context",
            return_value=SimpleNamespace(
                available=True,
                corroboration=SimpleNamespace(
                    original_observation=object(),
                    original_binding=object(),
                    fresh_observation=object(),
                    fresh_binding=object(),
                    fresh_screen_observation_id=(
                        "obs-fresh"
                    ),
                ),
            ),
        ), patch(
            "app.agent.gui_target_point_derivation."
            "derive_correlated_structured_ui_target_point",
            return_value=SimpleNamespace(
                matched=True,
                screen_observation_id=(
                    "obs-fresh"
                ),
                vision_point=(
                    250,
                    179,
                ),
            ),
        ), patch(
            "app.agent.gui_target_evidence_producer."
            "produce_structured_ui_visual_target_evidence",
            side_effect=lambda *args: SimpleNamespace(
                issued=True,
                production=SimpleNamespace(
                    visual_verification=args[-2],
                ),
            ),
        ), patch(
            "app.agent.gui_target_evidence_consumption."
            "consume_structured_ui_visual_target_evidence",
            side_effect=lambda visual, **kwargs: (
                SimpleNamespace(
                    matched=True,
                    consumption=SimpleNamespace(
                        visual_verification=visual,
                    ),
                )
            ),
        ):

            result = (
                self.service._execute_single_mission_step(
                    step_id="step-semantic-unknown",
                    objective=(
                        "Click the Settings target."
                    ),
                    success_criteria=[
                        "The Settings panel is visible.",
                    ],
                    verification_requirements=[
                        "Verify Settings visually.",
                    ],
                    required_capabilities=[
                        "mouse_control",
                    ],
                    planned_tool="click_vision",
                    gui_target_intent={
                        "role": "AXButton",
                        "text": "Settings",
                        "require_enabled": True,
                        "require_positive_area": True,
                    },
                    gui_authority="explicit_goal",
                    gui_authority_goal=(
                        "Click Settings."
                    ),
                )
            )

        self.assertFalse(
            result.success
        )

        self.assertFalse(
            result.verified
        )

        self.assertEqual(
            result.recovery_action,
            "escalate",
        )

        self.assertIn(
            "semantic target verification failed",
            result.error,
        )

        self.assertIn(
            "visual_verification_unavailable",
            result.error,
        )

        self.assertEqual(
            self.kuma.executor.calls,
            [],
        )

        self.assertEqual(
            len(
                target_verifier.calls
            ),
            1,
        )


    def test_exact_planner_bound_gui_tool_reaches_executor(
        self
    ):
        with patch(
            "app.agent.mission_service.chat",
            return_value=runtime_tool_response(
                "click",
                {
                    "x": 100,
                    "y": 200,
                },
            ),
        ):
            result = (
                self.service._execute_single_mission_step(
                    step_id="step-match",
                    objective=(
                        "Click the Settings control."
                    ),
                    success_criteria=[
                        "The Settings panel is visible.",
                    ],
                    verification_requirements=[
                        "Verify the Settings panel visually.",
                    ],
                    required_capabilities=[
                        "mouse_control",
                    ],
                    planned_tool="click",
                    gui_authority="explicit_goal",
                    gui_authority_goal="Click at 100, 200.",
                )
            )

        self.assertTrue(
            result.success,
            result.error,
        )

        self.assertTrue(
            result.verified
        )

        self.assertTrue(
            result.completed
        )

        self.assertEqual(
            len(
                self.kuma.executor.calls
            ),
            1,
        )

        executed_tool = (
            self.kuma.executor.calls[0][0]
        )

        self.assertEqual(
            executed_tool,
            "click",
        )


class TestGuiActionGrounding(
    unittest.TestCase
):

    def setUp(self):
        self.registry = (
            FakeCapabilityRegistry()
        )

    def test_gui_capability_requires_planned_tool(
        self
    ):
        valid, _ = (
            validate_planned_tool_binding(
                self.registry,
                ["mouse_control"],
                "",
            )
        )

        self.assertFalse(valid)

    def test_valid_gui_binding_is_accepted(
        self
    ):
        valid, error = (
            validate_planned_tool_binding(
                self.registry,
                ["mouse_control"],
                "click_vision",
            )
        )

        self.assertTrue(
            valid,
            error,
        )

    def test_gui_tool_outside_capability_is_rejected(
        self
    ):
        valid, _ = (
            validate_planned_tool_binding(
                self.registry,
                ["keyboard_control"],
                "click",
            )
        )

        self.assertFalse(valid)

    def test_runtime_substitution_is_rejected(
        self
    ):
        valid, error = (
            validate_runtime_gui_tool_binding(
                self.registry,
                ["mouse_control"],
                "click_vision",
                "click",
            )
        )

        self.assertFalse(valid)

        self.assertIn(
            "does not match",
            error,
        )

    def test_runtime_exact_match_is_accepted(
        self
    ):
        valid, error = (
            validate_runtime_gui_tool_binding(
                self.registry,
                ["mouse_control"],
                "click_vision",
                "click_vision",
            )
        )

        self.assertTrue(
            valid,
            error,
        )

    def test_non_gui_capability_needs_no_binding(
        self
    ):
        valid, error = (
            validate_planned_tool_binding(
                self.registry,
                ["filesystem"],
                "",
            )
        )

        self.assertTrue(
            valid,
            error,
        )

    def test_gui_resolution_is_deterministic(
        self
    ):
        tools = (
            gui_tool_names_for_capabilities(
                self.registry,
                ["mouse_control"],
            )
        )

        self.assertEqual(
            tools,
            frozenset(
                {
                    "move_mouse",
                    "click",
                    "click_vision",
                }
            ),
        )

    def test_goal_step_roundtrip_preserves_planned_tool(
        self
    ):
        original = GoalStep(
            id="step-1",
            objective="Click Settings.",
            required_capabilities=[
                "mouse_control"
            ],
            planned_tool="click_vision",
        )

        restored = GoalStep.from_dict(
            original.to_dict()
        )

        self.assertEqual(
            restored.planned_tool,
            "click_vision",
        )


if __name__ == "__main__":
    unittest.main()
