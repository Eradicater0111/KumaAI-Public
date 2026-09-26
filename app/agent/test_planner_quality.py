import unittest

from app.agent.goal_plan import (
    GoalPlan,
    GoalStep,
)
from app.agent.planner_quality import (
    PlannerQualityGate,
)


class TestPlannerQualityGate(unittest.TestCase):

    def make_valid_plan(self):

        plan = GoalPlan(
            goal="Build an application."
        )

        plan.add_step(
            GoalStep(
                id="requirements",
                objective="Define requirements.",
                success_criteria=[
                    "Requirements are documented."
                ],
                required_capabilities=[
                    "filesystem"
                ],
                artifacts=[
                    "requirements.md"
                ],
                verification_requirements=[
                    "Review requirements."
                ],
            )
        )

        plan.add_step(
            GoalStep(
                id="implementation",
                objective="Implement the application.",
                dependencies=[
                    "requirements"
                ],
                success_criteria=[
                    "Application starts."
                ],
                required_capabilities=[
                    "terminal"
                ],
                artifacts=[
                    "application source"
                ],
                verification_requirements=[
                    "Run the application."
                ],
            )
        )

        return plan

    def test_valid_plan_is_accepted(self):

        gate = PlannerQualityGate(
            available_capabilities={
                "filesystem",
                "terminal",
            }
        )

        accepted, reasons = gate.validate(
            self.make_valid_plan()
        )

        self.assertTrue(accepted)
        self.assertEqual(
            reasons,
            [],
        )

    def test_missing_success_criteria_is_rejected(self):

        plan = self.make_valid_plan()

        plan.steps[0].success_criteria = []

        gate = PlannerQualityGate(
            available_capabilities={
                "filesystem",
                "terminal",
            }
        )

        accepted, reasons = gate.validate(
            plan
        )

        self.assertFalse(accepted)
        self.assertTrue(
            any(
                "success criteria" in reason.lower()
                for reason in reasons
            )
        )

    def test_missing_verification_is_rejected(self):

        plan = self.make_valid_plan()

        plan.steps[0].verification_requirements = []

        gate = PlannerQualityGate(
            available_capabilities={
                "filesystem",
                "terminal",
            }
        )

        accepted, reasons = gate.validate(
            plan
        )

        self.assertFalse(accepted)
        self.assertTrue(
            any(
                "verification" in reason.lower()
                for reason in reasons
            )
        )

    def test_unavailable_capability_is_rejected(self):

        plan = self.make_valid_plan()

        plan.steps[0].required_capabilities = [
            "browser"
        ]

        gate = PlannerQualityGate(
            available_capabilities={
                "filesystem",
                "terminal",
            }
        )

        accepted, reasons = gate.validate(
            plan
        )

        self.assertFalse(accepted)
        self.assertTrue(
            any(
                "unavailable capability" in reason.lower()
                for reason in reasons
            )
        )

    def test_dependency_cycle_is_rejected(self):

        plan = GoalPlan(
            goal="Build something."
        )

        plan.add_step(
            GoalStep(
                id="a",
                objective="Do A.",
                dependencies=["b"],
                success_criteria=["A works."],
                artifacts=["a.txt"],
                verification_requirements=["Check A."],
            )
        )

        plan.add_step(
            GoalStep(
                id="b",
                objective="Do B.",
                dependencies=["a"],
                success_criteria=["B works."],
                artifacts=["b.txt"],
                verification_requirements=["Check B."],
            )
        )

        gate = PlannerQualityGate()

        accepted, reasons = gate.validate(
            plan
        )

        self.assertFalse(accepted)
        self.assertTrue(
            any(
                "cycle" in reason.lower()
                for reason in reasons
            )
        )

    def test_step_limit_is_enforced(self):

        plan = GoalPlan(
            goal="Large mission."
        )

        for index in range(6):

            plan.add_step(
                GoalStep(
                    id=f"step_{index}",
                    objective=f"Do step {index}.",
                    success_criteria=[
                        "Step succeeds."
                    ],
                    artifacts=[
                        f"artifact_{index}"
                    ],
                    verification_requirements=[
                        "Verify the step."
                    ],
                )
            )

        gate = PlannerQualityGate(
            max_steps=5
        )

        accepted, reasons = gate.validate(
            plan
        )

        self.assertFalse(accepted)
        self.assertTrue(
            any(
                "maximum allowed" in reason.lower()
                for reason in reasons
            )
        )


if __name__ == "__main__":
    unittest.main()