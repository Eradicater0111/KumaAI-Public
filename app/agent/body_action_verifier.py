from __future__ import annotations

from app.agent.body_button_state import (
    BODY_BUTTON_CLEAR,
    BODY_BUTTON_HELD,
    BODY_MOUSE_BUTTONS,
)


FINGER_BODY_STATE_TOOLS = frozenset(
    {
        "hold_mouse",
        "hold_mouse_vision",
        "release_mouse",
    }
)


def verify_body_action_postcondition(
    *,
    tool_name: object,
    arguments: object,
) -> tuple[bool, str]:
    """
    Verify one live process-local finger postcondition.

    Observation only:
    - no physical input
    - no permission grant
    - no execution authority
    - no reconstruction of physical state from planner data
    """

    if (
        type(tool_name) is not str
        or tool_name
        not in FINGER_BODY_STATE_TOOLS
    ):
        return (
            False,
            "Unknown finger-state action.",
        )

    if type(arguments) is not dict:
        return (
            False,
            "Finger-state verification requires "
            "normalized arguments.",
        )

    from app.agent.body_button_state import (
        BODY_BUTTON_STATE,
    )

    try:

        state = (
            BODY_BUTTON_STATE.snapshot()
        )

    except BaseException as error:

        return (
            False,
            "Could not inspect live KUMA finger state: "
            f"{type(error).__name__}: {error}",
        )

    if tool_name in {
        "hold_mouse",
        "hold_mouse_vision",
    }:

        button = arguments.get(
            "button",
            "left",
        )

        if (
            type(button) is not str
            or button not in BODY_MOUSE_BUTTONS
        ):
            return (
                False,
                "Hold postcondition has no exact valid "
                "button identity.",
            )

        if (
            state.status
            == BODY_BUTTON_HELD
            and state.button
            == button
        ):
            return (
                True,
                "KUMA body verification: exact mouse button "
                f"{button!r} is HELD.",
            )

        return (
            False,
            "KUMA body verification expected "
            f"HELD({button!r}) but observed "
            f"{state.status}({state.button!r}).",
        )

    # release_mouse has an exact zero-argument contract.
    if arguments:
        return (
            False,
            "Release postcondition rejects model-supplied "
            "button arguments.",
        )

    if (
        state.status
        == BODY_BUTTON_CLEAR
        and state.button is None
    ):
        return (
            True,
            "KUMA body verification: mouse-button state "
            "is CLEAR.",
        )

    return (
        False,
        "KUMA body verification expected CLEAR but observed "
        f"{state.status}({state.button!r}).",
    )
