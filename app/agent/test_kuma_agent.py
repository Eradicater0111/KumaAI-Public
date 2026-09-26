import unittest

import pytest
from unittest.mock import patch

from app.agent.kuma_agent import KumaAgent
from app.agent.tool_result import ToolResult

from app.agent.goal_decision import (
    GoalDecision,
    GoalStatus,
)


class TestKumaProductionAgent(unittest.TestCase):
    """Agent-loop tests with explicit model/tool and memory seams."""

    def setUp(self):
        # These tests exercise authority and loop behavior, not embedding search
        # or conversation persistence. Every test gets an empty memory context.
        for name, value in (
            ("initialize_memory", None), ("save_message", None),
            ("get_recent_messages", []), ("get_memory_context", ""),
        ):
            patcher = patch(f"app.agent.kuma_agent.{name}", return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)


    # =====================================================
    # SYSTEM INSPECTION
    # =====================================================

    @pytest.mark.live_model
    def test_system_inspection(self):

        def inspect_system() -> ToolResult:
            """Return fixed system information for the live model test."""
            return ToolResult.ok("System fixture: CPU and disk healthy.")

        kuma = KumaAgent(
            model="qwen3:8b",
            tool_registry={
                "inspect_system": inspect_system,
            },
        )

        result = kuma.run(
            "Inspect my system and tell me "
            "what you think about its current state."
        )

        self.assertIsInstance(
            result,
            str,
        )

        self.assertTrue(
            result.strip()
        )

        self.assertTrue(
            any(
                keyword in result.lower()
                for keyword in [
                    "system",
                    "cpu",
                    "disk",
                    "operating system",
                    "macos",
                ]
            )
        )

            # =====================================================
    # DUPLICATE SAFE-ACTION LOOP PROTECTION
    # =====================================================

    def test_identical_safe_action_cannot_loop_forever(self):

        calls = []

        def inspect_system():

            calls.append("inspect_system")

            return ToolResult.ok(
                "SYSTEM_OK"
            )

        kuma = KumaAgent(
            model="test-model",
            tool_registry={
                "inspect_system": inspect_system,
            },
            max_steps=5,
        )

        # -------------------------------------------------
        # MODEL ALWAYS REQUESTS THE EXACT SAME SAFE ACTION
        # -------------------------------------------------

        response_index = {
            "value": 0,
        }

        def fake_ask_model(messages):

            response_index["value"] += 1

            return type(
                "FakeResponse",
                (),
                {
                    "message": type(
                        "FakeMessage",
                        (),
                        {
                            "content": "",
                            "tool_calls": [
                                type(
                                    "FakeToolCall",
                                    (),
                                    {
                                        "function": type(
                                            "FakeFunction",
                                            (),
                                            {
                                                "name": "inspect_system",
                                                "arguments": {},
                                            },
                                        )(),
                                    },
                                )(),
                            ],
                        },
                    )(),
                },
            )()

        kuma.ask_model = fake_ask_model

        # -------------------------------------------------
        # DETERMINISTIC GOAL DECISION
        # -------------------------------------------------
        #
        # Keep the task incomplete so the same model-generated
        # safe action is requested again. This isolates and
        # exercises the duplicate-action guard.
        # -------------------------------------------------

        def fake_goal_decision(messages):

            decision = GoalDecision(
                status=GoalStatus.CONTINUE,
                remaining_objective=(
                    "Continue inspecting the system "
                    "because the request explicitly asks "
                    "for repeated inspection."
                ),
                next_action="inspect_system",
                reason=(
                    "The user requested repeated inspection."
                ),
            )

            return decision, None

        kuma.ask_goal_decision = fake_goal_decision

        # -------------------------------------------------
        # RUN
        # -------------------------------------------------

        result = kuma.run(
            "Inspect my system repeatedly."
        )

        # -------------------------------------------------
        # ACTUAL EXECUTION MUST HAPPEN ONLY ONCE
        # -------------------------------------------------

        self.assertEqual(
            calls,
            [
                "inspect_system",
            ],
        )

        # -------------------------------------------------
        # KUMA SHOULD STOP AFTER THE SECOND IDENTICAL
        # REQUEST IS REPLAYED
        # -------------------------------------------------

        self.assertIn(
            "requested repeatedly",
            result.lower(),
        )

        # The model should have been consulted for:
        # 1. initial execution
        # 2. first identical repeat
        # 3. second identical repeat that terminates
        self.assertEqual(
            response_index["value"],
            3,
        )

        # The authoritative result must exist in the task state.
        self.assertIsNotNone(
            kuma.task_state
        )

        self.assertEqual(
            kuma.task_state.last_evidence,
            "SYSTEM_OK",
        )

                # =====================================================
    # SAFE TOOL FAILURE — RECOVERY
    # =====================================================

    def test_safe_tool_failure_can_recover_with_next_action(self):

        calls = []

        def failing_inspect_system():

            calls.append("inspect_system")

            return ToolResult.fail(
                "System inspection is temporarily unavailable."
            )

        def analyze_screen():

            calls.append("analyze_screen")

            return ToolResult.ok(
                "The KUMA desktop interface is visible."
            )

        kuma = KumaAgent(
            model="test-model",
            tool_registry={
                "inspect_system": failing_inspect_system,
                "analyze_screen": analyze_screen,
            },
            max_steps=3,
        )

        model_responses = [
            type(
                "FakeResponse",
                (),
                {
                    "message": type(
                        "FakeMessage",
                        (),
                        {
                            "content": "",
                            "tool_calls": [
                                type(
                                    "FakeToolCall",
                                    (),
                                    {
                                        "function": type(
                                            "FakeFunction",
                                            (),
                                            {
                                                "name": "inspect_system",
                                                "arguments": {},
                                            },
                                        )(),
                                    },
                                )(),
                            ],
                        },
                    )(),
                },
            )(),

            type(
                "FakeResponse",
                (),
                {
                    "message": type(
                        "FakeMessage",
                        (),
                        {
                            "content": "",
                            "tool_calls": [
                                type(
                                    "FakeToolCall",
                                    (),
                                    {
                                        "function": type(
                                            "FakeFunction",
                                            (),
                                            {
                                                "name": "analyze_screen",
                                                "arguments": {},
                                            },
                                        )(),
                                    },
                                )(),
                            ],
                        },
                    )(),
                },
            )(),

            type(
                "FakeResponse",
                (),
                {
                    "message": type(
                        "FakeMessage",
                        (),
                        {
                            "content": (
                                "The system inspection failed, "
                                "but I recovered by checking "
                                "the screen."
                            ),
                            "tool_calls": [],
                        },
                    )(),
                },
            )(),
        ]

        response_index = {"value": 0}

        def fake_ask_model(messages):

            index = response_index["value"]
            response_index["value"] += 1

            return model_responses[index]

        kuma.ask_model = fake_ask_model

        goal_decisions = []

        def fake_goal_decision(messages):

            decision = GoalDecision(
                status=GoalStatus.CONTINUE,
                remaining_objective=(
                    "Analyze my screen as the "
                    "fallback inspection method."
                ),
                next_action="analyze_screen",
                reason=(
                    "The primary system inspection failed, "
                    "so a safe fallback inspection is "
                    "appropriate."
                ),
            )

            goal_decisions.append(decision)

            return decision, None

        kuma.ask_goal_decision = fake_goal_decision

        result = kuma.run(
            "Inspect my system and, if that fails, "
            "analyze my screen."
        )

        self.assertEqual(
            calls,
            [
                "inspect_system",
                "analyze_screen",
            ],
        )

        self.assertEqual(
            response_index["value"],
            3,
        )

        self.assertIsNotNone(
            kuma.task_state
        )

        self.assertIn(
            "System inspection is temporarily unavailable.",
            kuma.task_state.failures,
        )

        self.assertIn(
            "recovered",
            result.lower(),
        )

        self.assertIn(
            "screen",
            result.lower(),
        )

    def test_dangerous_action_denied_by_confirmation(self):

        calls = []
        confirmations = []

        def dangerous_command(command):

            calls.append(command)

            return ToolResult.ok(
                "THIS MUST NEVER EXECUTE"
            )

        def confirmation_callback(
            tool_name,
            arguments,
        ):

            confirmations.append(
                (
                    tool_name,
                    arguments,
                )
            )

            return False

        kuma = KumaAgent(
            model="qwen3:8b",
            tool_registry={
                "execute_command": dangerous_command,
            },
            confirmation_callback=confirmation_callback,
        )

        # Prevent Ollama from being required.
        def fake_model(messages):

            return type(
                "FakeResponse",
                (),
                {
                    "message": type(
                        "FakeMessage",
                        (),
                        {
                            "content": "",
                            "tool_calls": [
                                type(
                                    "FakeToolCall",
                                    (),
                                    {
                                        "function": type(
                                            "FakeFunction",
                                            (),
                                            {
                                                "name": (
                                                    "execute_command"
                                                ),
                                                "arguments": {
                                                    "command": (
                                                        "echo "
                                                        "SHOULD_NOT_EXECUTE"
                                                    )
                                                },
                                            },
                                        )(),
                                    },
                                )(),
                            ],
                        },
                    )(),
                },
            )()

        kuma.ask_model = fake_model

        result = kuma.run(
            "Run the command "
            "echo SHOULD_NOT_EXECUTE"
        )

        # Confirmation must have happened.
        self.assertEqual(
            len(confirmations),
            1,
        )

        self.assertEqual(
            confirmations[0][0],
            "execute_command",
        )

        self.assertEqual(
            confirmations[0][1]["command"],
            "echo SHOULD_NOT_EXECUTE",
        )

        # User denied it.
        self.assertIn(
            "denied",
            result.lower(),
        )

        # CRITICAL:
        # The dangerous tool must never execute.
        self.assertEqual(
            calls,
            [],
        )

    # =====================================================
    # CONFIRMATION — APPROVED
    # =====================================================

    def test_dangerous_action_approved_by_confirmation(self):

        calls = []
        confirmations = []

        def dangerous_command(command):

            calls.append(command)

            return ToolResult.ok(
                "APPROVED_EXECUTION"
            )

        def confirmation_callback(
            tool_name,
            arguments,
        ):

            confirmations.append(
                (
                    tool_name,
                    arguments,
                )
            )

            return True

        kuma = KumaAgent(
            model="qwen3:8b",
            tool_registry={
                "execute_command": dangerous_command,
            },
            confirmation_callback=confirmation_callback,
        )

        # Prevent Ollama from being required.
        def fake_model(messages):

            return type(
                "FakeResponse",
                (),
                {
                    "message": type(
                        "FakeMessage",
                        (),
                        {
                            "content": "",
                            "tool_calls": [
                                type(
                                    "FakeToolCall",
                                    (),
                                    {
                                        "function": type(
                                            "FakeFunction",
                                            (),
                                            {
                                                "name": (
                                                    "execute_command"
                                                ),
                                                "arguments": {
                                                    "command": (
                                                        "echo "
                                                        "APPROVED"
                                                    )
                                                },
                                            },
                                        )(),
                                    },
                                )(),
                            ],
                        },
                    )(),
                },
            )()

        kuma.ask_model = fake_model

        result = kuma.run(
            "Run the command echo APPROVED"
        )

        # Confirmation must have happened.
        self.assertEqual(
            len(confirmations),
            1,
        )

        # Tool must execute exactly once.
        self.assertEqual(
            calls,
            ["echo APPROVED"],
        )

        # Actual executor result must reach the user.
        self.assertIn(
            "APPROVED_EXECUTION",
            result,
        )

    def test_list_files_is_grounded_by_downloads_request(self):

        kuma = KumaAgent(
            tool_registry={}
        )

        self.assertTrue(
            kuma.explicitly_requests_tool_action(
                "Open the PDF in my Downloads folder and tell me what it contains.",
                "list_files",
                {
                    "folder": "Downloads"
                },
            )
        )

    def test_discovered_pdf_can_be_opened(self):

        kuma = KumaAgent(
            tool_registry={}
        )

        self.assertTrue(
            kuma.explicitly_requests_tool_action(
                "Open the PDF in my Downloads folder and tell me what it contains.",
                "open_file",
                {
                    "path": (
                        "/Users/test/Downloads/resume.pdf"
                    )
                },
            )
        )

    def test_unrelated_request_cannot_list_files(self):

        kuma = KumaAgent(
            tool_registry={}
        )

        self.assertFalse(
            kuma.explicitly_requests_tool_action(
                "Hello KUMA.",
                "list_files",
                {
                    "folder": "Downloads"
                },
            )
        )

    # =====================================================
    # CONFIRMATION — FAIL CLOSED
    # =====================================================

    def test_missing_confirmation_handler_denies_action(self):

        calls = []

        def dangerous_command(command):

            calls.append(command)

            return ToolResult.ok(
                "THIS MUST NEVER EXECUTE"
            )

        kuma = KumaAgent(
            model="qwen3:8b",
            tool_registry={
                "execute_command": dangerous_command,
            },
        )

        result = kuma.request_confirmation(
            "execute_command",
            {
                "command": "echo FAIL_CLOSED"
            },
        )

        self.assertFalse(
            result
        )

        self.assertEqual(
            calls,
            [],
        )

    # =====================================================
    # CONFIRMATION — CALLBACK FAILURE
    # =====================================================

    def test_confirmation_callback_failure_denies_action(self):

        calls = []

        def dangerous_command(command):

            calls.append(command)

            return ToolResult.ok(
                "THIS MUST NEVER EXECUTE"
            )

        def broken_confirmation(
            tool_name,
            arguments,
        ):

            raise RuntimeError(
                "confirmation system failure"
            )

        kuma = KumaAgent(
            model="qwen3:8b",
            tool_registry={
                "execute_command": dangerous_command,
            },
            confirmation_callback=broken_confirmation,
        )

        result = kuma.request_confirmation(
            "execute_command",
            {
                "command": "echo CALLBACK_FAILURE"
            },
        )

        self.assertFalse(
            result
        )

        self.assertEqual(
            calls,
            [],
        )

    def test_type_text_is_excluded_from_post_tool_reasoning(self):

        kuma = KumaAgent(
            model="test-model",
            tool_registry={
                "inspect_system": lambda: "SYSTEM_OK",
                "type_text": lambda text, interval=0.1: "TYPE_OK",
            },
        )

        messages = [
            {
                "role": "user",
                "content": (
                    "Inspect my system and tell me what you think "
                    "about its current state."
                ),
            },
            {
                "role": "tool",
                "content": "SYSTEM_OK",
            },
        ]

        tools = kuma.get_available_tools(
            messages
        )

        self.assertNotIn(
            kuma.tool_registry["type_text"],
            tools,
        )

    def test_type_text_remains_available_when_user_requests_typing(self):

        kuma = KumaAgent(
            model="test-model",
            tool_registry={
                "type_text": lambda text, interval=0.1: "TYPE_OK",
            },
        )

        messages = [
            {
                "role": "user",
                "content": "Type hello into the current app.",
            },
            {
                "role": "tool",
                "content": "Previous action completed.",
            },
        ]

        tools = kuma.get_available_tools(
            messages
        )

        self.assertIn(
            kuma.tool_registry["type_text"],
            tools,
        )

    # =====================================================
    # MULTI-STEP AGENT LOOP
    # =====================================================

    def test_multi_step_goal_completes_across_two_tools(self):

        calls = []

        def open_app(app_name):

            calls.append(
                ("open_app", app_name)
            )

            return ToolResult.ok(
                f"Opened {app_name} successfully."
            )

        def analyze_screen():

            calls.append(
                ("analyze_screen", None)
            )

            return ToolResult.ok(
                "The Chrome browser is visible on screen."
            )

        kuma = KumaAgent(
            model="test-model",
            tool_registry={
                "open_app": open_app,
                "analyze_screen": analyze_screen,
            },
            max_steps=5,
        )

        model_responses = [
            type(
                "FakeResponse",
                (),
                {
                    "message": type(
                        "FakeMessage",
                        (),
                        {
                            "content": "",
                            "tool_calls": [
                                type(
                                    "FakeToolCall",
                                    (),
                                    {
                                        "function": type(
                                            "FakeFunction",
                                            (),
                                            {
                                                "name": "open_app",
                                                "arguments": {
                                                    "app_name": "Chrome",
                                                },
                                            },
                                        )(),
                                    },
                                )(),
                            ],
                        },
                    )(),
                },
            )(),

            type(
                "FakeResponse",
                (),
                {
                    "message": type(
                        "FakeMessage",
                        (),
                        {
                            "content": "",
                            "tool_calls": [
                                type(
                                    "FakeToolCall",
                                    (),
                                    {
                                        "function": type(
                                            "FakeFunction",
                                            (),
                                            {
                                                "name": "analyze_screen",
                                                "arguments": {},
                                            },
                                        )(),
                                    },
                                )(),
                            ],
                        },
                    )(),
                },
            )(),

            type(
                "FakeResponse",
                (),
                {
                    "message": type(
                        "FakeMessage",
                        (),
                        {
                            "content": (
                                "Chrome is open and visible "
                                "on the screen."
                            ),
                            "tool_calls": [],
                        },
                    )(),
                },
            )(),
        ]

        response_index = {"value": 0}

        def fake_ask_model(messages):

            index = response_index["value"]
            response_index["value"] += 1

            return model_responses[index]

        kuma.ask_model = fake_ask_model

        goal_decisions = []

        def fake_goal_decision(messages):

            decision = GoalDecision(
                status=GoalStatus.CONTINUE,
                remaining_objective=(
                    "Tell the user what is visible "
                    "on the screen."
                ),
                next_action="analyze_screen",
                reason=(
                    "Chrome was opened successfully, "
                    "but the screen still needs to be "
                    "observed."
                ),
            )

            goal_decisions.append(decision)

            return decision, None

        kuma.ask_goal_decision = fake_goal_decision

        result = kuma.run(
            "Open Chrome and then tell me "
            "what is on the screen."
        )

        self.assertEqual(
            calls,
            [
                ("open_app", "Chrome"),
                ("analyze_screen", None),
            ],
        )

        self.assertEqual(
            len(goal_decisions),
            1,
        )

        self.assertEqual(
            goal_decisions[0].status,
            GoalStatus.CONTINUE,
        )

        self.assertIn(
            "Chrome",
            result,
        )

        self.assertIn(
            "screen",
            result.lower(),
        )

        self.assertEqual(
            response_index["value"],
            3,
        )

    # =====================================================
    # TOOL ARGUMENT NORMALIZATION
    # =====================================================

    def test_list_files_path_alias_is_normalized_to_folder(self):

        normalized = KumaAgent.normalize_tool_arguments(
            "Open the PDF in my Downloads folder.",
            "list_files",
            {
                "path": "~/Downloads",
            },
        )

        self.assertEqual(
            normalized,
            {
                "folder": "~/Downloads",
            },
        )


if __name__ == "__main__":
    unittest.main(
        verbosity=2
    )
