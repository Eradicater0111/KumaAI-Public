from __future__ import annotations

from app.agent.body_button_state import (
    BODY_BUTTON_CLEAR,
    BODY_BUTTON_STATE,
)

from app.agent.tool_result import (
    ToolResult,
)

from app.tools.computer_tools import (
    release_mouse,
)


# =========================================================
# NORMAL PROCESS SHUTDOWN
# =========================================================

def release_owned_mouse_button_for_shutdown() -> ToolResult:
    """
    Best-effort normal-shutdown cleanup for KUMA-owned finger state.

    This is a lifecycle boundary, not a planner/runtime tool.

    Safety contract:
    - accepts no button argument
    - never invents a button identity
    - never directly sets body state to CLEAR
    - HELD/UNKNOWN may become CLEAR only through release_mouse()
    - failed release leaves the live state HELD or UNKNOWN
    - shutdown interruptions are reported as cleanup failure after
      release_mouse() has already performed its fail-closed repair

    This cannot guarantee cleanup after SIGKILL, host termination,
    power loss, or other process death that prevents Python code
    from running.
    """

    try:

        before = (
            BODY_BUTTON_STATE.snapshot()
        )

    except BaseException as error:

        return ToolResult.fail(
            "Could not inspect KUMA-owned mouse-button state "
            "during shutdown: "
            f"{type(error).__name__}: {error}"
        )

    if (
        before.status
        == BODY_BUTTON_CLEAR
    ):
        return ToolResult.ok(
            "KUMA-owned mouse-button state is already CLEAR."
        )

    button = before.button

    if button is None:
        return ToolResult.fail(
            "KUMA shutdown found non-CLEAR mouse-button state "
            "without an exact button identity."
        )

    try:

        release_result = (
            release_mouse()
        )

    except BaseException as error:

        try:
            after = (
                BODY_BUTTON_STATE.snapshot()
            )

            state_description = (
                f"{after.status}"
                f"({after.button!r})"
            )

        except BaseException:
            state_description = (
                "<unreadable>"
            )

        return ToolResult.fail(
            "KUMA shutdown mouse release was interrupted after "
            "fail-closed body-state handling: "
            f"{type(error).__name__}: {error}. "
            "Current state: "
            f"{state_description}."
        )

    try:

        after = (
            BODY_BUTTON_STATE.snapshot()
        )

    except BaseException as error:

        return ToolResult.fail(
            "Mouse release returned, but KUMA could not inspect "
            "the final shutdown button state: "
            f"{type(error).__name__}: {error}"
        )

    if (
        release_result.success
        and after.status
        == BODY_BUTTON_CLEAR
        and after.button is None
    ):
        return ToolResult.ok(
            "Released KUMA-owned mouse button "
            f"{button!r} for shutdown."
        )

    detail = (
        release_result.error
        or "Mouse release did not establish CLEAR state."
    )

    return ToolResult.fail(
        "KUMA could not safely release its owned mouse button "
        "during shutdown. "
        f"{detail} "
        "Current state: "
        f"{after.status}({after.button!r})."
    )
