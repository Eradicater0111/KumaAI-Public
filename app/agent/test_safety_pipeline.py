import unittest

from app.agent.executor import ActionExecutor
from app.agent.permissions import (
    PermissionLevel,
    TOOL_PERMISSIONS,
    get_permission_level,
    has_explicit_permission,
    require_explicit_permission,
)
from app.agent.capability_registry import (
    create_default_capability_registry,
)
from app.agent.tool_registry import KUMA_TOOLS
from app.agent.tool_result import ToolResult
from app.agent.verifier import verify_result


class TestKumaSafetyPipeline(unittest.TestCase):
    """Fast regression tests for KUMA's permission/execution/verification layer."""

    # =====================================================
    # SAFE TOOL
    # =====================================================

    def test_safe_tool_executes_successfully(self):

        registry = {
            "list_files": lambda: ToolResult.ok("SAFE_OK"),
        }

        executor = ActionExecutor(registry)

        result = executor.execute(
            "list_files",
            {},
        )

        self.assertTrue(result.success)
        self.assertEqual(result.result, "SAFE_OK")
        self.assertIsNone(result.error)
        self.assertFalse(result.requires_confirmation)

    # =====================================================
    # STRUCTURED FAILURE
    # =====================================================

    def test_structured_tool_failure_is_preserved(self):

        # Use an explicitly classified SAFE tool identity.
        # This test covers structured ToolResult failure
        # preservation, not unknown permission handling.
        registry = {
            "open_file": lambda: ToolResult.fail(
                "EXPECTED_FAILURE"
            ),
        }

        executor = ActionExecutor(registry)

        result = executor.execute(
            "open_file",
            {},
        )

        self.assertFalse(result.success)
        self.assertIsNone(result.result)
        self.assertEqual(
            result.error,
            "EXPECTED_FAILURE",
        )

    # =====================================================
    # UNKNOWN TOOL
    # =====================================================

    def test_unknown_tool_is_rejected(self):

        executor = ActionExecutor({})

        result = executor.execute(
            "does_not_exist",
            {},
        )

        self.assertFalse(result.success)
        self.assertIn(
            "Unknown tool",
            result.error,
        )

    # =====================================================
    # DANGEROUS TOOL — CONFIRMATION REQUIRED
    # =====================================================

    def test_dangerous_tool_requires_confirmation(self):

        calls = []

        def dangerous_test():

            calls.append("EXECUTED")

            return ToolResult.ok(
                "SHOULD_NOT_RUN"
            )

        registry = {
            "execute_command": dangerous_test,
        }

        executor = ActionExecutor(
            registry
        )

        result = executor.execute(
            "execute_command",
            {},
            approved=False,
        )

        self.assertFalse(
            result.success
        )

        self.assertTrue(
            result.requires_confirmation
        )

        self.assertIn(
            "Confirmation required",
            result.error,
        )

        # Critical safety assertion:
        # The dangerous tool must NEVER
        # have been called.

        self.assertEqual(
            calls,
            [],
        )

    # =====================================================
    # DANGEROUS TOOL — APPROVED
    # =====================================================

    def test_dangerous_tool_executes_after_approval(self):

        calls = []

        def dangerous_test():

            calls.append("EXECUTED")

            return ToolResult.ok(
                "DANGEROUS_OK"
            )

        # IMPORTANT:
        # "dangerous_test" is not automatically dangerous
        # unless it is registered as a dangerous tool.
        #
        # Therefore use execute_command, which is already
        # classified as DANGEROUS by permissions.py.

        registry = {
            "execute_command": dangerous_test,
        }

        executor = ActionExecutor(
            registry
        )

        result = executor.execute(
            "execute_command",
            {},
            approved=True,
        )

        self.assertTrue(
            result.success
        )

        self.assertEqual(
            result.result,
            "DANGEROUS_OK",
        )

        self.assertEqual(
            calls,
            ["EXECUTED"],
        )

    # =====================================================
    # EXECUTOR EXCEPTION
    # =====================================================

    def test_executor_exception_becomes_failure(self):

        def broken_test():

            raise RuntimeError(
                "BOOM"
            )

        executor = ActionExecutor(
            {
                "open_app": broken_test,
            }
        )

        result = executor.execute(
            "open_app",
            {},
        )

        self.assertFalse(
            result.success
        )

        self.assertIsNone(
            result.result
        )

        self.assertIn(
            "BOOM",
            result.error,
        )

    # =====================================================
    # PERMISSION CLASSIFICATION
    # =====================================================

    def test_execute_command_is_dangerous(self):

        self.assertEqual(
            get_permission_level(
                "execute_command"
            ),
            PermissionLevel.DANGEROUS,
        )

    def test_unclassified_tool_is_rejected_at_registration_boundary(self):

        self.assertFalse(
            has_explicit_permission(
                "future_unclassified_tool"
            )
        )

        with self.assertRaises(ValueError):
            require_explicit_permission(
                "future_unclassified_tool"
            )

    def test_missing_or_malformed_permission_identity_fails_closed(self):

        for tool_name in (None, "", "   ", 42, True):
            with self.subTest(tool_name=tool_name):
                self.assertEqual(
                    get_permission_level(tool_name),
                    PermissionLevel.DANGEROUS,
                )

    def test_forget_has_explicit_permission_classification(self):

        self.assertEqual(
            TOOL_PERMISSIONS.get("forget"),
            PermissionLevel.USER_AUTHORIZED,
        )

    def test_every_registered_kuma_tool_has_explicit_permission(self):

        missing = sorted(
            set(KUMA_TOOLS)
            - set(TOOL_PERMISSIONS)
        )

        self.assertEqual(missing, [])

    def test_every_capability_tool_has_explicit_permission(self):

        registry = create_default_capability_registry()

        capability_tools = {
            tool_name
            for capability in registry.all()
            for tool_name in capability.tools
        }

        missing = sorted(
            capability_tools
            - set(TOOL_PERMISSIONS)
        )

        self.assertEqual(missing, [])

    # =====================================================
    # VERIFIER — EXECUTOR FAILURE
    # =====================================================

    def test_verifier_respects_executor_failure(self):

        self.assertFalse(
            verify_result(
                "execute_command",
                "Everything worked.",
                execution_success=False,
            )
        )

    # =====================================================
    # VERIFIER — EXECUTOR SUCCESS
    # =====================================================

    def test_verifier_accepts_executor_success(self):

        self.assertTrue(
            verify_result(
                "execute_command",
                "Everything worked.",
                execution_success=True,
            )
        )

    # =====================================================
    # VERIFIER — FAILURE TEXT
    # =====================================================

    def test_verifier_detects_failure_text(self):

        self.assertFalse(
            verify_result(
                "open_file",
                "I couldn't find /real/file.",
            )
        )

    # =====================================================
    # VERIFIER — SUCCESS TEXT
    # =====================================================

    def test_verifier_accepts_success_text(self):

        self.assertTrue(
            verify_result(
                "open_file",
                "Opened test.txt successfully.",
            )
        )

    # =====================================================
    # END-TO-END SAFETY — DENIED ACTION MUST NOT EXECUTE
    # =====================================================

    def test_dangerous_action_denied_never_reaches_tool(self):

        calls = []

        def dangerous_command(command):

            calls.append(command)

            return ToolResult.ok(
                "THIS MUST NEVER BE RETURNED"
            )

        executor = ActionExecutor(
            {
                "execute_command": dangerous_command,
            }
        )

        result = executor.execute(
            "execute_command",
            {
                "command": "echo SHOULD_NOT_EXECUTE"
            },
            approved=False,
        )

        # Executor must reject the action.
        self.assertFalse(
            result.success
        )

        # Confirmation must be required.
        self.assertTrue(
            result.requires_confirmation
        )

        # Most important safety assertion:
        # the actual dangerous tool was NEVER called.
        self.assertEqual(
            calls,
            [],
        )


    # =====================================================
    # END-TO-END SAFETY — APPROVED ACTION EXECUTES ONCE
    # =====================================================

    def test_dangerous_action_approved_executes_once(self):

        calls = []

        def dangerous_command(command):

            calls.append(command)

            return ToolResult.ok(
                "EXECUTION_CONFIRMED"
            )

        executor = ActionExecutor(
            {
                "execute_command": dangerous_command,
            }
        )

        result = executor.execute(
            "execute_command",
            {
                "command": "echo APPROVED"
            },
            approved=True,
        )

        # Execution must succeed.
        self.assertTrue(
            result.success
        )

        # Correct result must be preserved.
        self.assertEqual(
            result.result,
            "EXECUTION_CONFIRMED",
        )

        # The dangerous tool must execute exactly once.
        self.assertEqual(
            calls,
            ["echo APPROVED"],
        )


    # =====================================================
    # END-TO-END SAFETY — FAILED DANGEROUS TOOL
    # =====================================================

    def test_dangerous_action_failure_is_preserved(self):

        calls = []

        def dangerous_command(command):

            calls.append(command)

            return ToolResult.fail(
                "COMMAND_FAILED"
            )

        executor = ActionExecutor(
            {
                "execute_command": dangerous_command,
            }
        )

        result = executor.execute(
            "execute_command",
            {
                "command": "echo FAILURE"
            },
            approved=True,
        )

        # Tool was actually reached.
        self.assertEqual(
            calls,
            ["echo FAILURE"],
        )

        # But the executor must preserve the failure.
        self.assertFalse(
            result.success
        )

        self.assertIsNone(
            result.result
        )

        self.assertEqual(
            result.error,
            "COMMAND_FAILED",
        )

if __name__ == "__main__":
    unittest.main(
        verbosity=2
    )