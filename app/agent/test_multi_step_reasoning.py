import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.agent.kuma_agent import KumaAgent
from app.agent.permissions import PermissionLevel
from app.agent.task_state import TaskState


def fake_tool_call(name, arguments):
    return SimpleNamespace(
        function=SimpleNamespace(
            name=name,
            arguments=arguments,
        )
    )


def fake_response(content="", tool_calls=None):
    return SimpleNamespace(
        message=SimpleNamespace(
            content=content,
            tool_calls=tool_calls or [],
        )
    )


class TestKumaMultiStepReasoning(unittest.TestCase):
    """
    Phase 2 regression harness.

    These tests deliberately avoid Ollama. They exercise KUMA's
    agent loop with deterministic model responses so multi-step
    behavior can be tested quickly and repeatably.
    """

    @patch(
        "app.agent.kuma_agent.get_memory_context",
        return_value=None,
    )
    @patch(
        "app.agent.kuma_agent.save_message"
    )
    def test_task_state_tracks_verified_steps(
        self,
        _save_message,
        _memory_context,
    ):
        calls = []

        def first():
            calls.append("first")
            return "FIRST_VERIFIED"

        def second():
            calls.append("second")
            return "SECOND_VERIFIED"

        agent = self.make_agent(
            model_responses=[
                fake_response(
                    tool_calls=[
                        fake_tool_call(
                            "first_test",
                            {},
                        )
                    ]
                ),
                fake_response(
                    tool_calls=[
                        fake_tool_call(
                            "second_test",
                            {},
                        )
                    ]
                ),
                fake_response(
                    content="Task complete.",
                ),
            ],
            tools={
                "first_test": first,
                "second_test": second,
            },
        )

        result = agent.run(
            "Perform the first action, then perform the second action."
        )

        self.assertEqual(
            calls,
            [
                "first",
                "second",
            ],
        )

        self.assertIsNotNone(
            agent.task_state
        )

        self.assertEqual(
            agent.task_state.goal,
            "Perform the first action, then perform the second action.",
        )

        self.assertTrue(
            agent.task_state.finished
        )

        self.assertEqual(
            agent.task_state.remaining_objective,
            "",
        )

        self.assertEqual(
            len(
                agent.task_state.action_history
            ),
            2,
        )

        self.assertEqual(
            agent.task_state.action_history[0]["tool"],
            "first_test",
        )

        self.assertEqual(
            agent.task_state.action_history[1]["tool"],
            "second_test",
        )

        self.assertIn(
            "first_test completed successfully.",
            agent.task_state.completed_steps,
        )

        self.assertIn(
            "second_test completed successfully.",
            agent.task_state.completed_steps,
        )

        self.assertEqual(
            result,
            "Task complete.",
        )

    def make_agent(
        self,
        model_responses,
        tools,
        goal_decision="continue",
    ):
        agent = KumaAgent(
            model="test-model",
            tool_registry=tools,
            max_steps=5,
        )

        agent.explicitly_requests_tool_action = (
            lambda user_message, tool_name, arguments: True
        )

        agent.explicitly_requests_dangerous_action = (
            lambda user_message, tool_name, arguments: True
        )

        responses = iter(model_responses)

        agent.ask_model = (
            lambda messages: next(responses)
        )

        if goal_decision == "complete":

            goal_decision_response = fake_response(
                content=(
                    '{"status":"complete",'
                    '"remaining_objective":"",'
                    '"next_action":"",'
                    '"reason":"The task is complete."}'
                )
            )

        else:

            goal_decision_response = fake_response(
                content=(
                    '{"status":"continue",'
                    '"remaining_objective":"Continue the requested task.",'
                    '"next_action":"continue_reasoning",'
                    '"reason":"The task is not yet complete."}'
                )
            )

        agent.call_goal_decision_model = (
            lambda messages: goal_decision_response
        )

        # Keep this harness independent from persistent conversation
        # contents and long-term memory.
        agent.build_context_messages = (
            lambda user_message, memory_context, max_messages: [
                {
                    "role": "system",
                    "content": agent.get_system_prompt(),
                },
                {
                    "role": "user",
                    "content": user_message,
                },
            ]
        )

        return agent

    @patch("app.agent.kuma_agent.get_memory_context", return_value=None)
    @patch("app.agent.kuma_agent.save_message")
    def test_single_step_completes_without_second_model_call(
        self,
        _save_message,
        _memory_context,
    ):
        calls = []

        def inspect():
            calls.append("inspect")
            return "INSPECT_OK"

        agent = self.make_agent(
            model_responses=[
                fake_response(
                    tool_calls=[
                        fake_tool_call(
                            "inspect_test",
                            {},
                        )
                    ]
                ),
            ],
            tools={
                "inspect_test": inspect,
            },
        )

        result = agent.run(
            "Inspect the system."
        )

        self.assertEqual(
            calls,
            ["inspect"],
        )

        self.assertIn(
            "INSPECT_OK",
            result,
        )

    @patch(
        "app.agent.kuma_agent.get_memory_context",
        return_value=None,
    )
    @patch(
        "app.agent.kuma_agent.save_message"
    )
    def test_verified_result_is_returned_for_direct_completion(
        self,
        _save_message,
        _memory_context,
    ):
        calls = []

        def list_files(folder):
            calls.append(folder)

            return (
                "Screenshot 2026-08-27 at 4.17.40 PM.png\n"
                "Suprreeth (Resume).pdf\n"
                "notes.txt"
            )

        agent = self.make_agent(
            model_responses=[
                fake_response(
                    tool_calls=[
                        fake_tool_call(
                            "list_files",
                            {
                                "path": "~/Downloads"
                            },
                        )
                    ]
                ),
            ],
            tools={
                "list_files": list_files,
            },
            goal_decision="complete",
        )

        result = agent.run(
            "List the files in ~/Downloads."
        )

        self.assertEqual(
            calls,
            ["~/Downloads"],
        )

        self.assertIn(
            "Screenshot 2026-08-27 at 4.17.40 PM.png",
            result,
        )

    @patch("app.agent.kuma_agent.get_memory_context", return_value=None)
    @patch("app.agent.kuma_agent.save_message")
    def test_two_step_reasoning_executes_steps_in_order(
        self,
        _save_message,
        _memory_context,
    ):
        calls = []

        def first():
            calls.append("first")
            return "FIRST_OK"

        def second():
            calls.append("second")
            return "SECOND_OK"

        agent = self.make_agent(
            model_responses=[
                fake_response(
                    tool_calls=[
                        fake_tool_call(
                            "first_test",
                            {},
                        )
                    ]
                ),
                fake_response(
                    tool_calls=[
                        fake_tool_call(
                            "second_test",
                            {},
                        )
                    ]
                ),
                fake_response(
                    content="Task complete.",
                ),
            ],
            tools={
                "first_test": first,
                "second_test": second,
            },
        )

        result = agent.run(
            "Perform the first action, then the second action."
        )

        self.assertEqual(
            calls,
            [
                "first",
                "second",
            ],
        )

        self.assertEqual(
            result,
            "Task complete.",
        )

    @patch("app.agent.kuma_agent.get_memory_context", return_value=None)
    @patch("app.agent.kuma_agent.save_message")
    def test_failed_step_does_not_continue(
        self,
        _save_message,
        _memory_context,
    ):
        calls = []

        def failing():
            calls.append("failing")
            raise RuntimeError(
                "EXPECTED_FAILURE"
            )

        def should_not_run():
            calls.append("should_not_run")
            return "BAD"

        agent = self.make_agent(
            model_responses=[
                fake_response(
                    tool_calls=[
                        fake_tool_call(
                            "failing_test",
                            {},
                        )
                    ]
                ),
                fake_response(
                    tool_calls=[
                        fake_tool_call(
                            "should_not_run",
                            {},
                        )
                    ]
                ),
            ],
            tools={
                "failing_test": failing,
                "should_not_run": should_not_run,
            },
        )

        result = agent.run(
            "Do the failing action, then continue."
        )

        self.assertEqual(
            calls,
            ["failing"],
        )

        self.assertIn(
            "EXPECTED_FAILURE",
            result,
        )

    @patch("app.agent.kuma_agent.get_memory_context", return_value=None)
    @patch("app.agent.kuma_agent.save_message")
    def test_max_steps_is_hard_boundary(
        self,
        _save_message,
        _memory_context,
    ):
        calls = []

        def repeatable():
            calls.append("repeatable")
            return "OK"

        agent = self.make_agent(
            model_responses=[
                fake_response(
                    tool_calls=[
                        fake_tool_call(
                            "repeatable_test",
                            {},
                        )
                    ]
                ),
                fake_response(
                    tool_calls=[
                        fake_tool_call(
                            "repeatable_test",
                            {},
                        )
                    ]
                ),
                fake_response(
                    tool_calls=[
                        fake_tool_call(
                            "repeatable_test",
                            {},
                        )
                    ]
                ),
            ],
            tools={
                "repeatable_test": repeatable,
            },
        )

        agent.max_steps = 2

        result = agent.run(
            "Keep performing the action."
        )

        self.assertEqual(
            len(calls),
            2,
        )

        self.assertIn(
            "maximum",
            result.lower(),
        )

    @patch("app.agent.kuma_agent.get_memory_context", return_value=None)
    @patch("app.agent.kuma_agent.save_message")
    def test_model_can_finish_after_verified_tool_result(
        self,
        _save_message,
        _memory_context,
    ):
        calls = []

        def inspect():
            calls.append("inspect")
            return "AUTHORITATIVE_RESULT"

        agent = self.make_agent(
            model_responses=[
                fake_response(
                    tool_calls=[
                        fake_tool_call(
                            "inspect_test",
                            {},
                        )
                    ]
                ),
                fake_response(
                    content="The inspection is complete.",
                ),
            ],
            tools={
                "inspect_test": inspect,
            },
        )

        result = agent.run(
            "Inspect the system and report when finished."
        )

        self.assertEqual(
            calls,
            ["inspect"],
        )

        self.assertEqual(
            result,
            "The inspection is complete.",
        )

    @patch(
        "app.agent.kuma_agent.get_permission_level"
    )
    @patch(
        "app.agent.kuma_agent.get_memory_context",
        return_value=None,
    )
    @patch(
        "app.agent.kuma_agent.save_message"
    )
    def test_goal_decision_receives_authoritative_task_state(
        self,
        _save_message,
        _memory_context,
        _mock_permission,
    ):

        agent = KumaAgent(
            model="test-model",
            tool_registry={},
        )

        agent.task_state = TaskState(
            goal="Open a PDF and tell me what it contains."
        )

        agent.task_state.completed_steps = [
            "list_files completed successfully."
        ]

        agent.task_state.remaining_objective = (
            "Open the discovered PDF."
        )

        agent.task_state.last_evidence = (
            "resume.pdf"
        )

        captured = {}

        def fake_goal_model(messages):
            captured["messages"] = messages

            return fake_response(
                content=(
                    '{"status":"continue",'
                    '"remaining_objective":"Open the discovered PDF.",'
                    '"next_action":"open_file",'
                    '"reason":"The PDF still needs to be opened."}'
                )
            )

        agent.call_goal_decision_model = fake_goal_model

        decision, error = agent.ask_goal_decision(
            [
                {
                    "role": "user",
                    "content": (
                        "Open a PDF and tell me what it contains."
                    ),
                }
            ]
        )

        self.assertIsNone(error)

        self.assertEqual(
            decision.next_action,
            "open_file",
        )

        system_text = "\n".join(
            str(message.get("content", ""))
            for message in captured["messages"]
            if isinstance(message, dict)
        )

        self.assertIn(
            "CURRENT TASK STATE",
            system_text,
        )

        self.assertIn(
            "list_files completed successfully",
            system_text,
        )

        self.assertIn(
            "Open the discovered PDF",
            system_text,
        )

    @patch(
        "app.agent.kuma_agent.get_permission_level"
    )
    @patch(
        "app.agent.kuma_agent.get_memory_context",
        return_value=None,
    )
    @patch(
        "app.agent.kuma_agent.save_message"
    )
    def test_identical_safe_action_repetition_is_terminated(
        self,
        _save_message,
        _memory_context,
        mock_permission,
    ):
        calls = []

        def repeatable():
            calls.append("repeatable")
            return "OK"

        mock_permission.return_value = (
            PermissionLevel.SAFE
        )

        agent = self.make_agent(
            model_responses=[
                fake_response(
                    tool_calls=[
                        fake_tool_call(
                            "repeatable_test",
                            {},
                        )
                    ]
                ),
                fake_response(
                    tool_calls=[
                        fake_tool_call(
                            "repeatable_test",
                            {},
                        )
                    ]
                ),
                fake_response(
                    tool_calls=[
                        fake_tool_call(
                            "repeatable_test",
                            {},
                        )
                    ]
                ),
            ],
            tools={
                "repeatable_test": repeatable,
            },
        )

        agent.max_steps = 5

        result = agent.run(
            "Keep performing the action."
        )

        self.assertEqual(
            calls,
            ["repeatable"],
        )

        self.assertIn(
            "repeatedly",
            result.lower(),
        )

    def test_list_my_files_normalizes_users_home_to_tilde(self):
        result = KumaAgent.normalize_tool_arguments(
            "List my files.",
            "list_files",
            {
                "folder": "/Users/",
            },
        )

        self.assertEqual(
            result["folder"],
            "~",
        )

    def test_list_files_explicit_users_path_is_preserved(self):
        result = KumaAgent.normalize_tool_arguments(
            "List files in /Users/",
            "list_files",
            {
                "folder": "/Users/",
            },
        )

        self.assertEqual(
            result["folder"],
            "/Users/",
        )

    def test_list_files_downloads_is_preserved(self):
        result = KumaAgent.normalize_tool_arguments(
            "List files in Downloads.",
            "list_files",
            {
                "folder": "Downloads",
            },
        )

        self.assertEqual(
            result["folder"],
            "Downloads",
        )

    def test_list_my_files_without_model_folder_uses_home(self):
        result = KumaAgent.normalize_tool_arguments(
            "List my files.",
            "list_files",
            {},
        )

        self.assertEqual(
            result["folder"],
            "~",
        )