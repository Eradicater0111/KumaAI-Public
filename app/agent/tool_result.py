# =========================================================
# STRUCTURED TOOL RESULT
# =========================================================

class ToolResult:

    def __init__(
        self,
        success: bool,
        result=None,
        error=None,
        effect_started: bool = False,
    ):
        if type(effect_started) is not bool:
            raise TypeError(
                "effect_started must be a boolean."
            )

        self.success = success
        self.result = result
        self.error = error
        self.effect_started = effect_started

    # -----------------------------------------------------
    # SUCCESS
    # -----------------------------------------------------

    @classmethod
    def ok(
        cls,
        result=None,
        *,
        effect_started: bool = False,
    ):
        return cls(
            success=True,
            result=result,
            effect_started=effect_started,
        )

    # -----------------------------------------------------
    # FAILURE
    # -----------------------------------------------------

    @classmethod
    def fail(
        cls,
        error,
        *,
        effect_started: bool = False,
    ):
        return cls(
            success=False,
            error=error,
            effect_started=effect_started,
        )

    # -----------------------------------------------------
    # STRING REPRESENTATION
    # -----------------------------------------------------

    def __str__(self):

        if self.success:
            return str(
                self.result
                if self.result is not None
                else ""
            )

        return str(
            self.error
            if self.error is not None
            else "Tool execution failed."
        )