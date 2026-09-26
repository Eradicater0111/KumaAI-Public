import unittest

from types import SimpleNamespace

from app.agent.capability_registry import (
    Capability,
    CapabilityRegistry,
)
from app.agent.goal_plan import (
    GoalPlan,
    GoalStep,
)
from app.agent.kuma_agent import (
    KumaAgent,
)
from app.agent.kuma_mission_executor import (
    KumaMissionExecutor,
)
from app.agent.mission_controller import (
    MissionController,
)
from app.agent.mission_result import (
    MissionExecutionResult,
)
from app.agent.mission_runner import (
    MissionRunner,
)


def fake_tool_call(
    name,
    arguments=None,
):
    return SimpleNamespace(
        function=SimpleNamespace(
            name=name,
            arguments=arguments or {},
        )
    )


def fake_response(
    tool_name,
):
    return SimpleNamespace(
        message=SimpleNamespace(
            content="",
            tool_calls=[
                fake_tool_call(
                    tool_name
                )
            ],
        )
    )


class TestEndToEndMission(unittest.TestCase):

    def test_two_step_mission_runs_through_kuma(self):

        registry = CapabilityRegistry(
            capabilities=[
                Capability(
                    name="step_one_capability",
                    description="First test capability.",
                    tools=("first_test",),
                ),
                Capability(
                    name="step_two_capability",
                    description="Second test capability.",
                    tools=("second_test",),
                ),
            ]
        )

        executed = []
        visible_tool_scopes = []

        def first_test():
            executed.append("first_test")
            return "FIRST_OK"

        def second_test():
            executed.append("second_test")
            return "SECOND_OK"

        tools = {
            "first_test": first_test,
            "second_test": second_test,
        }

        kuma = KumaAgent(
            model="test-model",
            tool_registry=tools,
            capability_registry=registry,
        )

        responses = iter(
            [
                fake_response("first_test"),
                fake_response("second_test"),
            ]
        )

        def fake_chat(**kwargs):
            visible_tool_scopes.append(
                kwargs["tools"]
            )
            return next(responses)

        import app.agent.mission_service as mission_service_module

        original_chat = (
            mission_service_module.chat
        )

        mission_service_module.chat = fake_chat

        try:
            plan = GoalPlan(
                goal="Perform two mission steps."
            )

            plan.add_step(
                GoalStep(
                    id="first",
                    objective="Perform the first action.",
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
                        "Verify first result."
                    ],
                )
            )

            plan.add_step(
                GoalStep(
                    id="second",
                    objective="Perform the second action.",
                    dependencies=["first"],
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
                        "Verify second result."
                    ],
                )
            )

            controller = MissionController(
                goal="Perform two mission steps."
            )

            valid, error = controller.set_plan(
                plan
            )

            self.assertTrue(valid)
            self.assertIsNone(error)

            mission_executor = KumaMissionExecutor(
                kuma
            )

            def persist_state(controller):
                return None

            runner = MissionRunner(
                controller=controller,
                execute_step=mission_executor.execute,
                on_state_change=persist_state,
            )

            result = runner.run_mission()


        finally:
            mission_service_module.chat = (
                original_chat
            )

        self.assertTrue(
            result.completed
        )

        self.assertTrue(
            controller.is_complete()
        )

        self.assertTrue(
            controller.task_state.finished
        )

        self.assertEqual(
            executed,
            [
                "first_test",
                "second_test",
            ],
        )

        self.assertEqual(
            len(visible_tool_scopes),
            2,
        )

        def tool_names_from_scope(scope):
            names = []

            for tool in scope:
                if isinstance(tool, dict):
                    function = tool.get("function", {})

                    if isinstance(function, dict):
                        name = function.get("name")

                        if name:
                            names.append(name)

                    continue

                function = getattr(
                    tool,
                    "function",
                    None,
                )

                name = getattr(
                    function,
                    "name",
                    None,
                )

                if name:
                    names.append(name)

            return names

        print("\nVISIBLE TOOL SCOPES:")

        for scope in visible_tool_scopes:
            print(scope)

        self.assertEqual(
    [
        [
            getattr(tool, "__name__", "")
            for tool in scope
        ]
        for scope in visible_tool_scopes
    ],
    [
        ["first_test"],
        ["second_test"],
    ],
)


if __name__ == "__main__":
    unittest.main()
