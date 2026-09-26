from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest.mock import patch

from app.agent.goal_plan import (
    GoalStep,
)

from app.agent.mission_service import (
    MissionService,
)

from app.vision.gui_objective_verifier import (
    GuiObjectiveVerificationResult,
)


class FakeCapabilityRegistry:

    def __init__(
        self,
        mapping,
    ):
        self.mapping = dict(
            mapping
        )

    def tools_for(
        self,
        capability,
    ):
        return tuple(
            self.mapping.get(
                capability,
                (),
            )
        )


class FakeExecutor:

    def __init__(
        self,
        *,
        success=True,
        result="action issued",
        error="",
    ):
        self.success = success
        self.result = result
        self.error = error
        self.calls = []

    def execute(
        self,
        *,
        tool_name,
        arguments,
        approved=False,
    ):
        self.calls.append(
            {
                "tool_name":
                tool_name,
                "arguments":
                dict(arguments),
                "approved":
                approved,
            }
        )

        return SimpleNamespace(
            success=self.success,
            result=self.result,
            error=self.error,
        )


class FakeGuiVerifier:

    def __init__(
        self,
        result,
    ):
        self.result = result
        self.calls = []

    def verify_current_screen(
        self,
        **kwargs,
    ):
        self.calls.append(
            dict(kwargs)
        )

        return self.result


class FakeKuma:

    def __init__(
        self,
        *,
        tool_name="click",
        capability="mouse_control",
    ):
        self.model = "test-model"

        self.tool_registry = {
            tool_name:
            lambda **_kwargs:
            None,
        }

        self.capability_registry = (
            FakeCapabilityRegistry(
                {
                    capability: (
                        tool_name,
                    )
                }
            )
        )

        self.executor = FakeExecutor()

    def emit_status(
        self,
        _message,
    ):
        return None

    @staticmethod
    def normalize_tool_arguments(
        _objective,
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


def model_response(
    *,
    tool_name,
    arguments,
):
    return SimpleNamespace(
        message=SimpleNamespace(
            tool_calls=[
                SimpleNamespace(
                    function=(
                        SimpleNamespace(
                            name=tool_name,
                            arguments=dict(
                                arguments
                            ),
                        )
                    )
                )
            ]
        )
    )


class TestGuiMissionVerification(
    unittest.TestCase
):

    def make_step(
        self,
        *,
        capability="mouse_control",
    ):
        return GoalStep(
            id="step-1",
            objective=(
                "Open the Settings panel."
            ),
            success_criteria=[
                "The Settings panel is visible.",
            ],
            required_capabilities=[
                capability,
            ],
            planned_tool=(
                "click"
                if capability == "mouse_control"
                else ""
            ),
            gui_authority=(
                "explicit_goal"
                if capability == "mouse_control"
                else ""
            ),
            gui_authority_goal=(
                "Click at 100, 200."
                if capability == "mouse_control"
                else ""
            ),
            verification_requirements=[
                "Verify the Settings panel "
                "visually after the action.",
            ],
        )

    def test_gui_step_completes_only_after_visual_satisfaction(
        self
    ):
        kuma = FakeKuma()

        service = MissionService(
            kuma
        )

        gui_verifier = FakeGuiVerifier(
            GuiObjectiveVerificationResult(
                known=True,
                satisfied=True,
                summary=(
                    "Settings panel is visible."
                ),
                evidence=(
                    "Settings heading is visible."
                ),
            )
        )

        service.gui_objective_verifier = (
            gui_verifier
        )

        with patch(
            "app.agent.mission_service.chat",
            return_value=(
                model_response(
                    tool_name="click",
                    arguments={
                        "x": 100,
                        "y": 200,
                    },
                )
            ),
        ):
            result = (
                service.execute_mission_step(
                    self.make_step()
                )
            )

        self.assertTrue(
            result.completed
        )

        self.assertEqual(
            len(gui_verifier.calls),
            1,
        )

        call = (
            gui_verifier.calls[0]
        )

        self.assertEqual(
            call["success_criteria"],
            [
                "The Settings panel is visible.",
            ],
        )

        self.assertEqual(
            call[
                "verification_requirements"
            ],
            [
                "Verify the Settings panel "
                "visually after the action.",
            ],
        )

        self.assertIn(
            "Settings heading is visible.",
            result.verification,
        )

    def test_unknown_gui_outcome_never_completes_step(
        self
    ):
        kuma = FakeKuma()

        service = MissionService(
            kuma
        )

        service.gui_objective_verifier = (
            FakeGuiVerifier(
                GuiObjectiveVerificationResult(
                    known=False,
                    satisfied=None,
                    summary=(
                        "The expected state cannot "
                        "be determined visually."
                    ),
                    evidence="",
                )
            )
        )

        with patch(
            "app.agent.mission_service.chat",
            return_value=(
                model_response(
                    tool_name="click",
                    arguments={
                        "x": 100,
                        "y": 200,
                    },
                )
            ),
        ):
            result = (
                service.execute_mission_step(
                    self.make_step()
                )
            )

        self.assertFalse(
            result.completed
        )

        self.assertFalse(
            result.verified
        )

        self.assertEqual(
            result.recovery_action,
            "escalate",
        )

    def test_visibly_unsatisfied_gui_outcome_never_completes_step(
        self
    ):
        kuma = FakeKuma()

        service = MissionService(
            kuma
        )

        service.gui_objective_verifier = (
            FakeGuiVerifier(
                GuiObjectiveVerificationResult(
                    known=True,
                    satisfied=False,
                    summary=(
                        "Settings panel is not visible."
                    ),
                    evidence=(
                        "Original page remains visible."
                    ),
                )
            )
        )

        with patch(
            "app.agent.mission_service.chat",
            return_value=(
                model_response(
                    tool_name="click",
                    arguments={
                        "x": 100,
                        "y": 200,
                    },
                )
            ),
        ):
            result = (
                service.execute_mission_step(
                    self.make_step()
                )
            )

        self.assertFalse(
            result.completed
        )

        self.assertEqual(
            result.recovery_action,
            "escalate",
        )

        self.assertIn(
            "Original page remains visible.",
            result.verification,
        )

    def test_non_gui_tool_keeps_action_level_verification(
        self
    ):
        kuma = FakeKuma(
            tool_name="list_files",
            capability="filesystem",
        )

        service = MissionService(
            kuma
        )

        gui_verifier = FakeGuiVerifier(
            GuiObjectiveVerificationResult(
                known=True,
                satisfied=True,
                summary="unused",
                evidence="unused",
            )
        )

        service.gui_objective_verifier = (
            gui_verifier
        )

        step = GoalStep(
            id="step-files",
            objective=(
                "List the files."
            ),
            success_criteria=[
                "A file listing is returned.",
            ],
            required_capabilities=[
                "filesystem",
            ],
            verification_requirements=[
                "Use the tool result.",
            ],
        )

        with patch(
            "app.agent.mission_service.chat",
            return_value=(
                model_response(
                    tool_name="list_files",
                    arguments={},
                )
            ),
        ):
            result = (
                service.execute_mission_step(
                    step
                )
            )

        self.assertTrue(
            result.completed
        )

        self.assertEqual(
            gui_verifier.calls,
            [],
        )

    def test_planner_contract_is_forwarded_to_single_step_boundary(
        self
    ):
        kuma = FakeKuma()

        service = MissionService(
            kuma
        )

        captured = {}

        def fake_single_step(
            **kwargs,
        ):
            captured.update(
                kwargs
            )

            return SimpleNamespace()

        service._execute_single_mission_step = (
            fake_single_step
        )

        step = self.make_step()

        service.execute_mission_step(
            step
        )

        self.assertEqual(
            captured[
                "success_criteria"
            ],
            step.success_criteria,
        )

        self.assertEqual(
            captured[
                "verification_requirements"
            ],
            step.verification_requirements,
        )


if __name__ == "__main__":
    unittest.main()
