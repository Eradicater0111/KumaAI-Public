import json
import tempfile
import unittest
from pathlib import Path

from app.agent.goal_plan import (
    GoalPlan,
    GoalStep,
    StepStatus,
)
from app.agent.mission_persistence import (
    MissionPersistence,
)
from app.agent.mission_state import (
    MissionState,
    MissionStatus,
)


class TestMissionStateHardening(unittest.TestCase):

    def base_payload(
        self,
    ):
        mission = MissionState.create(
            "Recover safely."
        )

        return mission.to_dict()

    def paused_recovery_payload(
        self,
    ):
        mission = MissionState.create(
            "Recover safely."
        )

        plan = GoalPlan(
            goal=mission.goal
        )

        step = GoalStep(
            id="recover",
            objective="Finish the recovery step.",
            status=StepStatus.IN_PROGRESS,
            success_criteria=[
                "Recovery is complete."
            ],
            verification_requirements=[
                "Inspect the recovery end-state."
            ],
        )

        plan.add_step(
            step
        )

        plan.current_step_id = (
            step.id
        )

        mission.plan = plan

        mission.status = (
            MissionStatus.PAUSED
        )

        mission.current_step_id = (
            step.id
        )

        mission.last_evidence = (
            "VERIFIED_STATE"
        )

        mission.continuation_guard_known = True

        mission.continuation_guard_tool = (
            "open_file"
        )

        mission.continuation_guard_arguments = {
            "path": "/tmp/example"
        }

        mission.continuation_guard_capability = (
            "filesystem"
        )

        return mission.to_dict()

    def test_valid_recovery_state_still_round_trips(
        self,
    ):
        payload = self.paused_recovery_payload()

        restored = MissionState.from_dict(
            payload
        )

        self.assertEqual(
            restored.status,
            MissionStatus.PAUSED,
        )

        self.assertTrue(
            restored.continuation_guard_known
        )

    def test_string_false_is_not_accepted_as_guard_boolean(
        self,
    ):
        payload = self.base_payload()

        payload[
            "continuation_guard_known"
        ] = "false"

        with self.assertRaises(ValueError):
            MissionState.from_dict(
                payload
            )

    def test_integer_is_not_accepted_as_pending_boolean(
        self,
    ):
        payload = self.base_payload()

        payload[
            "continuation_verification_pending"
        ] = 1

        with self.assertRaises(ValueError):
            MissionState.from_dict(
                payload
            )

    def test_guard_arguments_must_be_dictionary(
        self,
    ):
        payload = self.base_payload()

        payload[
            "continuation_guard_arguments"
        ] = [
            [
                "target",
                "example",
            ]
        ]

        with self.assertRaises(ValueError):
            MissionState.from_dict(
                payload
            )

    def test_string_is_not_accepted_as_string_list(
        self,
    ):
        payload = self.base_payload()

        payload[
            "completed_step_ids"
        ] = "abc"

        with self.assertRaises(ValueError):
            MissionState.from_dict(
                payload
            )

    def test_action_history_rejects_non_dictionary_entries(
        self,
    ):
        payload = self.base_payload()

        payload[
            "action_history"
        ] = [
            {
                "tool": "open_file"
            },
            "corrupted-entry",
        ]

        with self.assertRaises(ValueError):
            MissionState.from_dict(
                payload
            )

    def test_plan_rejects_non_dictionary_shape(
        self,
    ):
        payload = self.base_payload()

        payload["plan"] = [
            "not",
            "a",
            "plan",
        ]

        with self.assertRaises(ValueError):
            MissionState.from_dict(
                payload
            )

    def test_unknown_guard_cannot_retain_provenance(
        self,
    ):
        payload = self.base_payload()

        payload[
            "continuation_guard_known"
        ] = False

        payload[
            "continuation_guard_tool"
        ] = "open_file"

        payload[
            "continuation_guard_arguments"
        ] = {
            "path": "/tmp/example"
        }

        with self.assertRaises(ValueError):
            MissionState.from_dict(
                payload
            )

    def test_pending_barrier_without_provenance_remains_loadable(
        self,
    ):
        payload = self.base_payload()

        payload[
            "continuation_verification_pending"
        ] = True

        restored = MissionState.from_dict(
            payload
        )

        self.assertTrue(
            restored.continuation_verification_pending
        )

        self.assertFalse(
            restored.continuation_guard_known
        )

    def test_pending_barrier_does_not_rewrite_remaining_objective(
        self,
    ):
        payload = self.paused_recovery_payload()

        payload[
            "continuation_verification_pending"
        ] = True

        payload[
            "remaining_objective"
        ] = "Persisted transitional remainder."

        restored = MissionState.from_dict(
            payload
        )

        self.assertTrue(
            restored.continuation_verification_pending
        )

        self.assertEqual(
            restored.remaining_objective,
            "Persisted transitional remainder.",
        )

    def test_mission_and_plan_current_step_must_match(
        self,
    ):
        payload = self.paused_recovery_payload()

        payload[
            "current_step_id"
        ] = ""

        with self.assertRaises(ValueError):
            MissionState.from_dict(
                payload
            )

    def test_paused_current_step_must_be_in_progress(
        self,
    ):
        payload = self.paused_recovery_payload()

        payload["plan"]["steps"][0][
            "status"
        ] = StepStatus.COMPLETED.value

        with self.assertRaises(ValueError):
            MissionState.from_dict(
                payload
            )

    def test_completed_mission_requires_complete_plan(
        self,
    ):
        payload = self.paused_recovery_payload()

        payload[
            "status"
        ] = MissionStatus.COMPLETED.value

        payload[
            "current_step_id"
        ] = ""

        payload["plan"][
            "current_step_id"
        ] = ""

        payload["plan"]["steps"][0][
            "status"
        ] = StepStatus.PENDING.value

        with self.assertRaises(ValueError):
            MissionState.from_dict(
                payload
            )

    def test_persistence_load_rejects_corrupted_recovery_json(
        self,
    ):
        with tempfile.TemporaryDirectory() as temp_dir:

            db_path = (
                Path(temp_dir)
                / "missions.db"
            )

            persistence = MissionPersistence(
                db_path=db_path
            )

            mission = MissionState.create(
                "Recover safely."
            )

            persistence.create(
                mission
            )

            payload = mission.to_dict()

            payload[
                "continuation_guard_known"
            ] = "false"

            with persistence.get_connection() as connection:

                connection.execute(
                    "UPDATE missions "
                    "SET state_json = ? "
                    "WHERE mission_id = ?",
                    (
                        json.dumps(
                            payload
                        ),
                        mission.mission_id,
                    ),
                )

                connection.commit()

            with self.assertRaises(ValueError):

                persistence.load(
                    mission.mission_id
                )


if __name__ == "__main__":
    unittest.main()
