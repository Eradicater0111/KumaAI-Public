from typing import Any

from app.agent.permissions import (
    PermissionLevel,
    get_permission_level,
)

from app.agent.tool_result import ToolResult


# =========================================================
# ACTION RESULT
# =========================================================

class ActionResult:
    """
    Normalized result produced by the KUMA action executor.

    This is the authoritative execution result passed
    from the tool layer to the agent/verifier layer.
    """

    def __init__(
        self,
        tool: str,
        success: bool,
        result: Any = None,
        error: str | None = None,
        requires_confirmation: bool = False,
        effect_started: bool = False,
    ):

        if type(effect_started) is not bool:
            raise TypeError(
                "effect_started must be a boolean."
            )

        self.tool = tool
        self.success = success
        self.result = result
        self.error = error
        self.requires_confirmation = (
            requires_confirmation
        )
        self.effect_started = (
            effect_started
        )

    # =====================================================
    # SUCCESS FACTORY
    # =====================================================

    @classmethod
    def ok(
        cls,
        tool: str,
        result: Any = None,
        *,
        effect_started: bool = False,
    ):

        return cls(
            tool=tool,
            success=True,
            result=result,
            effect_started=effect_started,
        )

    # =====================================================
    # FAILURE FACTORY
    # =====================================================

    @classmethod
    def fail(
        cls,
        tool: str,
        error: str,
        requires_confirmation: bool = False,
        *,
        effect_started: bool = False,
    ):

        return cls(
            tool=tool,
            success=False,
            error=error,
            requires_confirmation=(
                requires_confirmation
            ),
            effect_started=effect_started,
        )

    # =====================================================
    # SERIALIZATION
    # =====================================================

    def to_dict(self):

        return {
            "tool": self.tool,
            "success": self.success,
            "result": self.result,
            "error": self.error,
            "requires_confirmation": (
                self.requires_confirmation
            ),
            "effect_started": (
                self.effect_started
            ),
        }
    

    # =====================================================
    # STRING REPRESENTATION
    # =====================================================

    def __str__(self):

        if self.success:

            return str(
                self.result
                if self.result is not None
                else ""
            )

        return str(
            self.error
            if self.error
            else "Tool execution failed."
        )


# =========================================================
# ACTION EXECUTOR
# =========================================================

class ActionExecutor:
    """
    Executes registered KUMA tools while enforcing the
    permission layer and normalizing tool results.
    """

    def __init__(
        self,
        tool_registry: dict[str, Any] | None = None,
    ):

        self.tool_registry = (
            tool_registry or {}
        )

    # =====================================================
    # REGISTER TOOL
    # =====================================================

    def register_tool(
        self,
        name: str,
        function,
    ):

        self.tool_registry[name] = function

    # =====================================================
    # EXECUTE
    # =====================================================

    def execute(
        self,
        tool_name: str,
        arguments: dict | None = None,
        approved: bool = False,
    ) -> ActionResult:

        # -------------------------------------------------
        # NORMALIZE ARGUMENTS
        # -------------------------------------------------

        if arguments is None:

            arguments = {}

        if not isinstance(arguments, dict):

            return ActionResult.fail(
                tool=tool_name,
                error=(
                    "Tool arguments must be "
                    "provided as a dictionary."
                ),
            )

        # -------------------------------------------------
        # TOOL EXISTENCE
        # -------------------------------------------------

        tool = self.tool_registry.get(
            tool_name
        )

        if tool is None:

            return ActionResult.fail(
                tool=tool_name,
                error=(
                    f"Unknown tool: "
                    f"{tool_name}"
                ),
            )

        # -------------------------------------------------
        # PERMISSION
        # -------------------------------------------------

        permission = get_permission_level(
            tool_name
        )

        # -------------------------------------------------
        # DANGEROUS ACTION
        # -------------------------------------------------

        if permission == PermissionLevel.DANGEROUS:

            if not approved:

                return ActionResult.fail(
                    tool=tool_name,
                    error=(
                        f"Confirmation required "
                        f"before executing "
                        f"'{tool_name}'."
                    ),
                    requires_confirmation=True,
                )

        # -------------------------------------------------
        # EXECUTE TOOL
        # -------------------------------------------------

        try:

            raw_result = tool(
                **arguments
            )

        except Exception as error:

            return ActionResult.fail(
                tool=tool_name,
                error=(
                    f"Tool execution failed: "
                    f"{error}"
                ),
            )

        # -------------------------------------------------
        # STRUCTURED TOOL RESULT
        # -------------------------------------------------

        if isinstance(
            raw_result,
            ToolResult,
        ):

            if raw_result.success:

                return ActionResult.ok(
                    tool=tool_name,
                    result=raw_result.result,
                    effect_started=(
                        raw_result.effect_started
                        is True
                    ),
                )

            return ActionResult.fail(
                tool=tool_name,
                error=(
                    raw_result.error
                    or "Tool reported failure."
                ),
                effect_started=(
                    raw_result.effect_started
                    is True
                ),
            )

        # -------------------------------------------------
        # LEGACY TOOL RESULT
        # -------------------------------------------------

        return ActionResult.ok(
            tool=tool_name,
            result=raw_result,
        )
    # =====================================================
    # TRUSTED FOCUSED TEXT EXECUTION
    # =====================================================

    def execute_focused_text(
        self,
        receipt,
        approved: bool = False,
    ) -> ActionResult:
        """
        Execute trusted focused typing without caller-supplied text.

        The logical/public tool remains ``type_text``.

        This private execution lane bypasses the registered
        ``type_text(text=...)`` callable and invokes only
        ``type_text_focused(receipt)``.

        It does not accept arbitrary arguments or a text payload.
        """

        tool_name = "type_text"

        # Logical type_text registration must still exist.
        if (
            self.tool_registry.get(
                tool_name
            )
            is None
        ):
            return ActionResult.fail(
                tool=tool_name,
                error=(
                    "Unknown tool: "
                    f"{tool_name}"
                ),
            )

        # Require the exact trusted receipt type.
        try:
            from app.agent.focused_text_receipt import (
                FocusedTextReceipt,
            )
        except Exception as error:
            return ActionResult.fail(
                tool=tool_name,
                error=(
                    "Focused typing trust boundary "
                    f"is unavailable: {error}"
                ),
            )

        if (
            type(receipt)
            is not FocusedTextReceipt
        ):
            return ActionResult.fail(
                tool=tool_name,
                error=(
                    "Focused typing requires the exact "
                    "trusted focused-text receipt."
                ),
            )

        # Preserve the existing permission contract.
        permission = get_permission_level(
            tool_name
        )

        if (
            permission
            == PermissionLevel.DANGEROUS
            and not approved
        ):
            return ActionResult.fail(
                tool=tool_name,
                error=(
                    "Confirmation required before "
                    "executing 'type_text'."
                ),
                requires_confirmation=True,
            )

        # Private physical bridge.
        try:
            from app.tools.computer_tools import (
                type_text_focused,
            )

            raw_result = (
                type_text_focused(
                    receipt
                )
            )

        except Exception as error:
            return ActionResult.fail(
                tool=tool_name,
                error=(
                    "Focused text execution failed "
                    "before a structured result was returned: "
                    f"{error}"
                ),
            )

        if not isinstance(
            raw_result,
            ToolResult,
        ):
            return ActionResult.fail(
                tool=tool_name,
                error=(
                    "Focused text execution returned "
                    "an invalid physical result."
                ),
            )

        if raw_result.success:
            return ActionResult.ok(
                tool=tool_name,
                result=raw_result.result,
                effect_started=(
                    raw_result.effect_started
                    is True
                ),
            )

        return ActionResult.fail(
            tool=tool_name,
            error=(
                raw_result.error
                or "Focused text execution failed."
            ),
            effect_started=(
                raw_result.effect_started
                is True
            ),
        )


    def execute_trusted_key(
        self,
        receipt,
        approved: bool = False,
    ) -> ActionResult:
        """
        Execute one trusted keyboard-key receipt.

        The logical/public tool remains ``press_key``.

        This lane accepts no caller-supplied key and invokes only
        the private ``press_key_trusted(receipt)`` bridge.
        """

        tool_name = "press_key"

        # Logical press_key registration must still exist.
        if (
            self.tool_registry.get(
                tool_name
            )
            is None
        ):
            return ActionResult.fail(
                tool=tool_name,
                error=(
                    "Unknown tool: "
                    f"{tool_name}"
                ),
            )

        try:
            from app.agent.trusted_key_receipt import (
                TrustedKeyReceipt,
            )
        except Exception as error:
            return ActionResult.fail(
                tool=tool_name,
                error=(
                    "Trusted key boundary is unavailable: "
                    f"{error}"
                ),
            )

        if (
            type(receipt)
            is not TrustedKeyReceipt
        ):
            return ActionResult.fail(
                tool=tool_name,
                error=(
                    "Trusted key execution requires the exact "
                    "single-use key receipt."
                ),
            )

        permission = get_permission_level(
            tool_name
        )

        if (
            permission
            == PermissionLevel.DANGEROUS
            and not approved
        ):
            return ActionResult.fail(
                tool=tool_name,
                error=(
                    "Confirmation required before "
                    "executing 'press_key'."
                ),
                requires_confirmation=True,
            )

        try:
            from app.tools.computer_tools import (
                press_key_trusted,
            )

            raw_result = (
                press_key_trusted(
                    receipt
                )
            )

        except Exception as error:
            return ActionResult.fail(
                tool=tool_name,
                error=(
                    "Trusted key execution failed before "
                    "a structured result was returned: "
                    f"{error}"
                ),
            )

        if not isinstance(
            raw_result,
            ToolResult,
        ):
            return ActionResult.fail(
                tool=tool_name,
                error=(
                    "Trusted key execution returned "
                    "an invalid physical result."
                ),
            )

        if raw_result.success:
            return ActionResult.ok(
                tool=tool_name,
                result=raw_result.result,
                effect_started=(
                    raw_result.effect_started
                    is True
                ),
            )

        return ActionResult.fail(
            tool=tool_name,
            error=(
                raw_result.error
                or "Trusted key execution failed."
            ),
            effect_started=(
                raw_result.effect_started
                is True
            ),
        )


    def execute_trusted_scroll(
        self,
        receipt,
        approved: bool = False,
    ) -> ActionResult:
        """Execute trusted scrolling without caller-supplied amount."""

        tool_name = "scroll"

        if (
            self.tool_registry.get(
                tool_name
            )
            is None
        ):
            return ActionResult.fail(
                tool=tool_name,
                error=f"Unknown tool: {tool_name}",
            )

        try:
            from app.agent.trusted_scroll_receipt import (
                TrustedScrollReceipt,
            )
        except Exception as error:
            return ActionResult.fail(
                tool=tool_name,
                error=(
                    "Trusted scroll boundary unavailable: "
                    f"{error}"
                ),
            )

        if (
            type(receipt)
            is not TrustedScrollReceipt
        ):
            return ActionResult.fail(
                tool=tool_name,
                error=(
                    "Trusted scroll requires the exact "
                    "single-use receipt."
                ),
            )

        permission = get_permission_level(
            tool_name
        )

        if (
            permission
            == PermissionLevel.DANGEROUS
            and not approved
        ):
            return ActionResult.fail(
                tool=tool_name,
                error=(
                    "Confirmation required before "
                    "executing 'scroll'."
                ),
                requires_confirmation=True,
            )

        try:
            from app.tools.computer_tools import (
                scroll_trusted,
            )

            raw_result = scroll_trusted(
                receipt
            )

        except Exception as error:
            return ActionResult.fail(
                tool=tool_name,
                error=(
                    "Trusted scroll failed before a "
                    "structured result was returned: "
                    f"{error}"
                ),
            )

        if not isinstance(
            raw_result,
            ToolResult,
        ):
            return ActionResult.fail(
                tool=tool_name,
                error=(
                    "Trusted scroll returned an invalid "
                    "physical result."
                ),
            )

        if raw_result.success:
            return ActionResult.ok(
                tool=tool_name,
                result=raw_result.result,
                effect_started=(
                    raw_result.effect_started is True
                ),
            )

        return ActionResult.fail(
            tool=tool_name,
            error=(
                raw_result.error
                or "Trusted scroll failed."
            ),
            effect_started=(
                raw_result.effect_started is True
            ),
        )


    def _execute_trusted_mouse_receipt(
        self,
        *,
        receipt,
        logical_tool,
        receipt_type,
        bridge,
        approved,
    ) -> ActionResult:
        if self.tool_registry.get(logical_tool) is None:
            return ActionResult.fail(
                tool=logical_tool,
                error=f"Unknown tool: {logical_tool}",
            )

        if type(receipt) is not receipt_type:
            return ActionResult.fail(
                tool=logical_tool,
                error=(
                    f"Trusted {logical_tool} requires "
                    "the exact receipt type."
                ),
            )

        permission = get_permission_level(
            logical_tool
        )

        if (
            permission == PermissionLevel.DANGEROUS
            and not approved
        ):
            return ActionResult.fail(
                tool=logical_tool,
                error=(
                    "Confirmation required before "
                    f"executing '{logical_tool}'."
                ),
                requires_confirmation=True,
            )

        try:
            raw_result = bridge(
                receipt
            )
        except Exception as error:
            return ActionResult.fail(
                tool=logical_tool,
                error=(
                    f"Trusted {logical_tool} failed before "
                    f"a structured result was returned: {error}"
                ),
            )

        if not isinstance(
            raw_result,
            ToolResult,
        ):
            return ActionResult.fail(
                tool=logical_tool,
                error=(
                    f"Trusted {logical_tool} returned "
                    "an invalid physical result."
                ),
            )

        if raw_result.success:
            return ActionResult.ok(
                tool=logical_tool,
                result=raw_result.result,
                effect_started=(
                    raw_result.effect_started is True
                ),
            )

        return ActionResult.fail(
            tool=logical_tool,
            error=raw_result.error,
            effect_started=(
                raw_result.effect_started is True
            ),
        )


    def execute_trusted_hold_mouse(
        self,
        receipt,
        approved: bool = False,
    ) -> ActionResult:
        from app.agent.trusted_mouse_button_receipt import (
            TrustedMouseHoldReceipt,
        )
        from app.tools.computer_tools import (
            hold_mouse_trusted,
        )

        return self._execute_trusted_mouse_receipt(
            receipt=receipt,
            logical_tool="hold_mouse",
            receipt_type=TrustedMouseHoldReceipt,
            bridge=hold_mouse_trusted,
            approved=approved,
        )


    def execute_trusted_hold_mouse_vision(
        self,
        receipt,
        approved: bool = False,
    ) -> ActionResult:
        from app.agent.trusted_semantic_hold_receipt import (
            TrustedSemanticHoldReceipt,
        )
        from app.tools.computer_tools import (
            hold_mouse_vision_trusted,
        )

        return self._execute_trusted_mouse_receipt(
            receipt=receipt,
            logical_tool="hold_mouse_vision",
            receipt_type=TrustedSemanticHoldReceipt,
            bridge=hold_mouse_vision_trusted,
            approved=approved,
        )


    def execute_trusted_release_mouse(
        self,
        receipt,
        approved: bool = False,
    ) -> ActionResult:
        from app.agent.trusted_mouse_button_receipt import (
            TrustedMouseReleaseReceipt,
        )
        from app.tools.computer_tools import (
            release_mouse_trusted,
        )

        return self._execute_trusted_mouse_receipt(
            receipt=receipt,
            logical_tool="release_mouse",
            receipt_type=TrustedMouseReleaseReceipt,
            bridge=release_mouse_trusted,
            approved=approved,
        )
