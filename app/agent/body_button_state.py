from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import math
from threading import RLock
import time
from typing import Callable, Iterator


# =========================================================
# RUNTIME POINTER-BUTTON STATE
# =========================================================
#
# This module records only KUMA-owned runtime button state.
#
# It does NOT:
# - execute mouse input
# - grant GUI authority
# - grant permission
# - persist state
# - reconstruct state after restart
# - infer physical state from planner/model text
#
# A HELD state may be recorded only by the physical body
# boundary after a live mouse-down transition succeeds.
# =========================================================


BODY_BUTTON_CLEAR = "clear"
BODY_BUTTON_HELD = "held"
BODY_BUTTON_UNKNOWN = "unknown"

BODY_BUTTON_STATUSES = frozenset(
    {
        BODY_BUTTON_CLEAR,
        BODY_BUTTON_HELD,
        BODY_BUTTON_UNKNOWN,
    }
)

BODY_MOUSE_BUTTONS = frozenset(
    {
        "left",
        "right",
        "middle",
    }
)


class BodyButtonStateError(
    RuntimeError
):
    """Raised when a runtime finger-state transition is invalid."""


def _exact_mouse_button(
    button: object,
) -> str:

    if (
        type(button) is not str
        or button not in BODY_MOUSE_BUTTONS
    ):
        raise BodyButtonStateError(
            "Mouse button identity must be exactly one of: "
            "left, right, middle."
        )

    return button


def _finite_monotonic(
    value: object,
) -> float:

    if (
        isinstance(value, bool)
        or not isinstance(
            value,
            (int, float),
        )
    ):
        raise BodyButtonStateError(
            "Button-state monotonic time must be a finite number."
        )

    value = float(
        value
    )

    if (
        not math.isfinite(value)
        or value < 0.0
    ):
        raise BodyButtonStateError(
            "Button-state monotonic time must be a finite "
            "non-negative number."
        )

    return value


@dataclass(
    frozen=True,
    slots=True,
)
class BodyButtonSnapshot:
    """
    Immutable observation of KUMA-owned pointer-button state.

    CLEAR:
        button is None.

    HELD:
        KUMA has successfully issued a live mouse-down transition
        for exactly `button`, with no later successful release.

    UNKNOWN:
        KUMA attempted a physical transition whose final button
        state could not be established safely. `button` identifies
        the only button KUMA is permitted to recover by releasing.

    This object is descriptive only. Constructing one does not
    change runtime state or grant physical authority.
    """

    status: str
    button: str | None
    generation: int
    changed_at_monotonic: float

    def __post_init__(
        self,
    ) -> None:

        if (
            type(self.status) is not str
            or self.status
            not in BODY_BUTTON_STATUSES
        ):
            raise BodyButtonStateError(
                "Invalid body-button status."
            )

        if (
            type(self.generation) is not int
            or self.generation < 0
        ):
            raise BodyButtonStateError(
                "Button-state generation must be a "
                "non-negative integer."
            )

        _finite_monotonic(
            self.changed_at_monotonic
        )

        if (
            self.status
            == BODY_BUTTON_CLEAR
        ):
            if self.button is not None:
                raise BodyButtonStateError(
                    "CLEAR button state must not name a button."
                )

            return

        _exact_mouse_button(
            self.button
        )


class BodyButtonStateStore:
    """
    Process-local state machine for KUMA-owned mouse-button state.

    Mutating transition methods are intentionally private to this
    runtime contract. Production callers should be the physical
    body boundary only.

    There is deliberately no public clear/reset/set/from_dict API.
    A live HELD/UNKNOWN state must not disappear because planner,
    recovery, persistence, or model code asks for a cleaner state.
    """

    def __init__(
        self,
        *,
        clock: Callable[[], float] | None = None,
    ) -> None:

        if (
            clock is not None
            and not callable(clock)
        ):
            raise TypeError(
                "clock must be callable."
            )

        self._clock = (
            time.monotonic
            if clock is None
            else clock
        )

        self._lock = RLock()

        self._state = BodyButtonSnapshot(
            status=BODY_BUTTON_CLEAR,
            button=None,
            generation=0,
            changed_at_monotonic=(
                self._now()
            ),
        )

    def _now(
        self,
    ) -> float:

        try:
            value = self._clock()

        except Exception as error:
            raise BodyButtonStateError(
                "Could not read button-state monotonic clock."
            ) from error

        return _finite_monotonic(
            value
        )

    def snapshot(
        self,
    ) -> BodyButtonSnapshot:

        with self._lock:
            return self._state

    @contextmanager
    def serialized_transition(
        self,
    ) -> Iterator[BodyButtonSnapshot]:
        """
        Serialize check → physical effect → state-record operations.

        Future pointer-effect tools must hold this boundary while
        checking current finger state and issuing their corresponding
        physical transition. The lock is reentrant so state methods
        remain safe inside the boundary.
        """

        with self._lock:
            yield self._state

    def _next(
        self,
        *,
        status: str,
        button: str | None,
    ) -> BodyButtonSnapshot:

        next_state = BodyButtonSnapshot(
            status=status,
            button=button,
            generation=(
                self._state.generation
                + 1
            ),
            changed_at_monotonic=(
                self._now()
            ),
        )

        self._state = next_state

        return next_state

    def _record_press_success(
        self,
        button: object,
    ) -> BodyButtonSnapshot:
        """
        Record a mouse-down transition only after the physical
        boundary reports that live mouseDown returned successfully.
        """

        button = _exact_mouse_button(
            button
        )

        with self._lock:

            if (
                self._state.status
                != BODY_BUTTON_CLEAR
            ):
                raise BodyButtonStateError(
                    "Cannot record mouse-down success unless "
                    "KUMA-owned button state is CLEAR."
                )

            return self._next(
                status=BODY_BUTTON_HELD,
                button=button,
            )

    def _record_release_success(
        self,
        button: object,
    ) -> BodyButtonSnapshot:
        """
        Record CLEAR only after a live mouseUp for the exact
        HELD/UNKNOWN button returns successfully.
        """

        button = _exact_mouse_button(
            button
        )

        with self._lock:

            if self._state.status not in {
                BODY_BUTTON_HELD,
                BODY_BUTTON_UNKNOWN,
            }:
                raise BodyButtonStateError(
                    "Cannot record mouse-up success when no "
                    "KUMA-owned button may be down."
                )

            if (
                self._state.button
                != button
            ):
                raise BodyButtonStateError(
                    "Mouse-up button does not match the exact "
                    "KUMA-owned held/unknown button."
                )

            return self._next(
                status=BODY_BUTTON_CLEAR,
                button=None,
            )

    def _record_uncertain(
        self,
        button: object,
    ) -> BodyButtonSnapshot:
        """
        Fail closed after an ambiguous physical transition.

        UNKNOWN retains the exact candidate button so the recovery
        boundary can attempt only that button's mouseUp operation.
        """

        button = _exact_mouse_button(
            button
        )

        with self._lock:

            if (
                self._state.status
                in {
                    BODY_BUTTON_HELD,
                    BODY_BUTTON_UNKNOWN,
                }
                and self._state.button
                != button
            ):
                raise BodyButtonStateError(
                    "Cannot replace an existing held/unknown "
                    "button with a different button identity."
                )

            # UNKNOWN is KUMA's fail-closed emergency state.
            #
            # Recording it must not depend on the runtime clock
            # remaining healthy. If the clock fails after an
            # ambiguous physical transition, preserve the previous
            # known-good timestamp rather than leaving state CLEAR
            # or HELD merely because metadata could not advance.
            try:
                changed_at_monotonic = (
                    self._now()
                )
            except BaseException:
                changed_at_monotonic = (
                    self._state.changed_at_monotonic
                )

            next_state = BodyButtonSnapshot(
                status=BODY_BUTTON_UNKNOWN,
                button=button,
                generation=(
                    self._state.generation
                    + 1
                ),
                changed_at_monotonic=(
                    changed_at_monotonic
                ),
            )

            self._state = next_state

            return next_state


BODY_BUTTON_STATE = (
    BodyButtonStateStore()
)
