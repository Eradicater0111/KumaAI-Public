import unittest

from app.agent.capability_registry import (
    create_default_capability_registry,
)
from app.agent.goal_decomposer import (
    GoalDecomposer,
)
from app.agent.goal_plan import (
    StepStatus,
)


class TestGoalDecomposer(unittest.TestCase):

    def valid_json(self):
        return """
        {
          "goal": "Build an application.",
          "steps": [
            {
              "id": "requirements",
              "objective": "Define requirements.",
              "dependencies": [],
              "success_criteria": [
                "Requirements are documented."
              ],
              "required_capabilities": [
                "filesystem"
              ],
              "risk_level": "normal",
              "artifacts": [
                "requirements document"
              ],
              "verification_requirements": [
                "Review the requirements."
              ]
            },
            {
              "id": "implementation",
              "objective": "Implement the application.",
              "dependencies": [
                "requirements"
              ],
              "success_criteria": [
                "Application starts."
              ],
              "required_capabilities": [
                "filesystem",
                "terminal"
              ],
              "risk_level": "normal",
              "artifacts": [
                "application source"
              ],
              "verification_requirements": [
                "Run the application."
              ]
            }
          ]
        }
        """

    def test_valid_plan_is_parsed(self):

        plan, error = GoalDecomposer.parse_plan(
            self.valid_json()
        )

        self.assertIsNone(error)
        self.assertIsNotNone(plan)

        self.assertEqual(
            plan.goal,
            "Build an application.",
        )

        self.assertEqual(
            len(plan.steps),
            2,
        )

        self.assertEqual(
            plan.steps[0].status,
            StepStatus.PENDING,
        )

    def test_dependency_is_preserved(self):

        plan, error = GoalDecomposer.parse_plan(
            self.valid_json()
        )

        self.assertIsNone(error)

        implementation = plan.get_step(
            "implementation"
        )

        self.assertIn(
            "requirements",
            implementation.dependencies,
        )

    def test_invalid_json_is_rejected(self):

        plan, error = GoalDecomposer.parse_plan(
            "not json"
        )

        self.assertIsNone(plan)

        self.assertIn(
            "valid json",
            error.lower(),
        )

    def test_invalid_dependency_is_rejected(self):

        raw = """
        {
          "goal": "Build an application.",
          "steps": [
            {
              "id": "build",
              "objective": "Build the application.",
              "dependencies": ["missing"],
              "risk_level": "normal"
            }
          ]
        }
        """

        plan, error = GoalDecomposer.parse_plan(
            raw
        )

        self.assertIsNone(plan)

        self.assertIn(
            "unknown dependency",
            error.lower(),
        )

    def test_missing_steps_is_rejected(self):

        raw = """
        {
          "goal": "Build an application.",
          "steps": []
        }
        """

        plan, error = GoalDecomposer.parse_plan(
            raw
        )

        self.assertIsNone(plan)

        self.assertIn(
            "at least one step",
            error.lower(),
        )

    def test_invalid_risk_level_is_rejected(self):

        raw = """
        {
          "goal": "Build an application.",
          "steps": [
            {
              "id": "build",
              "objective": "Build the application.",
              "risk_level": "banana"
            }
          ]
        }
        """

        plan, error = GoalDecomposer.parse_plan(
            raw
        )

        self.assertIsNone(plan)

        self.assertIn(
            "invalid risk level",
            error.lower(),
        )

    def test_empty_goal_is_rejected(self):

        plan, error = GoalDecomposer.decompose(
            GoalDecomposer(),
            "",
        )

        self.assertIsNone(plan)

        self.assertIn(
            "empty goal",
            error.lower(),
        )

    def test_unknown_capability_is_rejected(self):

        raw = """
        {
          "goal": "Build an application.",
          "steps": [
            {
              "id": "build",
              "objective": "Build the application.",
              "dependencies": [],
              "success_criteria": [
                "Application works."
              ],
              "required_capabilities": [
                "quantum_magic"
              ],
              "risk_level": "normal",
              "artifacts": [
                "application"
              ],
              "verification_requirements": [
                "Run the application."
              ]
            }
          ]
        }
        """

        plan, error = GoalDecomposer.parse_plan(
            raw,
            capability_registry=(
                create_default_capability_registry()
            ),
        )

        self.assertIsNone(plan)
        self.assertIsNotNone(error)

        self.assertIn(
            "unavailable capabilities",
            error.lower(),
        )

        self.assertIn(
            "quantum_magic",
            error,
        )

    def test_real_capability_is_accepted(self):

        raw = """
        {
          "goal": "Build an application.",
          "steps": [
            {
              "id": "build",
              "objective": "Build the application.",
              "dependencies": [],
              "success_criteria": [
                "Application works."
              ],
              "required_capabilities": [
                "filesystem",
                "terminal"
              ],
              "risk_level": "normal",
              "artifacts": [
                "application"
              ],
              "verification_requirements": [
                "Run the application."
              ]
            }
          ]
        }
        """

        plan, error = GoalDecomposer.parse_plan(
            raw,
            capability_registry=(
                create_default_capability_registry()
            ),
        )

        self.assertIsNone(error)
        self.assertIsNotNone(plan)

        self.assertEqual(
            plan.steps[0].required_capabilities,
            [
                "filesystem",
                "terminal",
            ],
        )

    def test_custom_capability_registry_is_used(self):

        from app.agent.capability_registry import (
            Capability,
            CapabilityRegistry,
        )

        registry = CapabilityRegistry()

        registry.register(
            Capability(
                name="test_capability",
                description="Test capability.",
                tools=("test_tool",),
            )
        )

        raw = """
        {
          "goal": "Run a test.",
          "steps": [
            {
              "id": "run_test",
              "objective": "Run the test.",
              "dependencies": [],
              "success_criteria": [
                "Test passes."
              ],
              "required_capabilities": [
                "test_capability"
              ],
              "risk_level": "normal",
              "artifacts": [
                "test result"
              ],
              "verification_requirements": [
                "Check test result."
              ]
            }
          ]
        }
        """

        plan, error = GoalDecomposer.parse_plan(
            raw,
            capability_registry=registry,
        )

        self.assertIsNone(error)
        self.assertIsNotNone(plan)

        self.assertEqual(
            plan.steps[0].required_capabilities,
            ["test_capability"],
        )

    def test_model_output_can_be_injected(self):

        decomposer = GoalDecomposer()

        decomposer.call_model = (
            lambda goal: type(
                "Response",
                (),
                {
                    "message": type(
                        "Message",
                        (),
                        {
                            "content": self.valid_json()
                        },
                    )()
                },
            )()
        )

        plan, error = decomposer.decompose(
            "Build an application."
        )

        self.assertIsNone(error)
        self.assertIsNotNone(plan)

        self.assertEqual(
            plan.goal,
            "Build an application.",
        )


if __name__ == "__main__":
    unittest.main()