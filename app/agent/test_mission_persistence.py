import tempfile
import unittest
from pathlib import Path

from app.agent.mission_persistence import (
    MissionPersistence,
)
from app.agent.mission_state import (
    MissionState,
    MissionStatus,
)


class TestMissionPersistence(unittest.TestCase):

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

    def test_create_and_load(self):

        mission = MissionState.create(
            "Build a calculator."
        )

        self.persistence.create(
            mission
        )

        restored = self.persistence.load(
            mission.mission_id
        )

        self.assertIsNotNone(
            restored
        )

        self.assertEqual(
            restored.mission_id,
            mission.mission_id,
        )

        self.assertEqual(
            restored.goal,
            mission.goal,
        )

        self.assertEqual(
            restored.status,
            MissionStatus.PLANNED,
        )

    def test_save_updates_existing_mission(self):

        mission = MissionState.create(
            "Build an application."
        )

        self.persistence.create(
            mission
        )

        mission.start()

        mission.set_current_step(
            "implementation"
        )

        self.persistence.save(
            mission
        )

        restored = self.persistence.load(
            mission.mission_id
        )

        self.assertEqual(
            restored.status,
            MissionStatus.RUNNING,
        )

        self.assertEqual(
            restored.current_step_id,
            "implementation",
        )

    def test_missing_mission_returns_none(self):

        self.assertIsNone(
            self.persistence.load(
                "M-doesnotexist"
            )
        )

    def test_duplicate_create_is_rejected(self):

        mission = MissionState.create(
            "Build an application."
        )

        self.persistence.create(
            mission
        )

        with self.assertRaises(ValueError):
            self.persistence.create(
                mission
            )

    def test_list_missions(self):

        first = MissionState.create(
            "First mission."
        )

        second = MissionState.create(
            "Second mission."
        )

        self.persistence.create(
            first
        )

        self.persistence.create(
            second
        )

        missions = (
            self.persistence.list_missions()
        )

        ids = {
            mission.mission_id
            for mission in missions
        }

        self.assertEqual(
            ids,
            {
                first.mission_id,
                second.mission_id,
            },
        )

    def test_plan_survives_database_round_trip(self):

        from app.agent.goal_plan import (
            GoalPlan,
            GoalStep,
            StepStatus,
        )

        mission = MissionState.create(
            "Perform three actions."
        )

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
                dependencies=["second"],
            )
        )

        mission.plan = plan
        mission.status = MissionStatus.PAUSED

        self.persistence.create(
            mission
        )

        restored = self.persistence.load(
            mission.mission_id
        )

        self.assertIsNotNone(
            restored
        )

        self.assertIsNotNone(
            restored.plan
        )

        self.assertEqual(
            restored.plan.goal,
            mission.plan.goal,
        )

        self.assertEqual(
            restored.plan.steps[0].status,
            StepStatus.COMPLETED,
        )

        self.assertEqual(
            restored.plan.steps[1].status,
            StepStatus.COMPLETED,
        )

        self.assertEqual(
            restored.plan.steps[2].status,
            StepStatus.PENDING,
        )

        self.assertEqual(
            restored.plan.steps[2].dependencies,
            ["second"],
        )

        self.assertEqual(
            restored.plan.next_pending_step().id,
            "third",
        )

    def test_delete_mission(self):

        mission = MissionState.create(
            "Delete me."
        )

        self.persistence.create(
            mission
        )

        self.assertTrue(
            self.persistence.delete(
                mission.mission_id
            )
        )

        self.assertIsNone(
            self.persistence.load(
                mission.mission_id
            )
        )

        self.assertFalse(
            self.persistence.delete(
                mission.mission_id
            )
        )


if __name__ == "__main__":
    unittest.main()