import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.agent.goal_plan import (
    GoalPlan,
    GoalStep,
    StepStatus,
)
from app.agent.kuma_agent import KumaAgent
from app.agent.kuma_mission_executor import (
    KumaMissionExecutor,
)
from app.agent.mission_persistence import (
    MissionPersistence,
)
from app.agent.mission_result import (
    MissionExecutionResult,
)
from app.agent.mission_state import (
    MissionState,
    MissionStatus,
)
from app.agent.remaining_objective_resolver import (
    RemainingObjectiveResolution,
)
from app.agent.gui_intent_authority import (
    GUI_AUTHORITY_CONFIRMED,
    GUI_AUTHORITY_CONFIRMATION_TOOL,
    GUI_AUTHORITY_EXPLICIT,
)


class TestMissionResume(unittest.TestCase):

    def setUp(self):

        self.temp_dir = tempfile.TemporaryDirectory()

        self.db_path = (
            Path(self.temp_dir.name)
            / "missions.db"
        )

        self.persistence = MissionPersistence(
            db_path=self.db_path
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def make_mission(self):

        plan = GoalPlan(
            goal="Perform three actions."
        )

        plan.add_step(
            GoalStep(
                id="first",
                objective="Perform the first action.",
                status=StepStatus.COMPLETED,
            )
        )

        plan.add_step(
            GoalStep(
                id="second",
                objective="Perform the second action.",
                status=StepStatus.COMPLETED,
                dependencies=["first"],
            )
        )

        plan.add_step(
            GoalStep(
                id="third",
                objective="Perform the third action.",
                status=StepStatus.PENDING,
                dependencies=["second"],
            )
        )

        mission = MissionState.create(
            "Perform three actions."
        )

        mission.plan = plan
        mission.status = MissionStatus.PAUSED

        mission.completed_step_ids = [
            "first",
            "second",
        ]

        mission.last_evidence = (
            "SECOND_VERIFIED"
        )

        self.persistence.create(
            mission
        )

        return mission

    def test_resume_does_not_repeat_completed_steps(self):

        mission = self.make_mission()

        calls = []

        kuma = KumaAgent(
            tool_registry={}
        )

        def fake_execute(step):

            print(
                f"\nFAKE EXECUTE CALLED → {step.id}"
            )

            calls.append(
                step.id
            )

            result = MissionExecutionResult(
                success=True,
                verified=True,
                step_id=step.id,
                capability="test",
                tool_name=f"{step.id}_tool",
                arguments={},
                result=f"{step.id}_verified",
                verification="verified",
            )

            print(
                "FAKE EXECUTE RESULT →",
                result,
            )

            return result

        kuma.execute_mission_step = (
            fake_execute
        )

        with patch(
            "app.agent.mission_service.MissionPersistence",
            return_value=self.persistence,
        ):
            result = kuma.resume_mission(
                mission.mission_id
            )

        print(
            "\n===== RESUME DEBUG ====="
        )

        print(
            "RESULT →",
            result,
        )

        print(
            "RESULT SUCCESS →",
            result.success,
        )

        print(
            "RESULT VERIFIED →",
            result.verified,
        )

        print(
            "RESULT COMPLETED →",
            result.completed,
        )

        print(
            "RESULT STEP →",
            result.step_id,
        )

        print(
            "RESULT TOOL →",
            result.tool_name,
        )

        print(
            "RESULT ERROR →",
            result.error,
        )

        print(
            "RESULT VERIFICATION →",
            result.verification,
        )

        print(
            "EXECUTED CALLS →",
            calls,
        )

        restored = self.persistence.load(
            mission.mission_id
        )

        print(
            "\n===== PERSISTED STATE ====="
        )

        print(
            restored.summary()
        )

        print(
            "PERSISTED STATUS →",
            restored.status,
        )

        print(
            "PERSISTED COMPLETED →",
            restored.completed_step_ids,
        )

        print(
            "PERSISTED CURRENT STEP →",
            restored.current_step_id,
        )

        self.assertTrue(
            result.completed
        )

        self.assertEqual(
            calls,
            ["third"],
        )

        self.assertEqual(
            restored.status,
            MissionStatus.COMPLETED,
        )

        self.assertEqual(
            restored.completed_step_ids,
            [
                "first",
                "second",
                "third",
            ],
        )

    def test_missing_mission_is_rejected(self):

        kuma = KumaAgent(
            tool_registry={}
        )

        with patch(
            "app.agent.mission_service.MissionPersistence",
            return_value=self.persistence,
        ):
            result = kuma.resume_mission(
                "M-does-not-exist"
            )

            self.assertFalse(
                result.success
            )

            self.assertIn(
                "not found",
                result.error.lower(),
            )

    def test_completed_mission_is_not_rerun(self):

        mission = self.make_mission()

        mission.plan.steps[2].status = (
            StepStatus.COMPLETED
        )

        mission.completed_step_ids.append(
            "third"
        )

        mission.status = (
            MissionStatus.COMPLETED
        )

        self.persistence.save(
            mission
        )

        kuma = KumaAgent(
            tool_registry={}
        )

        with patch(
            "app.agent.mission_service.MissionPersistence",
            return_value=self.persistence,
        ):
            result = kuma.resume_mission(
                mission.mission_id
            )

        self.assertTrue(
            result.success
        )

        self.assertEqual(
            result.step_id,
            "",
        )

    def test_failed_mission_requires_explicit_retry(self):

        mission = self.make_mission()

        mission.status = (
            MissionStatus.FAILED
        )

        mission.failures.append(
            "Second action failed."
        )

        self.persistence.save(
            mission
        )

        kuma = KumaAgent(
            tool_registry={}
        )

        with patch(
            "app.agent.mission_service.MissionPersistence",
            return_value=self.persistence,
        ):
            result = kuma.resume_mission(
                mission.mission_id
            )

        self.assertFalse(
            result.success
        )

        self.assertIn(
            "previously failed",
            result.error.lower(),
        )

    def test_resume_does_not_replay_in_progress_partial_step(self):

        mission = self.make_mission()

        step = mission.plan.get_step(
            "third"
        )

        step.status = StepStatus.IN_PROGRESS
        step.reason = (
            "Verified partial state requires continuation."
        )

        mission.plan.current_step_id = (
            "third"
        )

        mission.current_step_id = (
            "third"
        )

        mission.status = (
            MissionStatus.PAUSED
        )

        mission.last_evidence = (
            "PARTIAL_STATE_VERIFIED"
        )

        self.persistence.save(
            mission
        )

        calls = []

        kuma = KumaAgent(
            tool_registry={}
        )

        def fake_execute(step):
            calls.append(step.id)

            raise AssertionError(
                "A resumable partial step must not "
                "be automatically replayed."
            )

        kuma.execute_mission_step = (
            fake_execute
        )

        with patch(
            "app.agent.mission_service.MissionPersistence",
            return_value=self.persistence,
        ), patch(
            (
                "app.agent.mission_service."
                "RemainingObjectiveResolver.resolve"
            ),
            return_value=(
                RemainingObjectiveResolution(
                    known=True,
                    remaining_objective=(
                        "Perform only the unfinished "
                        "third-action work."
                    ),
                    reason=(
                        "Verified evidence shows partial "
                        "progress already exists."
                    ),
                    evidence_used=(
                        "PARTIAL_STATE_VERIFIED"
                    ),
                )
            ),
        ):
            result = kuma.resume_mission(
                mission.mission_id
            )

        restored = self.persistence.load(
            mission.mission_id
        )

        self.assertEqual(
            calls,
            [],
        )

        self.assertFalse(
            result.completed
        )

        self.assertTrue(
            result.success
        )

        self.assertEqual(
            result.recovery_action,
            "resume",
        )

        self.assertEqual(
            result.recovery_evidence,
            "PARTIAL_STATE_VERIFIED",
        )

        self.assertEqual(
            restored.status,
            MissionStatus.PAUSED,
        )

        self.assertEqual(
            restored.current_step_id,
            "third",
        )

        self.assertEqual(
            restored.plan.get_step(
                "third"
            ).status,
            StepStatus.IN_PROGRESS,
        )

        self.assertEqual(
            restored.remaining_objective,
            (
                "Perform only the unfinished "
                "third-action work."
            ),
        )

        self.assertEqual(
            result.result,
            (
                "Perform only the unfinished "
                "third-action work."
            ),
        )


    def test_unknown_remaining_objective_stays_paused(self):

        mission = self.make_mission()

        step = mission.plan.get_step(
            "third"
        )

        step.status = (
            StepStatus.IN_PROGRESS
        )

        step.reason = (
            "Verified partial state is ambiguous."
        )

        mission.plan.current_step_id = (
            "third"
        )

        mission.current_step_id = (
            "third"
        )

        mission.status = (
            MissionStatus.PAUSED
        )

        mission.last_evidence = (
            "PARTIAL_STATE_VERIFIED"
        )

        self.persistence.save(
            mission
        )

        calls = []

        kuma = KumaAgent(
            tool_registry={}
        )

        def fake_execute(step):

            calls.append(
                step.id
            )

            raise AssertionError(
                "Unknown continuation must not execute."
            )

        kuma.execute_mission_step = (
            fake_execute
        )

        with patch(
            "app.agent.mission_service.MissionPersistence",
            return_value=self.persistence,
        ), patch(
            (
                "app.agent.mission_service."
                "RemainingObjectiveResolver.resolve"
            ),
            return_value=(
                RemainingObjectiveResolution(
                    known=False,
                    remaining_objective="",
                    reason=(
                        "Evidence does not safely identify "
                        "the unfinished remainder."
                    ),
                    evidence_used=(
                        "PARTIAL_STATE_VERIFIED"
                    ),
                )
            ),
        ):

            result = kuma.resume_mission(
                mission.mission_id
            )

        restored = self.persistence.load(
            mission.mission_id
        )

        self.assertEqual(
            calls,
            [],
        )

        self.assertFalse(
            result.success
        )

        self.assertEqual(
            result.recovery_action,
            "escalate",
        )

        self.assertEqual(
            restored.status,
            MissionStatus.PAUSED,
        )

        self.assertEqual(
            restored.current_step_id,
            "third",
        )

        self.assertEqual(
            restored.remaining_objective,
            "",
        )

        self.assertEqual(
            restored.plan.get_step(
                "third"
            ).status,
            StepStatus.IN_PROGRESS,
        )



    def _make_gui_resume_mission(
        self,
        *,
        goal: str,
        legacy_authority: str,
        legacy_authority_goal: str,
    ):
        plan = GoalPlan(
            goal=goal
        )

        plan.add_step(
            GoalStep(
                id="gui-step",
                objective="Advance the GUI task.",
                planned_tool="click",
                gui_authority=legacy_authority,
                gui_authority_goal=(
                    legacy_authority_goal
                ),
            )
        )

        mission = MissionState.create(
            goal
        )

        mission.plan = plan
        mission.status = MissionStatus.PAUSED

        self.persistence.create(
            mission
        )

        return mission

    def test_resume_rederives_explicit_gui_authority(
        self
    ):
        goal = "Click the Settings button."

        mission = self._make_gui_resume_mission(
            goal=goal,
            legacy_authority=(
                GUI_AUTHORITY_CONFIRMED
            ),
            legacy_authority_goal=(
                "Click Delete."
            ),
        )

        confirmation_calls = []
        executed = []

        kuma = KumaAgent(
            tool_registry={},
            confirmation_callback=(
                lambda tool, arguments: (
                    confirmation_calls.append(
                        (tool, arguments)
                    )
                    or False
                )
            ),
        )

        def fake_execute(step):
            executed.append(
                (
                    step.gui_authority,
                    step.gui_authority_goal,
                )
            )

            return MissionExecutionResult(
                success=True,
                verified=True,
                step_id=step.id,
                capability="computer_control",
                tool_name=step.planned_tool,
                arguments={},
                result="verified",
                verification="verified",
            )

        kuma.execute_mission_step = (
            fake_execute
        )

        with patch(
            "app.agent.mission_service.MissionPersistence",
            return_value=self.persistence,
        ):
            result = kuma.resume_mission(
                mission.mission_id
            )

        self.assertTrue(
            result.completed
        )
        self.assertEqual(
            confirmation_calls,
            [],
        )
        self.assertEqual(
            executed,
            [
                (
                    GUI_AUTHORITY_EXPLICIT,
                    goal,
                )
            ],
        )

        restored = self.persistence.load(
            mission.mission_id
        )

        restored_step = (
            restored.plan.get_step(
                "gui-step"
            )
        )

        self.assertEqual(
            restored_step.gui_authority,
            "",
        )
        self.assertEqual(
            restored_step.gui_authority_goal,
            "",
        )

    def test_resume_expansion_requires_fresh_confirmation(
        self
    ):
        goal = "Look at the Settings page."

        mission = self._make_gui_resume_mission(
            goal=goal,
            legacy_authority=(
                GUI_AUTHORITY_CONFIRMED
            ),
            legacy_authority_goal=goal,
        )

        confirmation_calls = []
        executed = []

        kuma = KumaAgent(
            tool_registry={},
            confirmation_callback=(
                lambda tool, arguments: (
                    confirmation_calls.append(
                        (tool, arguments)
                    )
                    or False
                )
            ),
        )

        kuma.execute_mission_step = (
            lambda step: executed.append(step)
        )

        with patch(
            "app.agent.mission_service.MissionPersistence",
            return_value=self.persistence,
        ):
            result = kuma.resume_mission(
                mission.mission_id
            )

        self.assertFalse(
            result.success
        )
        self.assertEqual(
            result.recovery_action,
            "escalate",
        )
        self.assertEqual(
            executed,
            [],
        )
        self.assertEqual(
            len(confirmation_calls),
            1,
        )
        self.assertEqual(
            confirmation_calls[0][0],
            GUI_AUTHORITY_CONFIRMATION_TOOL,
        )
        self.assertIn(
            "could not be re-established",
            result.error,
        )

    def test_resume_confirmed_expansion_is_rebound_fresh(
        self
    ):
        goal = "Look at the Settings page."

        mission = self._make_gui_resume_mission(
            goal=goal,
            legacy_authority=(
                GUI_AUTHORITY_EXPLICIT
            ),
            legacy_authority_goal=(
                "Click Delete."
            ),
        )

        confirmation_calls = []
        executed = []

        kuma = KumaAgent(
            tool_registry={},
            confirmation_callback=(
                lambda tool, arguments: (
                    confirmation_calls.append(
                        (tool, arguments)
                    )
                    or True
                )
            ),
        )

        def fake_execute(step):
            executed.append(
                (
                    step.gui_authority,
                    step.gui_authority_goal,
                )
            )

            return MissionExecutionResult(
                success=True,
                verified=True,
                step_id=step.id,
                capability="computer_control",
                tool_name=step.planned_tool,
                arguments={},
                result="verified",
                verification="verified",
            )

        kuma.execute_mission_step = (
            fake_execute
        )

        with patch(
            "app.agent.mission_service.MissionPersistence",
            return_value=self.persistence,
        ):
            result = kuma.resume_mission(
                mission.mission_id
            )

        self.assertTrue(
            result.completed
        )
        self.assertEqual(
            len(confirmation_calls),
            1,
        )
        self.assertEqual(
            confirmation_calls[0][0],
            GUI_AUTHORITY_CONFIRMATION_TOOL,
        )
        self.assertEqual(
            executed,
            [
                (
                    GUI_AUTHORITY_CONFIRMED,
                    goal,
                )
            ],
        )


if __name__ == "__main__":
    unittest.main()