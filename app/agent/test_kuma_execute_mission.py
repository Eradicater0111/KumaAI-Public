import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from types import SimpleNamespace
from unittest.mock import patch

from app.agent.kuma_agent import KumaAgent
import app.memory.memory as memory_module
from app.agent.mission_persistence import (
    MissionPersistence as _RealMissionPersistence,
)
from app.agent.mission_result import (
    MissionExecutionResult,
)


def fake_tool_call(name):
    return SimpleNamespace(
        function=SimpleNamespace(
            name=name,
            arguments={},
        )
    )


def fake_response(name):
    return SimpleNamespace(
        message=SimpleNamespace(
            content="",
            tool_calls=[
                fake_tool_call(name)
            ],
        )
    )


def _make_isolated_kuma_agent(
    test_case,
    **kwargs,
):
    """Construct KumaAgent against one temporary shared SQLite DB."""

    temporary_directory = TemporaryDirectory()

    test_case.addCleanup(
        temporary_directory.cleanup
    )

    db_path = (
        Path(temporary_directory.name)
        / "kuma_memory.db"
    )

    memory_db_patch = patch.object(
        memory_module,
        "DB_PATH",
        db_path,
    )

    memory_db_patch.start()

    test_case.addCleanup(
        memory_db_patch.stop
    )

    mission_persistence_patch = patch(
        "app.agent.mission_service.MissionPersistence",
        side_effect=lambda *args, **factory_kwargs: (
            _RealMissionPersistence(
                db_path=db_path,
            )
        ),
    )

    mission_persistence_patch.start()

    test_case.addCleanup(
        mission_persistence_patch.stop
    )

    return KumaAgent(
        **kwargs,
    )


class TestKumaExecuteMission(unittest.TestCase):

    def test_execute_mission_runs_complete_pipeline(self):

        executed = []

        def first_test():
            executed.append(
                "first_test"
            )
            return "FIRST_OK"

        def second_test():
            executed.append(
                "second_test"
            )
            return "SECOND_OK"

        tools = {
            "first_test": first_test,
            "second_test": second_test,
        }

        kuma = _make_isolated_kuma_agent(
            self,
            model="test-model",
            tool_registry=tools,
        )

        responses = iter(
            [
                fake_response(
                    "first_test"
                ),
                fake_response(
                    "second_test"
                ),
            ]
        )

        def fake_decompose(
            goal,
        ):
            from app.agent.goal_plan import (
                GoalPlan,
                GoalStep,
            )

            plan = GoalPlan(
                goal=goal
            )

            plan.add_step(
                GoalStep(
                    id="first",
                    objective="Perform first action.",
                    required_capabilities=[
                        "step_one_capability"
                    ],
                    success_criteria=[
                        "First action succeeds."
                    ],
                    artifacts=[
                        "first result"
                    ],
                    verification_requirements=[
                        "Verify first action."
                    ],
                )
            )

            plan.add_step(
                GoalStep(
                    id="second",
                    objective="Perform second action.",
                    dependencies=[
                        "first"
                    ],
                    required_capabilities=[
                        "step_two_capability"
                    ],
                    success_criteria=[
                        "Second action succeeds."
                    ],
                    artifacts=[
                        "second result"
                    ],
                    verification_requirements=[
                        "Verify second action."
                    ],
                )
            )

            return plan, None

        kuma.capability_registry.register(
            # use the existing Capability class
            type(
                "Capability",
                (),
                {
                    "name": "step_one_capability",
                    "description": "first",
                    "tools": ("first_test",),
                    "platform": "macos",
                    "risk_level": "normal",
                    "tags": (),
                },
            )()
        )

        kuma.capability_registry.register(
            type(
                "Capability",
                (),
                {
                    "name": "step_two_capability",
                    "description": "second",
                    "tools": ("second_test",),
                    "platform": "macos",
                    "risk_level": "normal",
                    "tags": (),
                },
            )()
        )

        with patch(
            "app.agent.mission_service.GoalDecomposer.decompose",
            side_effect=fake_decompose,
        ), patch(
            "app.agent.mission_service.chat",
            side_effect=lambda **kwargs: next(
                responses
            ),
        ):

            result = kuma.execute_mission(
                "Perform two actions."
            )

        self.assertIsInstance(
            result,
            MissionExecutionResult,
        )

        self.assertTrue(
            result.completed
        )

        self.assertEqual(
            executed,
            [
                "first_test",
                "second_test",
            ],
        )



class TestKumaMissionGuiAuthorityAcceptance(
    unittest.TestCase
):

    def test_unapproved_gui_plan_expansion_stops_before_execution(
        self,
    ):

        executed = []

        def fake_click():
            executed.append(
                "click"
            )
            return "CLICKED"

        kuma = _make_isolated_kuma_agent(
            self,
            model="test-model",
            tool_registry={
                "click": fake_click,
            },
        )

        def fake_decompose(
            goal,
        ):
            from app.agent.goal_plan import (
                GoalPlan,
                GoalStep,
            )

            plan = GoalPlan(
                goal=goal
            )

            plan.add_step(
                GoalStep(
                    id="settings-click",
                    objective=(
                        "Click the Settings control."
                    ),
                    required_capabilities=[
                        "mouse_control"
                    ],
                    planned_tool="click",
                    success_criteria=[
                        "Settings is opened."
                    ],
                    artifacts=[
                        "Settings view"
                    ],
                    verification_requirements=[
                        "Verify Settings is open."
                    ],
                )
            )

            return plan, None

        with patch(
            "app.agent.mission_service.GoalDecomposer.decompose",
            side_effect=fake_decompose,
        ), patch(
            "app.agent.mission_service.chat",
        ) as mock_chat, patch.object(
            kuma,
            "request_confirmation",
            return_value=False,
        ) as mock_confirmation:

            result = kuma.execute_mission(
                "Look at the Settings page."
            )

        self.assertIsInstance(
            result,
            MissionExecutionResult,
        )

        self.assertFalse(
            result.success
        )

        self.assertIn(
            "GUI authority rejected",
            result.error,
        )

        # No physical tool reached execution.
        self.assertEqual(
            executed,
            [],
        )

        # The mission-step runtime model was never entered.
        mock_chat.assert_not_called()

        # The planner's authority expansion was presented
        # exactly once to the human confirmation boundary.
        mock_confirmation.assert_called_once()

        confirmation_tool, arguments = (
            mock_confirmation.call_args.args
        )

        self.assertEqual(
            confirmation_tool,
            "mission_gui_authority_expansion",
        )

        self.assertEqual(
            arguments[
                "authority_scope"
            ],
            "gui_action_classes_only",
        )

        self.assertEqual(
            len(
                arguments[
                    "proposed_steps"
                ]
            ),
            1,
        )

        self.assertEqual(
            arguments[
                "proposed_steps"
            ][0][
                "planned_tool"
            ],
            "click",
        )
