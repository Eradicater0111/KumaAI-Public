# =========================================================
# VERIFY ACTION RESULT
# =========================================================

def verify_result(
    tool_name: str,
    result,
    execution_success: bool = None,
) -> bool:
    """
    Verify whether a tool action succeeded.

    The executor success flag is the primary source
    of truth.

    Result-content inspection is only a compatibility
    fallback for older tools.
    """

    # -----------------------------------------------------
    # STRUCTURED EXECUTION RESULT
    # -----------------------------------------------------

    if execution_success is not None:
        return execution_success

    # -----------------------------------------------------
    # NO RESULT
    # -----------------------------------------------------

    if result is None:
        return False

    # -----------------------------------------------------
    # LEGACY FALLBACK
    # -----------------------------------------------------

    if isinstance(result, str):

        normalized = result.strip().lower()

        if not normalized:
            return False

        failure_markers = (
            "tool error:",
            "error:",
            "could not",
            "couldn't",
            "failed",
            "failure",
            "does not exist",
            "doesn't exist",
            "not found",
            "cannot open",
            "can't open",
            "unable to",
            "i couldn't find",
            "i could not find",
        )

        if normalized.startswith(failure_markers):
            return False

    return True


# =========================================================
# VERIFICATION REPORT
# =========================================================

def verification_report(
    tool_name: str,
    result,
    execution_success: bool = None,
) -> str:
    """
    Generate a human-readable verification report.
    """

    verified = verify_result(
        tool_name=tool_name,
        result=result,
        execution_success=execution_success,
    )

    if verified:

        return (
            f"KUMA verified that "
            f"'{tool_name}' completed successfully."
        )

    return (
        f"KUMA could not verify "
        f"'{tool_name}' successfully."
    )