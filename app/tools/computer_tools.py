import math
import time

import pyautogui

from app.agent.tool_result import ToolResult

from app.vision.coordinates import CoordinateMapper, CoordinateMappingError


# =========================================================
# PHYSICAL BODY SAFETY CONTRACT
# =========================================================

MAX_MOUSE_MOVE_DURATION_SECONDS = 2.0
MAX_CLICK_COUNT = 2

MAX_TYPE_TEXT_CHARACTERS = 4096
MAX_TYPE_INTERVAL_SECONDS = 0.25
MAX_TYPE_ACTION_DURATION_SECONDS = 30.0

MAX_SCROLL_UNITS = 20

PYAUTOGUI_PAUSE_SECONDS = 0.1

# Final physical-boundary desktop revalidation is deliberately independent
# from MissionService's earlier A6-1 gate. Both must fail closed.
PHYSICAL_DESKTOP_REVALIDATION_TIMEOUT_SECONDS = 2.0
PHYSICAL_DESKTOP_REVALIDATION_MAX_WINDOWS = 32
PHYSICAL_DESKTOP_REVALIDATION_MAX_AGE_SECONDS = 2.0

SUPPORTED_MOUSE_BUTTONS = frozenset(
    {
        "left",
        "right",
        "middle",
    }
)

SUPPORTED_KEYBOARD_KEYS = frozenset(
    str(key).strip().lower()
    for key in (
        getattr(
            pyautogui,
            "KEYBOARD_KEYS",
            (),
        )
        or ()
    )
    if str(key).strip()
)


def _finite_number(
    value,
) -> bool:
    return (
        not isinstance(
            value,
            bool,
        )
        and isinstance(
            value,
            (int, float),
        )
        and math.isfinite(
            float(value)
        )
    )


def _enforce_pyautogui_safety() -> None:
    """
    Preserve KUMA's host-level emergency stop.

    PyAutoGUI FAILSAFE must remain enabled whenever KUMA
    performs a physical desktop action.

    A deterministic global pause is restored so automated
    input cannot silently become either an uncontrolled
    zero-delay stream or a pathologically stalled action.
    """

    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = (
        PYAUTOGUI_PAUSE_SECONDS
    )


# Establish the intended host safety policy at import time.
_enforce_pyautogui_safety()


# =========================================================
# POINTER / FINGER INTERLOCK
# =========================================================

def _pointer_button_block_reason(
    action_label: str,
) -> str | None:
    """
    Read-only early guard for pointer actions.

    Trusted vision actions use this before consuming target
    evidence so an already HELD/UNKNOWN finger does not waste
    a fresh semantic target proof.

    Raw physical pointer actions still perform the authoritative
    serialized state check immediately around the physical effect.
    """

    from app.agent.body_button_state import (
        BODY_BUTTON_CLEAR,
        BODY_BUTTON_STATE,
    )

    try:
        state = (
            BODY_BUTTON_STATE.snapshot()
        )

    except Exception as error:
        return (
            f"{action_label} rejected because KUMA-owned "
            "button state could not be read safely: "
            f"{error}"
        )

    if (
        state.status
        == BODY_BUTTON_CLEAR
    ):
        return None

    button = (
        state.button
        if state.button is not None
        else "<unknown>"
    )

    return (
        f"{action_label} rejected because KUMA-owned "
        f"button state is {state.status!r} "
        f"for button {button!r}."
    )


# =========================================================
# PHYSICAL VISION-ACTION DESKTOP GUARD
# =========================================================

def _revalidate_physical_vision_click_desktop_context(
    observation_id,
):
    """Fail closed unless the frontmost app still matches this screen.

    This is an independent final body-boundary prerequisite. A match proves
    frontmost-application continuity only. It does not grant permission,
    semantic target authority, pixel continuity, or click authority.
    """

    if (
        type(observation_id) is not str
        or not observation_id.strip()
    ):
        return (
            False,
            "Physical vision click desktop provenance requires "
            "an exact screen observation ID.",
        )

    observation_id = observation_id.strip()

    from app.desktop.provenance import (
        SCREEN_DESKTOP_PROVENANCE,
    )
    from app.desktop.revalidation import (
        revalidate_desktop_context,
    )
    from app.desktop.runtime import (
        collect_desktop_context,
    )

    try:
        provenance = (
            SCREEN_DESKTOP_PROVENANCE.get(
                observation_id
            )
        )
    except Exception:
        return (
            False,
            "Physical vision click desktop provenance lookup failed.",
        )

    if provenance is None:
        return (
            False,
            "Physical vision click desktop provenance is unavailable "
            "for the exact screen observation.",
        )

    try:
        current = collect_desktop_context(
            timeout_seconds=(
                PHYSICAL_DESKTOP_REVALIDATION_TIMEOUT_SECONDS
            ),
            max_windows=(
                PHYSICAL_DESKTOP_REVALIDATION_MAX_WINDOWS
            ),
        )
    except Exception:
        return (
            False,
            "Physical vision click current desktop context "
            "collection failed.",
        )

    try:
        revalidation = revalidate_desktop_context(
            provenance.binding,
            provenance.desktop_before,
            provenance.desktop_after,
            current,
            max_current_age_seconds=(
                PHYSICAL_DESKTOP_REVALIDATION_MAX_AGE_SECONDS
            ),
        )
    except Exception:
        return (
            False,
            "Physical vision click desktop context revalidation "
            "failed closed.",
        )

    if not revalidation.matched:
        diagnostic = "unknown"
        if (
            type(revalidation.diagnostics) is tuple
            and revalidation.diagnostics
            and type(revalidation.diagnostics[0]) is str
        ):
            diagnostic = revalidation.diagnostics[0]

        status = (
            revalidation.status
            if type(revalidation.status) is str
            else "unknown"
        )

        return (
            False,
            "Physical vision click desktop context revalidation "
            f"failed: {status} ({diagnostic}).",
        )

    return True, ""


def _revalidate_physical_vision_move_desktop_context(
    observation_id,
):
    """Fail closed unless the frontmost app still matches this screen.

    This is an independent final body-boundary prerequisite
    for trusted semantic pointer movement.

    A match proves frontmost-application continuity only.
    It does not grant permission, semantic target authority,
    pixel continuity, or movement authority.
    """

    if (
        type(observation_id) is not str
        or not observation_id.strip()
    ):
        return (
            False,
            "Physical vision move desktop provenance requires "
            "an exact screen observation ID.",
        )

    observation_id = (
        observation_id.strip()
    )

    from app.desktop.provenance import (
        SCREEN_DESKTOP_PROVENANCE,
    )

    from app.desktop.revalidation import (
        revalidate_desktop_context,
    )

    from app.desktop.runtime import (
        collect_desktop_context,
    )

    try:
        provenance = (
            SCREEN_DESKTOP_PROVENANCE.get(
                observation_id
            )
        )

    except Exception:
        return (
            False,
            "Physical vision move desktop provenance "
            "lookup failed.",
        )

    if provenance is None:
        return (
            False,
            "Physical vision move desktop provenance "
            "is unavailable for the exact screen observation.",
        )

    try:
        current = collect_desktop_context(
            timeout_seconds=(
                PHYSICAL_DESKTOP_REVALIDATION_TIMEOUT_SECONDS
            ),
            max_windows=(
                PHYSICAL_DESKTOP_REVALIDATION_MAX_WINDOWS
            ),
        )

    except Exception:
        return (
            False,
            "Physical vision move current desktop "
            "context collection failed.",
        )

    try:
        revalidation = revalidate_desktop_context(
            provenance.binding,
            provenance.desktop_before,
            provenance.desktop_after,
            current,
            max_current_age_seconds=(
                PHYSICAL_DESKTOP_REVALIDATION_MAX_AGE_SECONDS
            ),
        )

    except Exception:
        return (
            False,
            "Physical vision move desktop context "
            "revalidation failed closed.",
        )

    if not revalidation.matched:

        diagnostic = "unknown"

        if (
            type(revalidation.diagnostics) is tuple
            and revalidation.diagnostics
            and type(
                revalidation.diagnostics[0]
            ) is str
        ):
            diagnostic = (
                revalidation.diagnostics[0]
            )

        status = (
            revalidation.status
            if type(
                revalidation.status
            ) is str
            else "unknown"
        )

        return (
            False,
            "Physical vision move desktop context "
            f"revalidation failed: "
            f"{status} ({diagnostic}).",
        )

    return True, ""


# =========================================================
# SCREEN
# =========================================================

def screenshot_screen(
    save_path: str = "/tmp/kuma_screen.png",
) -> ToolResult:
    """
    Capture the current macOS screen and save it to disk.

    This tool is kept for explicit screenshot requests.

    The isolated vision pipeline uses capture_screen()
    directly and does not depend on this file.
    """

    try:
        from pathlib import Path

        path = Path(save_path).expanduser()

        allowed_root = Path("/tmp").resolve()
        resolved_path = path.resolve()

        if allowed_root not in resolved_path.parents:
            return ToolResult.fail(
                "Screenshot path must be inside /tmp."
            )

        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        screenshot = pyautogui.screenshot()

        screenshot.save(
            str(path),
            format="PNG",
        )

        if not path.exists():
            return ToolResult.fail(
                "Screenshot capture reported success, "
                "but the image file was not created."
            )

        file_size = path.stat().st_size

        if file_size <= 0:
            return ToolResult.fail(
                "Screenshot file was created but is empty."
            )

        width, height = screenshot.size

        return ToolResult.ok(
            f"Screenshot captured successfully: "
            f"{path} "
            f"({width}x{height}, {file_size} bytes)"
        )

    except Exception as error:
        return ToolResult.fail(
            f"Could not capture screenshot: {error}"
        )


# =========================================================
# MOUSE
# =========================================================

def move_mouse(
    x: int,
    y: int,
    duration: float = 0.15,
) -> ToolResult:
    """
    Move the mouse to an absolute native screen coordinate.

    Physical magnitude and input types are deliberately bounded.

    Pointer movement is forbidden while KUMA owns a HELD or
    UNKNOWN mouse-button state. The state check and physical
    movement are serialized under the same body-state lock so
    raw movement cannot accidentally become an implicit drag.
    """

    from app.agent.body_button_state import (
        BODY_BUTTON_CLEAR,
        BODY_BUTTON_STATE,
    )

    try:
        if (
            type(x) is not int
            or type(y) is not int
        ):
            return ToolResult.fail(
                "Mouse coordinates must be integers."
            )

        if not _finite_number(
            duration
        ):
            return ToolResult.fail(
                "Mouse move duration must be a finite number."
            )

        duration = float(
            duration
        )

        if not (
            0.0
            <= duration
            <= MAX_MOUSE_MOVE_DURATION_SECONDS
        ):
            return ToolResult.fail(
                "Mouse move duration must be between "
                f"0 and "
                f"{MAX_MOUSE_MOVE_DURATION_SECONDS:g} seconds."
            )

        with BODY_BUTTON_STATE.serialized_transition() as state:

            if (
                state.status
                != BODY_BUTTON_CLEAR
            ):
                return ToolResult.fail(
                    "Mouse movement rejected because KUMA-owned "
                    f"button state is {state.status!r}."
                )

            screen_width, screen_height = (
                pyautogui.size()
            )

            if not (
                0 <= x < screen_width
                and 0 <= y < screen_height
            ):
                return ToolResult.fail(
                    f"Mouse coordinate ({x}, {y}) is outside "
                    f"screen bounds "
                    f"{screen_width}x{screen_height}."
                )

            _enforce_pyautogui_safety()

            pyautogui.moveTo(
                x,
                y,
                duration=duration,
            )

            return ToolResult.ok(
                f"Moved mouse to ({x}, {y})."
            )

    except Exception as error:
        return ToolResult.fail(
            f"Could not move mouse: {error}"
        )


def click_at(
    x: int,
    y: int,
    button: str = "left",
    clicks: int = 1,
) -> ToolResult:
    """
    Safely click an absolute native screen coordinate.

    IMPORTANT:
    This function expects NATIVE SCREEN coordinates.

    Vision coordinates must be converted through
    CoordinateMapper before reaching this function.

    Atomic clicks may execute only while KUMA-owned button state
    is CLEAR. If pyautogui.click reports failure after execution
    begins, the internal down/up result is physically ambiguous,
    so KUMA records UNKNOWN for the exact click button.
    """

    from app.agent.body_button_state import (
        BODY_BUTTON_CLEAR,
        BODY_BUTTON_STATE,
    )

    try:
        if (
            type(x) is not int
            or type(y) is not int
        ):
            return ToolResult.fail(
                "Click coordinates must be integers."
            )

        if type(button) is not str:
            return ToolResult.fail(
                "Mouse button must be a string."
            )

        button = (
            button.strip().lower()
        )

        if button not in SUPPORTED_MOUSE_BUTTONS:
            return ToolResult.fail(
                f"Unsupported mouse button: {button}"
            )

        if type(clicks) is not int:
            return ToolResult.fail(
                "Click count must be an integer."
            )

        if not (
            1
            <= clicks
            <= MAX_CLICK_COUNT
        ):
            return ToolResult.fail(
                "Click count must be "
                f"between 1 and {MAX_CLICK_COUNT}."
            )

        with BODY_BUTTON_STATE.serialized_transition() as state:

            if (
                state.status
                != BODY_BUTTON_CLEAR
            ):
                return ToolResult.fail(
                    "Mouse click rejected because KUMA-owned "
                    f"button state is {state.status!r}."
                )

            screen_width, screen_height = (
                pyautogui.size()
            )

            if not (
                0 <= x < screen_width
                and 0 <= y < screen_height
            ):
                return ToolResult.fail(
                    f"Click coordinate ({x}, {y}) is outside "
                    f"screen bounds "
                    f"{screen_width}x{screen_height}."
                )

            # Failure here occurs before click execution begins,
            # so CLEAR remains a valid representation.
            _enforce_pyautogui_safety()

            try:

                pyautogui.click(
                    x=x,
                    y=y,
                    button=button,
                    clicks=clicks,
                    interval=0.08,
                )

            except BaseException as error:

                # pyautogui.click is internally a down/up compound
                # action. Once the call begins, an exception cannot
                # prove whether the host button was ultimately left
                # pressed or released.
                BODY_BUTTON_STATE._record_uncertain(
                    button
                )

                if isinstance(
                    error,
                    Exception,
                ):
                    return ToolResult.fail(
                        f"Could not click at ({x}, {y}); "
                        "KUMA-owned mouse-button state "
                        f"is UNKNOWN for {button!r}: {error}"
                    )

                raise

            return ToolResult.ok(
                f"Clicked {button} at ({x}, {y}) "
                f"{clicks} time(s)."
            )

    except Exception as error:
        return ToolResult.fail(
            f"Could not click at ({x}, {y}): {error}"
        )



def hold_mouse(
    button: str = "left",
) -> ToolResult:
    """
    Hold one exact mouse button at the pointer's current position.

    This is a raw finger action only. It does not move the pointer,
    resolve a semantic target, grant permission, or establish GUI
    authority.

    A successful live mouseDown is recorded in KUMA's process-local
    runtime body state. If the physical transition becomes ambiguous,
    KUMA compensates with mouseUp where possible and otherwise enters
    UNKNOWN state for the exact candidate button.
    """

    from app.agent.body_button_state import (
        BODY_BUTTON_CLEAR,
        BODY_BUTTON_STATE,
        BODY_MOUSE_BUTTONS,
        BodyButtonStateError,
    )

    effect_started = False

    if (
        type(button) is not str
        or button not in BODY_MOUSE_BUTTONS
    ):
        return ToolResult.fail(
            "Mouse hold button must be exactly one of: "
            "left, right, middle."
        )

    try:

        with BODY_BUTTON_STATE.serialized_transition() as state:

            if (
                state.status
                != BODY_BUTTON_CLEAR
            ):
                return ToolResult.fail(
                    "Mouse hold rejected because KUMA-owned "
                    f"button state is {state.status!r}."
                )

            # No physical effect has occurred yet. If host-safety
            # configuration itself fails, state remains CLEAR.
            _enforce_pyautogui_safety()

            try:

                # This is the first potentially stateful physical
                # transition. Any failure from this point until the
                # HELD state is recorded is treated as ambiguous.
                effect_started = True

                pyautogui.mouseDown(
                    button=button,
                )

                BODY_BUTTON_STATE._record_press_success(
                    button
                )

            except BaseException as error:

                compensation_error = None

                try:

                    _enforce_pyautogui_safety()

                    pyautogui.mouseUp(
                        button=button,
                    )

                except BaseException as cleanup_error:

                    compensation_error = (
                        cleanup_error
                    )

                    # UNKNOWN recording is deliberately hardened so
                    # clock failure cannot leave an ambiguous live
                    # mouse-down represented as CLEAR.
                    BODY_BUTTON_STATE._record_uncertain(
                        button
                    )

                if isinstance(
                    error,
                    Exception,
                ):

                    if compensation_error is None:
                        return ToolResult.fail(
                            "Could not hold mouse button "
                            f"{button!r}; compensating mouseUp "
                            "completed and KUMA-owned button "
                            "state remains CLEAR.",
                            effect_started=effect_started,
                        )

                    return ToolResult.fail(
                        "Could not hold mouse button "
                        f"{button!r}; compensating mouseUp "
                        "also failed, so KUMA-owned button "
                        "state is UNKNOWN.",
                        effect_started=effect_started,
                    )

                # KeyboardInterrupt, SystemExit, and other
                # BaseException subclasses are never normalized
                # into ordinary tool failure. Cleanup/state repair
                # has already been attempted.
                raise

            return ToolResult.ok(
                f"Holding mouse button {button}.",
                effect_started=effect_started,
            )

    except BodyButtonStateError as error:

        return ToolResult.fail(
            "Mouse hold body-state transition failed: "
            f"{error}"
        )

    except Exception as error:

        return ToolResult.fail(
            f"Could not hold mouse button {button!r}: "
            f"{error}"
        )


def release_mouse() -> ToolResult:
    """
    Release KUMA's exact process-local held/unknown mouse button.

    This function intentionally accepts no button argument.

    Planner/model input cannot tell KUMA which button it supposedly
    has down. The release identity comes only from live runtime body
    state established by the physical boundary.

    UNKNOWN is recoverable only by issuing mouseUp for that exact
    recorded candidate button.
    """

    from app.agent.body_button_state import (
        BODY_BUTTON_CLEAR,
        BODY_BUTTON_STATE,
        BodyButtonStateError,
    )

    effect_started = False

    try:

        with BODY_BUTTON_STATE.serialized_transition() as state:

            if (
                state.status
                == BODY_BUTTON_CLEAR
            ):
                return ToolResult.fail(
                    "Mouse release rejected because KUMA-owned "
                    "button state is already CLEAR."
                )

            button = state.button

            if button is None:
                # Snapshot invariants should make this impossible,
                # but the physical boundary remains fail closed.
                return ToolResult.fail(
                    "Mouse release rejected because the runtime "
                    "button identity is unavailable."
                )

            # If this fails before mouseUp begins, preserve the
            # existing HELD/UNKNOWN state unchanged.
            _enforce_pyautogui_safety()

            try:

                effect_started = True

                pyautogui.mouseUp(
                    button=button,
                )

            except BaseException as error:

                # mouseUp may have partially reached the host before
                # reporting failure. The final physical state is
                # therefore UNKNOWN, not HELD or CLEAR.
                BODY_BUTTON_STATE._record_uncertain(
                    button
                )

                if isinstance(
                    error,
                    Exception,
                ):
                    return ToolResult.fail(
                        "Could not release mouse button "
                        f"{button!r}; KUMA-owned button "
                        "state is UNKNOWN.",
                        effect_started=effect_started,
                    )

                raise

            try:

                BODY_BUTTON_STATE._record_release_success(
                    button
                )

            except BaseException as error:

                # mouseUp returned successfully, but KUMA failed to
                # synchronize its state record. Stay conservative:
                # UNKNOWN permits only another exact recovery release.
                BODY_BUTTON_STATE._record_uncertain(
                    button
                )

                if isinstance(
                    error,
                    Exception,
                ):
                    return ToolResult.fail(
                        "Mouse button was physically released, "
                        "but KUMA could not safely record CLEAR; "
                        "button state is UNKNOWN.",
                        effect_started=effect_started,
                    )

                raise

            return ToolResult.ok(
                f"Released mouse button {button}.",
                effect_started=effect_started,
            )

    except BodyButtonStateError as error:

        return ToolResult.fail(
            "Mouse release body-state transition failed: "
            f"{error}"
        )

    except Exception as error:

        return ToolResult.fail(
            f"Could not release mouse button: {error}"
        )




def hold_mouse_trusted(
    receipt,
) -> ToolResult:
    from app.agent.trusted_mouse_button_receipt import (
        TRUSTED_MOUSE_HOLD_RECEIPTS,
        TrustedMouseHoldReceipt,
    )

    if type(receipt) is not TrustedMouseHoldReceipt:
        return ToolResult.fail(
            "Trusted mouse hold requires an exact receipt."
        )

    claimed = TRUSTED_MOUSE_HOLD_RECEIPTS.claim(
        receipt
    )

    if claimed is None:
        return ToolResult.fail(
            "Trusted mouse hold receipt is stale, consumed, "
            "or its pointer/body context changed."
        )

    return hold_mouse(
        claimed.hold_evidence.button
    )


def release_mouse_trusted(
    receipt,
) -> ToolResult:
    from app.agent.trusted_mouse_button_receipt import (
        TRUSTED_MOUSE_RELEASE_RECEIPTS,
        TrustedMouseReleaseReceipt,
    )

    if type(receipt) is not TrustedMouseReleaseReceipt:
        return ToolResult.fail(
            "Trusted mouse release requires an exact receipt."
        )

    claimed = (
        TRUSTED_MOUSE_RELEASE_RECEIPTS.claim(
            receipt
        )
    )

    if claimed is None:
        return ToolResult.fail(
            "Trusted mouse release receipt is stale, consumed, "
            "or live button state changed."
        )

    # No button parameter. Exact identity remains owned by
    # BODY_BUTTON_STATE inside release_mouse().
    return release_mouse()



def _revalidate_physical_vision_hold_desktop_context(
    observation_id,
):
    """
    Fail closed unless the frontmost application still matches
    the trusted screen used for one semantic hold action.

    Trusted hold has the same frontmost-application continuity
    requirement as trusted pointer movement. This wrapper grants
    no target authority, permission, or physical button state.
    """

    allowed, reason = (
        _revalidate_physical_vision_move_desktop_context(
            observation_id
        )
    )

    return (
        allowed,
        reason.replace(
            "Physical vision move",
            "Physical vision hold",
        ),
    )


def hold_mouse_vision(
    x: int,
    y: int,
    observation_id: str,
    button: str = "left",
) -> ToolResult:
    """
    Move to one trusted semantic target and hold an exact button.

    Caller contract:
        - exact trusted vision x/y
        - exact screen observation ID
        - exact button identity
        - no caller-controlled movement duration

    Trust contract:
        - model target coordinates remain proposals upstream
        - exact target+button hold attestation is single-use
        - frontmost-application continuity is revalidated
        - target-region pixels must remain unchanged
        - screen observation is single-use
        - trusted point is mapped into native coordinates

    Physical contract:
        - the final target move and mouse-down occur under one
          serialized KUMA finger-state transition
        - raw move_mouse retains physical coordinate/duration bounds
        - raw hold_mouse owns mouseDown compensation and UNKNOWN
          state handling
        - only successful live mouseDown may establish HELD state

    This tool is intentionally not registered during 8C4B.
    """

    effect_started = False

    from app.agent.body_button_state import (
        BODY_BUTTON_CLEAR,
        BODY_BUTTON_STATE,
        BODY_MOUSE_BUTTONS,
    )

    from app.vision.observation import (
        SCREEN_OBSERVATIONS,
        ScreenObservationError,
    )

    from app.vision.gui_target_verifier import (
        GUI_HOLD_TARGET_ATTESTATIONS,
        current_screen_matches_attestation,
    )

    from app.desktop.provenance import (
        SCREEN_DESKTOP_PROVENANCE,
    )

    def invalidate_action_evidence():

        try:
            GUI_HOLD_TARGET_ATTESTATIONS.clear()
        except Exception:
            pass

        SCREEN_OBSERVATIONS.clear()
        SCREEN_DESKTOP_PROVENANCE.clear()

    try:

        # -------------------------------------------------
        # STRICT RUNTIME ARGUMENT CONTRACT
        # -------------------------------------------------

        if (
            type(x) is not int
            or type(y) is not int
        ):
            return ToolResult.fail(
                "Vision hold coordinates must be integers."
            )

        if (
            type(observation_id) is not str
            or not observation_id
            or observation_id
            != observation_id.strip()
        ):
            return ToolResult.fail(
                "Vision hold requires an exact trusted "
                "screen observation ID."
            )

        if (
            type(button) is not str
            or button not in BODY_MOUSE_BUTTONS
        ):
            return ToolResult.fail(
                "Vision hold button must be exactly one of: "
                "left, right, middle."
            )

        # -------------------------------------------------
        # EARLY NON-CONSUMING FINGER INTERLOCK
        # -------------------------------------------------

        body_block = _pointer_button_block_reason(
            "Vision hold"
        )

        if body_block is not None:
            return ToolResult.fail(
                body_block
            )

        # -------------------------------------------------
        # TRUSTED OBSERVATION LOOKUP
        # -------------------------------------------------

        observation = (
            SCREEN_OBSERVATIONS.peek(
                observation_id
            )
        )

        if not (
            0 <= x
            < observation.vision_width
            and
            0 <= y
            < observation.vision_height
        ):
            return ToolResult.fail(
                f"Vision coordinate ({x}, {y}) is outside "
                "the trusted observation bounds "
                f"{observation.vision_width}x"
                f"{observation.vision_height}."
            )

        # -------------------------------------------------
        # DISPLAY GEOMETRY CONTINUITY
        # -------------------------------------------------

        current_width, current_height = (
            pyautogui.size()
        )

        current_width = int(
            current_width
        )

        current_height = int(
            current_height
        )

        if (
            current_width
            != observation.native_width
            or current_height
            != observation.native_height
        ):
            invalidate_action_evidence()

            return ToolResult.fail(
                "Native screen geometry changed after the "
                "trusted screen observation. Analyze the "
                "screen again before holding the target."
            )

        # -------------------------------------------------
        # FINAL FINGER-STATE SERIALIZATION
        # -------------------------------------------------
        #
        # Everything from receipt claim through target movement
        # and mouseDown executes while one body-state RLock is
        # held. Raw move/hold functions re-enter the same lock.
        #
        # This prevents another thread from creating HELD state
        # between trusted movement and the physical press.
        # -------------------------------------------------

        with (
            BODY_BUTTON_STATE.serialized_transition()
            as body_state
        ):

            if (
                body_state.status
                != BODY_BUTTON_CLEAR
            ):
                return ToolResult.fail(
                    "Vision hold rejected because KUMA-owned "
                    f"button state is {body_state.status!r}."
                )

            # ---------------------------------------------
            # EXACT TARGET + BUTTON RECEIPT
            # ---------------------------------------------

            try:

                target_attestation = (
                    GUI_HOLD_TARGET_ATTESTATIONS.claim(
                        observation_id=(
                            observation_id
                        ),
                        x=x,
                        y=y,
                        button=button,
                    )
                )

            except ValueError as error:

                return ToolResult.fail(
                    "Vision hold rejected: semantic hold "
                    "target attestation unavailable or invalid: "
                    f"{error}"
                )

            # ---------------------------------------------
            # INDEPENDENT DESKTOP REVALIDATION
            # ---------------------------------------------

            (
                desktop_context_matched,
                desktop_context_error,
            ) = (
                _revalidate_physical_vision_hold_desktop_context(
                    observation_id
                )
            )

            if not desktop_context_matched:
                invalidate_action_evidence()

                return ToolResult.fail(
                    "Vision hold rejected: "
                    f"{desktop_context_error}"
                )

            # ---------------------------------------------
            # TARGET-REGION PIXEL CONTINUITY
            # ---------------------------------------------

            (
                pixels_match,
                pixel_error,
            ) = (
                current_screen_matches_attestation(
                    observation=observation,
                    attestation=target_attestation,
                )
            )

            if not pixels_match:
                invalidate_action_evidence()

                return ToolResult.fail(
                    "Vision hold rejected: "
                    f"{pixel_error}"
                )

            # ---------------------------------------------
            # SINGLE-USE SCREEN OBSERVATION
            # ---------------------------------------------

            observation = (
                SCREEN_OBSERVATIONS.claim(
                    observation_id
                )
            )

            SCREEN_DESKTOP_PROVENANCE.clear()

            # ---------------------------------------------
            # LAST DISPLAY-GEOMETRY CHECK
            # ---------------------------------------------

            confirmed_width, confirmed_height = (
                pyautogui.size()
            )

            confirmed_width = int(
                confirmed_width
            )

            confirmed_height = int(
                confirmed_height
            )

            if (
                confirmed_width
                != observation.native_width
                or confirmed_height
                != observation.native_height
            ):
                return ToolResult.fail(
                    "Native screen geometry changed immediately "
                    "before trusted semantic hold. Analyze the "
                    "screen again before holding."
                )

            # ---------------------------------------------
            # TRUSTED COORDINATE CONVERSION
            # ---------------------------------------------

            mapper = CoordinateMapper(
                vision_width=(
                    observation.vision_width
                ),
                vision_height=(
                    observation.vision_height
                ),
                screen_width=(
                    observation.native_width
                ),
                screen_height=(
                    observation.native_height
                ),
            )

            screen_x, screen_y = (
                mapper.vision_to_screen(
                    x,
                    y,
                )
            )

            print(
                "KUMA ACTION → Observation:"
                f" {observation.observation_id}"
            )

            print(
                "KUMA ACTION → Trusted hold target:"
                f" ({x}, {y})"
            )

            print(
                "KUMA ACTION → Native hold target:"
                f" ({screen_x}, {screen_y})"
            )

            print(
                "KUMA ACTION → Hold button:"
                f" {button}"
            )

            # ---------------------------------------------
            # PHYSICAL TARGET MOVEMENT
            # ---------------------------------------------
            #
            # The outer body lock remains held. move_mouse()
            # re-enters that same RLock and performs its own
            # final CLEAR-state and native-bounds enforcement.
            # ---------------------------------------------

            move_result = move_mouse(
                screen_x,
                screen_y,
                duration=0.15,
            )

            if not move_result.success:
                return ToolResult.fail(
                    "Vision hold could not reach the trusted "
                    f"target: {move_result.error}",
                    effect_started=(
                        getattr(
                            move_result,
                            "effect_started",
                            False,
                        )
                        is True
                    ),
                )

            # Successful target movement is already a physical
            # effect even before mouseDown begins.
            effect_started = True

            # ---------------------------------------------
            # PHYSICAL MOUSE-DOWN
            # ---------------------------------------------
            #
            # hold_mouse() re-enters the same RLock. It owns
            # mouseDown compensation, interruption handling,
            # and CLEAR/HELD/UNKNOWN state transitions.
            # ---------------------------------------------

            hold_result = hold_mouse(
                button
            )

            if not hold_result.success:
                return ToolResult.fail(
                    "Vision hold physical press failed: "
                    f"{hold_result.error}",
                    effect_started=(
                        effect_started
                        or getattr(
                            hold_result,
                            "effect_started",
                            False,
                        )
                        is True
                    ),
                )

            final_state = (
                BODY_BUTTON_STATE.snapshot()
            )

            if (
                final_state.status
                != "held"
                or final_state.button
                != button
            ):
                return ToolResult.fail(
                    "Vision hold physical press returned success "
                    "without establishing the exact HELD state.",
                    effect_started=True,
                )

            return ToolResult.ok(
                "Holding trusted semantic target "
                f"with mouse button {button}.",
                effect_started=True,
            )

    except ScreenObservationError as error:

        return ToolResult.fail(
            f"Vision hold rejected: {error}"
        )

    except CoordinateMappingError as error:

        return ToolResult.fail(
            "Vision hold coordinate mapping failed: "
            f"{error}"
        )

    except Exception as error:

        return ToolResult.fail(
            "Could not hold trusted vision target: "
            f"{error}",
            effect_started=effect_started,
        )




def hold_mouse_vision_trusted(
    receipt,
) -> ToolResult:
    """
    Execute one exact semantic-hold receipt.

    Private physical bridge only. It is not a model-facing tool.
    """

    from app.agent.trusted_semantic_hold_receipt import (
        TRUSTED_SEMANTIC_HOLD_RECEIPTS,
        TrustedSemanticHoldReceipt,
    )

    if (
        type(receipt)
        is not TrustedSemanticHoldReceipt
    ):
        return ToolResult.fail(
            "Trusted semantic hold requires an exact receipt."
        )

    claimed = (
        TRUSTED_SEMANTIC_HOLD_RECEIPTS.claim(
            receipt
        )
    )

    if claimed is None:
        return ToolResult.fail(
            "Trusted semantic-hold receipt is stale, consumed, "
            "or its runtime authority/body state changed."
        )

    return hold_mouse_vision(
        claimed.vision_x,
        claimed.vision_y,
        claimed.observation_id,
        button=claimed.button,
    )


def click_vision(
    x: int,
    y: int,
    observation_id: str,
    button: str = "left",
    clicks: int = 1,
) -> ToolResult:
    """
    Click a coordinate from one trusted KUMA screen observation.

    Caller argument contract:
        - x
        - y
        - observation_id
        - button
        - bounded click count

    MissionService trust boundary:
        - model x/y/observation_id are proposals only
        - observation_id is rebound to fresh trusted O1
        - x/y are rebound to the trusted K4-derived point
        - button/clicks remain caller-selected within their bounds

    KUMA physical authority:
        - trusted observation lookup
        - vision/native screen dimensions
        - coordinate conversion
        - observation freshness and single-use state
        - exact semantic target attestation
        - final desktop and target-region continuity checks

    The caller must never supply vision_width or vision_height.
    """

    from app.vision.observation import (
        SCREEN_OBSERVATIONS,
        ScreenObservationError,
    )

    from app.vision.gui_target_verifier import (
        GUI_TARGET_ATTESTATIONS,
        current_screen_matches_attestation,
    )

    from app.desktop.provenance import (
        SCREEN_DESKTOP_PROVENANCE,
    )

    def invalidate_action_evidence():
        SCREEN_OBSERVATIONS.clear()
        SCREEN_DESKTOP_PROVENANCE.clear()

    try:
        # -------------------------------------------------
        # STRICT MODEL ARGUMENT CONTRACT
        # -------------------------------------------------

        if (
            type(x) is not int
            or type(y) is not int
        ):
            return ToolResult.fail(
                "Vision coordinates must be integers."
            )

        if (
            type(observation_id) is not str
            or not observation_id.strip()
        ):
            return ToolResult.fail(
                "A trusted screen observation ID is required."
            )

        observation_id = (
            observation_id.strip()
        )

        if type(button) is not str:
            return ToolResult.fail(
                "Mouse button must be a string."
            )

        button = (
            button.strip().lower()
        )

        if button not in {
            "left",
            "right",
            "middle",
        }:
            return ToolResult.fail(
                f"Unsupported mouse button: {button}"
            )

        if type(clicks) is not int:
            return ToolResult.fail(
                "Click count must be an integer."
            )

        # Vision-target clicks are deliberately bounded.
        # One or two clicks cover ordinary and double-click
        # interaction without allowing model-generated
        # click storms.
        if clicks not in {
            1,
            2,
        }:
            return ToolResult.fail(
                "Vision click count must be 1 or 2."
            )

        # -------------------------------------------------
        # TRUSTED OBSERVATION LOOKUP
        # -------------------------------------------------

        # -------------------------------------------------
        # POINTER / FINGER INTERLOCK — EARLY GUARD
        # -------------------------------------------------
        #
        # Do this before consuming target evidence. The raw
        # physical delegate repeats the check under the serialized
        # body-state lock immediately around the actual effect.
        # -------------------------------------------------

        body_block = _pointer_button_block_reason(
            "Vision click"
        )

        if body_block is not None:
            return ToolResult.fail(
                body_block
            )

        observation = (
            SCREEN_OBSERVATIONS.peek(
                observation_id
            )
        )

        # -------------------------------------------------
        # VALIDATE MODEL COORDINATE AGAINST TRUSTED GEOMETRY
        # -------------------------------------------------

        if not (
            0 <= x
            < observation.vision_width
            and
            0 <= y
            < observation.vision_height
        ):
            return ToolResult.fail(
                f"Vision coordinate ({x}, {y}) is outside "
                "the trusted observation bounds "
                f"{observation.vision_width}x"
                f"{observation.vision_height}."
            )

        # -------------------------------------------------
        # DISPLAY GEOMETRY MUST STILL MATCH
        # -------------------------------------------------

        current_width, current_height = (
            pyautogui.size()
        )

        current_width = int(
            current_width
        )
        current_height = int(
            current_height
        )

        if (
            current_width
            != observation.native_width
            or current_height
            != observation.native_height
        ):
            # The coordinate system changed. The old
            # observation must never become usable again.
            invalidate_action_evidence()

            return ToolResult.fail(
                "Native screen geometry changed after the "
                "screen observation. Analyze the screen again "
                "before clicking."
            )

        # -------------------------------------------------
        # SEMANTIC TARGET ATTESTATION
        # -------------------------------------------------
        #
        # A trusted runtime verifier must have attested that
        # this exact observation/x/y/button/click-count maps
        # to the human-authorized visible target.
        #
        # Model arguments cannot create this attestation.
        # Every claim is single-use.
        # -------------------------------------------------

        try:

            target_attestation = (
                GUI_TARGET_ATTESTATIONS.claim(
                    observation_id=(
                        observation_id
                    ),
                    x=x,
                    y=y,
                    button=button,
                    clicks=clicks,
                )
            )

        except ValueError as error:

            return ToolResult.fail(
                "Vision click rejected: semantic target "
                "attestation unavailable or invalid: "
                f"{error}"
            )

        # -------------------------------------------------
        # FINAL PHYSICAL DESKTOP-CONTEXT REVALIDATION
        # -------------------------------------------------
        #
        # MissionService already performs A6-1 before issuing
        # the semantic attestation. The physical body repeats
        # the check independently after consuming that exact
        # attestation and before the final target-region digest check.
        #
        # The desktop collector may take time, so pixel
        # revalidation deliberately runs AFTER this gate and
        # remains the last target-content check before claim.
        # -------------------------------------------------

        (
            desktop_context_matched,
            desktop_context_error,
        ) = (
            _revalidate_physical_vision_click_desktop_context(
                observation_id
            )
        )

        if not desktop_context_matched:
            invalidate_action_evidence()

            return ToolResult.fail(
                "Vision click rejected: "
                f"{desktop_context_error}"
            )

        # -------------------------------------------------
        # VERIFIED TARGET-REGION PIXELS MUST STILL MATCH
        # -------------------------------------------------
        #
        # The semantic verifier inspected a fresh screenshot.
        # Re-capture immediately before consuming the trusted
        # ScreenObservation.
        #
        # Any target-region pixel change invalidates the click.
        # -------------------------------------------------

        (
            pixels_match,
            pixel_error,
        ) = current_screen_matches_attestation(
            observation=observation,
            attestation=target_attestation,
        )

        if not pixels_match:

            # Semantic evidence is stale. Force a complete
            # fresh observe → verify → click cycle.
            invalidate_action_evidence()

            return ToolResult.fail(
                "Vision click rejected: "
                f"{pixel_error}"
            )

        # -------------------------------------------------
        # SINGLE-USE OBSERVATION AUTHORIZATION
        # -------------------------------------------------
        #
        # Claim only after:
        # - argument validation
        # - geometry validation
        # - semantic target attestation
        # - exact target-region digest recheck
        #
        # Once claimed, success OR failure requires a new
        # observation before another vision click.
        # -------------------------------------------------

        observation = (
            SCREEN_OBSERVATIONS.claim(
                observation_id
            )
        )

        # The paired provenance cannot remain active after the
        # single-use screen observation has been consumed.
        SCREEN_DESKTOP_PROVENANCE.clear()

        # Re-check after the atomic claim to narrow the
        # observation-to-action race window.
        confirmed_width, confirmed_height = (
            pyautogui.size()
        )

        confirmed_width = int(
            confirmed_width
        )
        confirmed_height = int(
            confirmed_height
        )

        if (
            confirmed_width
            != observation.native_width
            or confirmed_height
            != observation.native_height
        ):
            return ToolResult.fail(
                "Native screen geometry changed immediately "
                "before the vision click. Analyze the screen "
                "again before clicking."
            )

        # -------------------------------------------------
        # TRUSTED COORDINATE CONVERSION
        # -------------------------------------------------

        mapper = CoordinateMapper(
            vision_width=(
                observation.vision_width
            ),
            vision_height=(
                observation.vision_height
            ),
            screen_width=(
                observation.native_width
            ),
            screen_height=(
                observation.native_height
            ),
        )

        screen_x, screen_y = (
            mapper.vision_to_screen(
                x,
                y,
            )
        )

        print(
            "KUMA ACTION → Observation:"
            f" {observation.observation_id}"
        )

        print(
            "KUMA ACTION → Vision coordinate:"
            f" ({x}, {y})"
        )

        print(
            "KUMA ACTION → Native screen coordinate:"
            f" ({screen_x}, {screen_y})"
        )

        # Native click retains its own final coordinate
        # bounds check.
        return click_at(
            screen_x,
            screen_y,
            button=button,
            clicks=clicks,
        )

    except ScreenObservationError as error:
        return ToolResult.fail(
            f"Vision click rejected: {error}"
        )

    except CoordinateMappingError as error:
        return ToolResult.fail(
            f"Vision coordinate mapping failed: {error}"
        )

    except Exception as error:
        return ToolResult.fail(
            f"Could not click vision coordinate: {error}"
        )


def move_mouse_vision(
    x: int,
    y: int,
    observation_id: str,
    duration: float = 0.15,
) -> ToolResult:
    """
    Move the pointer to one trusted semantic KUMA target.

    Caller argument contract:
        - x
        - y
        - observation_id
        - bounded movement duration

    Future MissionService trust boundary:
        - model observation/x/y are proposals only
        - trusted runtime must replace them with fresh target proof
        - duration remains an action argument, never target evidence

    Physical body boundary:
        - exact trusted observation lookup
        - exact target-only semantic attestation
        - native-display geometry continuity
        - independent frontmost-application revalidation
        - exact target-region pixel continuity
        - single-use screen observation
        - trusted vision-to-native conversion
        - final raw move_mouse bounds enforcement

    This tool cannot create its own semantic attestation.
    """

    from app.vision.observation import (
        SCREEN_OBSERVATIONS,
        ScreenObservationError,
    )

    from app.vision.gui_target_verifier import (
        GUI_SEMANTIC_TARGET_ATTESTATIONS,
        current_screen_matches_attestation,
    )

    from app.desktop.provenance import (
        SCREEN_DESKTOP_PROVENANCE,
    )

    def invalidate_action_evidence():

        try:
            GUI_SEMANTIC_TARGET_ATTESTATIONS.clear()
        except Exception:
            pass

        SCREEN_OBSERVATIONS.clear()
        SCREEN_DESKTOP_PROVENANCE.clear()

    try:

        # -------------------------------------------------
        # STRICT ARGUMENT CONTRACT
        # -------------------------------------------------

        if (
            type(x) is not int
            or type(y) is not int
        ):
            return ToolResult.fail(
                "Vision movement coordinates must be integers."
            )

        if (
            type(observation_id) is not str
            or not observation_id.strip()
        ):
            return ToolResult.fail(
                "A trusted screen observation ID is required."
            )

        observation_id = (
            observation_id.strip()
        )

        if not _finite_number(
            duration
        ):
            return ToolResult.fail(
                "Vision movement duration must be "
                "a finite number."
            )

        duration = float(
            duration
        )

        if not (
            0.0
            <= duration
            <= MAX_MOUSE_MOVE_DURATION_SECONDS
        ):
            return ToolResult.fail(
                "Vision movement duration must be between "
                f"0 and "
                f"{MAX_MOUSE_MOVE_DURATION_SECONDS:g} seconds."
            )

        # -------------------------------------------------
        # TRUSTED OBSERVATION LOOKUP
        # -------------------------------------------------

        # -------------------------------------------------
        # POINTER / FINGER INTERLOCK — EARLY GUARD
        # -------------------------------------------------
        #
        # Do this before consuming target evidence. The raw
        # physical delegate repeats the check under the serialized
        # body-state lock immediately around the actual effect.
        # -------------------------------------------------

        body_block = _pointer_button_block_reason(
            "Vision movement"
        )

        if body_block is not None:
            return ToolResult.fail(
                body_block
            )

        observation = (
            SCREEN_OBSERVATIONS.peek(
                observation_id
            )
        )

        if not (
            0 <= x
            < observation.vision_width
            and
            0 <= y
            < observation.vision_height
        ):
            return ToolResult.fail(
                f"Vision coordinate ({x}, {y}) is outside "
                "the trusted observation bounds "
                f"{observation.vision_width}x"
                f"{observation.vision_height}."
            )

        # -------------------------------------------------
        # DISPLAY GEOMETRY CONTINUITY
        # -------------------------------------------------

        current_width, current_height = (
            pyautogui.size()
        )

        current_width = int(
            current_width
        )

        current_height = int(
            current_height
        )

        if (
            current_width
            != observation.native_width
            or current_height
            != observation.native_height
        ):
            invalidate_action_evidence()

            return ToolResult.fail(
                "Native screen geometry changed after the "
                "trusted screen observation. Analyze the "
                "screen again before moving the pointer."
            )

        # -------------------------------------------------
        # TARGET-ONLY SEMANTIC ATTESTATION
        # -------------------------------------------------
        #
        # This binds only:
        # - observation
        # - x/y
        # - human-goal digest
        # - image / target-region evidence
        #
        # It deliberately contains no duration or click state.
        # -------------------------------------------------

        try:
            target_attestation = (
                GUI_SEMANTIC_TARGET_ATTESTATIONS.claim(
                    observation_id=(
                        observation_id
                    ),
                    x=x,
                    y=y,
                )
            )

        except ValueError as error:

            return ToolResult.fail(
                "Vision move rejected: semantic target "
                "attestation unavailable or invalid: "
                f"{error}"
            )

        # -------------------------------------------------
        # FINAL BODY DESKTOP REVALIDATION
        # -------------------------------------------------

        (
            desktop_context_matched,
            desktop_context_error,
        ) = (
            _revalidate_physical_vision_move_desktop_context(
                observation_id
            )
        )

        if not desktop_context_matched:
            invalidate_action_evidence()

            return ToolResult.fail(
                "Vision move rejected: "
                f"{desktop_context_error}"
            )

        # -------------------------------------------------
        # TARGET-REGION PIXEL CONTINUITY
        # -------------------------------------------------

        (
            pixels_match,
            pixel_error,
        ) = (
            current_screen_matches_attestation(
                observation=observation,
                attestation=target_attestation,
            )
        )

        if not pixels_match:
            invalidate_action_evidence()

            return ToolResult.fail(
                "Vision move rejected: "
                f"{pixel_error}"
            )

        # -------------------------------------------------
        # SINGLE-USE SCREEN OBSERVATION
        # -------------------------------------------------

        observation = (
            SCREEN_OBSERVATIONS.claim(
                observation_id
            )
        )

        SCREEN_DESKTOP_PROVENANCE.clear()

        # -------------------------------------------------
        # LAST DISPLAY-GEOMETRY CHECK
        # -------------------------------------------------

        confirmed_width, confirmed_height = (
            pyautogui.size()
        )

        confirmed_width = int(
            confirmed_width
        )

        confirmed_height = int(
            confirmed_height
        )

        if (
            confirmed_width
            != observation.native_width
            or confirmed_height
            != observation.native_height
        ):
            return ToolResult.fail(
                "Native screen geometry changed immediately "
                "before trusted pointer movement. Analyze "
                "the screen again before moving."
            )

        # -------------------------------------------------
        # TRUSTED COORDINATE CONVERSION
        # -------------------------------------------------

        mapper = CoordinateMapper(
            vision_width=(
                observation.vision_width
            ),
            vision_height=(
                observation.vision_height
            ),
            screen_width=(
                observation.native_width
            ),
            screen_height=(
                observation.native_height
            ),
        )

        screen_x, screen_y = (
            mapper.vision_to_screen(
                x,
                y,
            )
        )

        print(
            "KUMA ACTION → Observation:"
            f" {observation.observation_id}"
        )

        print(
            "KUMA ACTION → Trusted vision target:"
            f" ({x}, {y})"
        )

        print(
            "KUMA ACTION → Native pointer target:"
            f" ({screen_x}, {screen_y})"
        )

        # Raw native movement retains the final physical bounds
        # and duration enforcement.
        return move_mouse(
            screen_x,
            screen_y,
            duration=duration,
        )

    except ScreenObservationError as error:

        return ToolResult.fail(
            f"Vision move rejected: {error}"
        )

    except CoordinateMappingError as error:

        return ToolResult.fail(
            "Vision movement coordinate mapping failed: "
            f"{error}"
        )

    except Exception as error:

        return ToolResult.fail(
            "Could not move to trusted vision target: "
            f"{error}"
        )


# =========================================================
# KEYBOARD
# =========================================================

def type_text(
    text: str,
    interval: float = 0.01,
) -> ToolResult:
    """
    Type a bounded text payload using the keyboard.
    """

    effect_started = False

    try:
        if type(text) is not str:
            return ToolResult.fail(
                "Text payload must be a string."
            )

        if not text:
            return ToolResult.fail(
                "Text payload cannot be empty."
            )

        if (
            len(text)
            > MAX_TYPE_TEXT_CHARACTERS
        ):
            return ToolResult.fail(
                "Text payload exceeds the "
                f"{MAX_TYPE_TEXT_CHARACTERS}-character "
                "per-action limit."
            )

        if not _finite_number(
            interval
        ):
            return ToolResult.fail(
                "Typing interval must be a finite number."
            )

        interval = float(
            interval
        )

        if not (
            0.0
            <= interval
            <= MAX_TYPE_INTERVAL_SECONDS
        ):
            return ToolResult.fail(
                "Typing interval must be between "
                f"0 and "
                f"{MAX_TYPE_INTERVAL_SECONDS:g} seconds."
            )

        estimated_action_seconds = (
            len(text)
            * interval
            + PYAUTOGUI_PAUSE_SECONDS
        )

        if (
            estimated_action_seconds
            > MAX_TYPE_ACTION_DURATION_SECONDS
        ):
            return ToolResult.fail(
                "Estimated typing action exceeds the "
                f"{MAX_TYPE_ACTION_DURATION_SECONDS:g}-second "
                "per-action limit."
            )

        _enforce_pyautogui_safety()

        effect_started = True

        pyautogui.write(
            text,
            interval=interval,
        )

        return ToolResult.ok(
            "Text typed successfully.",
            effect_started=effect_started,
        )

    except Exception as error:
        return ToolResult.fail(
            f"Could not type text: {error}",
            effect_started=effect_started,
        )


def type_text_focused(
    receipt,
    interval: float = 0.01,
) -> ToolResult:
    """
    Type only the exact text carried by one trusted focused-text receipt.

    This is a private physical execution primitive.

    The caller supplies no text payload. Text is recovered only from the
    exact receipt atomically consumed by FOCUSED_TEXT_RECEIPTS.

    The single-use receipt is consumed before the existing raw type_text()
    physical boundary is entered. Success or failure therefore cannot reuse
    the same focused-text evidence.

    This function does not publish receipts, establish focus, grant
    permission, or register itself as a model-facing tool.
    """

    try:
        from app.agent.focused_text_receipt import (
            FOCUSED_TEXT_RECEIPTS,
        )

        claimed = (
            FOCUSED_TEXT_RECEIPTS.claim(
                receipt
            )
        )

    except Exception:
        return ToolResult.fail(
            "Focused typing rejected because the exact "
            "single-use focused-text receipt is unavailable."
        )

    if (
        claimed
        is not receipt
    ):
        return ToolResult.fail(
            "Focused typing rejected because the claimed "
            "receipt identity changed."
        )

    try:
        text_evidence = (
            claimed.text_evidence
        )

        text = (
            text_evidence.raw_text
        )

    except Exception:
        return ToolResult.fail(
            "Focused typing rejected because the trusted "
            "text payload is unavailable."
        )

    if (
        type(text)
        is not str
        or not text
    ):
        return ToolResult.fail(
            "Focused typing rejected because the trusted "
            "text payload is invalid."
        )

    result = (
        type_text(
            text,
            interval=interval,
        )
    )

    if (
        type(result)
        is not ToolResult
    ):
        return ToolResult.fail(
            "Focused typing returned an invalid physical "
            "execution result."
        )

    return result


def press_key(
    key: str,
) -> ToolResult:
    """
    Press one known PyAutoGUI keyboard key.
    """

    effect_started = False

    try:
        if type(key) is not str:
            return ToolResult.fail(
                "Keyboard key must be a string."
            )

        key = (
            key.strip().lower()
        )

        if not key:
            return ToolResult.fail(
                "No key was provided."
            )

        if not SUPPORTED_KEYBOARD_KEYS:
            return ToolResult.fail(
                "Trusted keyboard-key registry "
                "is unavailable."
            )

        if key not in SUPPORTED_KEYBOARD_KEYS:
            return ToolResult.fail(
                f"Unsupported keyboard key: {key}"
            )

        _enforce_pyautogui_safety()

        effect_started = True

        pyautogui.press(
            key
        )

        return ToolResult.ok(
            f"Pressed key '{key}'.",
            effect_started=effect_started,
        )

    except Exception as error:
        return ToolResult.fail(
            f"Could not press key '{key}': {error}",
            effect_started=effect_started,
        )



def press_key_trusted(
    receipt,
) -> ToolResult:
    """Execute one exact single-use trusted keyboard receipt.

    This function is private infrastructure and MUST NOT be
    registered as a model-facing tool.
    """

    from app.agent.trusted_key_receipt import (
        TRUSTED_KEY_RECEIPTS,
        TrustedKeyReceipt,
    )

    if type(receipt) is not TrustedKeyReceipt:
        return ToolResult.fail(
            "Trusted key execution requires an exact receipt."
        )

    claimed = (
        TRUSTED_KEY_RECEIPTS.claim(
            receipt
        )
    )

    if claimed is None:
        return ToolResult.fail(
            "Trusted key receipt is unavailable, stale, or already consumed."
        )

    key = (
        claimed.key_evidence.raw_key
    )

    result = press_key(
        key
    )

    if type(result) is not ToolResult:
        return ToolResult.fail(
            "Trusted key execution returned an invalid physical result."
        )

    return result


# =========================================================
# SCROLL
# =========================================================

def scroll(
    amount: int,
) -> ToolResult:
    """
    Scroll vertically by a bounded amount.

    Positive values scroll up.
    Negative values scroll down.

    Larger navigation should occur through multiple
    observe → scroll → verify cycles.
    """

    effect_started = False

    try:
        if type(amount) is not int:
            return ToolResult.fail(
                "Scroll amount must be an integer."
            )

        if amount == 0:
            return ToolResult.ok(
                "No scrolling performed."
            )

        if (
            abs(amount)
            > MAX_SCROLL_UNITS
        ):
            return ToolResult.fail(
                "Scroll magnitude exceeds the "
                f"{MAX_SCROLL_UNITS}-unit per-action limit."
            )

        _enforce_pyautogui_safety()

        effect_started = True

        pyautogui.scroll(
            amount
        )

        direction = (
            "up"
            if amount > 0
            else "down"
        )

        return ToolResult.ok(
            f"Scrolled {direction} by "
            f"{abs(amount)}.",
            effect_started=effect_started,
        )

    except Exception as error:
        return ToolResult.fail(
            f"Could not scroll: {error}",
            effect_started=effect_started,
        )



def scroll_trusted(
    receipt,
) -> ToolResult:
    """Execute one exact single-use trusted scroll receipt."""

    from app.agent.trusted_scroll_receipt import (
        TRUSTED_SCROLL_RECEIPTS,
        TrustedScrollReceipt,
    )

    if (
        type(receipt)
        is not TrustedScrollReceipt
    ):
        return ToolResult.fail(
            "Trusted scroll execution requires an exact receipt."
        )

    claimed = (
        TRUSTED_SCROLL_RECEIPTS.claim(
            receipt
        )
    )

    if claimed is None:
        return ToolResult.fail(
            "Trusted scroll receipt is stale, invalid, "
            "already consumed, or its pointer context changed."
        )

    amount = (
        claimed
        .scroll_evidence
        .amount
    )

    result = scroll(
        amount
    )

    if type(result) is not ToolResult:
        return ToolResult.fail(
            "Trusted scroll returned an invalid physical result."
        )

    return result


# =========================================================
# SCREEN ANALYSIS
# =========================================================

def analyze_screen() -> ToolResult:
    """
    Capture and analyze the current screen with native desktop provenance.

    The physical screenshot is bracketed by two read-only native desktop
    observations before semantic analysis begins. The later ScreenObservation
    is published only if it finalizes against that exact capture bracket.

    Desktop evidence remains observation provenance only. It grants no GUI
    execution authority.
    """

    from app.vision.screen import (
        capture_screen,
        ScreenCaptureError,
    )

    from app.vision.analyzer import (
        analyze_image,
        VisionAnalysisError,
    )

    from app.vision.observation import (
        SCREEN_OBSERVATIONS,
        ScreenObservationError,
    )

    from app.desktop.runtime import (
        collect_desktop_context,
    )

    from app.desktop.screen_binding import (
        bracket_desktop_capture,
        finalize_screen_binding,
    )

    from app.desktop.provenance import (
        SCREEN_DESKTOP_PROVENANCE,
        ScreenDesktopProvenance,
    )

    from app.ui_observation.runtime import (
        collect_structured_ui,
    )

    from app.agent.gui_perception_context import (
        STRUCTURED_UI_SCREEN_CONTEXTS,
        publish_structured_ui_screen_context,
    )

    def clear_trusted_observation_state():
        SCREEN_OBSERVATIONS.clear()
        SCREEN_DESKTOP_PROVENANCE.clear()
        STRUCTURED_UI_SCREEN_CONTEXTS.clear()

    def desktop_capture_access_uncertain(context):
        return bool(
            {
                "screen_capture_access_unavailable",
                "screen_capture_access_unknown",
            }
            & set(context.diagnostics)
        )

    # A new perception attempt invalidates previous action-bound evidence.
    # Failure must never fall back to an older successful observation.
    clear_trusted_observation_state()

    try:
        before = collect_desktop_context(
            timeout_seconds=3.0,
            max_windows=32,
        )

        if before.status == "unavailable":
            return ToolResult.fail(
                "Could not establish trusted desktop context before screen capture."
            )

        before_app = before.active_application
        if (
            before_app is None
            or type(before_app.bundle_id) is not str
            or not before_app.bundle_id.strip()
        ):
            return ToolResult.fail(
                "Trusted desktop application identity is incomplete before screen capture."
            )

        if desktop_capture_access_uncertain(before):
            return ToolResult.fail(
                "Trusted desktop evidence cannot confirm screen-capture access."
            )

        image = capture_screen()

        # Preserve the historical ScreenObservation contract: this timestamp
        # is recorded immediately after the bounded OS capture returns, before
        # desktop-after collection or semantic analysis.
        captured_at = time.monotonic()

        # B8K1 opportunistically captures one read-only AX snapshot inside the
        # SAME desktop bracket as the trusted screen capture. Failure here does
        # not turn an observation-only analyze_screen call into an execution
        # failure; it simply means later dual-sensor click corroboration has no
        # structured context and must fail closed.
        try:
            structured_ui_observation = collect_structured_ui(
                before_app,
                timeout_seconds=2.0,
                max_nodes=128,
                max_depth=6,
                max_children=32,
            )
        except Exception:
            structured_ui_observation = None

        after = collect_desktop_context(
            timeout_seconds=3.0,
            max_windows=32,
        )

        if after.status == "unavailable":
            return ToolResult.fail(
                "Could not establish trusted desktop context after screen capture."
            )

        if desktop_capture_access_uncertain(after):
            return ToolResult.fail(
                "Trusted desktop evidence became uncertain after screen capture."
            )

        bracket_result = bracket_desktop_capture(
            captured_at,
            before,
            after,
            max_age_seconds=(
                SCREEN_OBSERVATIONS.max_age_seconds
            ),
            max_capture_gap_seconds=5.0,
        )

        if not bracket_result.bracketed:
            return ToolResult.fail(
                "Could not bind screen capture to trusted desktop context: "
                f"{bracket_result.diagnostics[0]}"
            )

        native_width, native_height = (
            pyautogui.size()
        )

        analysis = analyze_image(
            image,
        )

        observation = (
            SCREEN_OBSERVATIONS.create(
                captured_at_monotonic=(
                    captured_at
                ),
                capture_width=(
                    analysis.capture_width
                ),
                capture_height=(
                    analysis.capture_height
                ),
                vision_width=(
                    analysis.vision_width
                ),
                vision_height=(
                    analysis.vision_height
                ),
                native_width=int(
                    native_width
                ),
                native_height=int(
                    native_height
                ),
                vision_scale=(
                    analysis.vision_scale
                ),
                analysis=(
                    analysis.analysis
                ),
            )
        )

        binding_result = finalize_screen_binding(
            observation,
            bracket_result.bracket,
        )

        if not binding_result.linked:
            clear_trusted_observation_state()
            return ToolResult.fail(
                "Could not finalize trusted desktop provenance for screen observation: "
                f"{binding_result.diagnostics[0]}"
            )

        provenance = ScreenDesktopProvenance(
            binding=binding_result.binding,
            desktop_before=before,
            desktop_after=after,
        )

        if not SCREEN_DESKTOP_PROVENANCE.publish(
            provenance
        ):
            clear_trusted_observation_state()
            return ToolResult.fail(
                "Trusted desktop provenance expired before publication."
            )

        # B8K1 publishes only when an exact non-unavailable AX snapshot can be
        # bound to the same desktop-before/after IDs as this screen provenance.
        # The context remains evidence only and is not model-facing authority.
        if (
            structured_ui_observation is not None
            and getattr(structured_ui_observation, "status", None)
            != "unavailable"
        ):
            publish_structured_ui_screen_context(
                observation,
                structured_ui_observation,
                provenance,
            )

        return ToolResult.ok(
            str(
                observation
            ),
        )

    except ScreenCaptureError as error:
        clear_trusted_observation_state()
        return ToolResult.fail(
            f"Could not capture screen: {error}",
        )

    except VisionAnalysisError as error:
        clear_trusted_observation_state()
        return ToolResult.fail(
            f"Could not analyze screen: {error}",
        )

    except ScreenObservationError as error:
        clear_trusted_observation_state()
        return ToolResult.fail(
            f"Could not establish trusted screen observation: {error}",
        )

    except Exception as error:
        clear_trusted_observation_state()
        return ToolResult.fail(
            f"Screen analysis failed: {error}",
        )
