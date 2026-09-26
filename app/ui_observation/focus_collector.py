"""Read-only collection of one stable native focused AX element.

8D1B does not search the bounded structured Accessibility tree for focus.
The focused element is read directly from the frontmost application's native
kAXFocusedUIElementAttribute.

Native AX references remain local to the injected provider. The returned
FocusedUIObservation contains descriptive evidence only.
"""

from __future__ import annotations

import math
import time
from typing import Protocol

from app.desktop.contracts import (
    ApplicationIdentity,
)

from app.ui_observation.contracts import (
    MAX_UI_TEXT,
    optional_ui_text,
)

from app.ui_observation.focus_contracts import (
    FOCUS_STATUS_AVAILABLE,
    FocusedUIObservation,
    unavailable_focus,
)


class FocusProvider(Protocol):
    def accessibility_trusted(
        self,
    ) -> bool: ...

    def frontmost_application(
        self,
    ) -> ApplicationIdentity | None: ...

    def application_element(
        self,
        pid: int,
    ): ...

    def element_pid(
        self,
        element,
    ) -> int | None: ...

    def focused_element(
        self,
        application_element,
    ): ...

    def same_element(
        self,
        left,
        right,
    ) -> bool | None: ...

    def read_node(
        self,
        element,
    ) -> dict: ...

    def read_geometry(
        self,
        element,
    ) -> dict: ...


def _timestamp(
    value: object,
) -> bool:
    return (
        type(value) in (int, float)
        and math.isfinite(value)
        and value >= 0
    )


def _same_application(
    left,
    right,
) -> bool:
    return (
        type(left) is ApplicationIdentity
        and type(right) is ApplicationIdentity
        and type(left.pid) is int
        and type(right.pid) is int
        and left.pid == right.pid
        and type(left.bundle_id) is str
        and type(right.bundle_id) is str
        and bool(left.bundle_id.strip())
        and left.bundle_id
        == right.bundle_id
    )


def _complete_application(
    value,
) -> bool:
    return (
        type(value) is ApplicationIdentity
        and type(value.pid) is int
        and value.pid > 0
        and type(value.bundle_id) is str
        and bool(value.bundle_id.strip())
    )


def _optional_text(
    value,
):
    if not optional_ui_text(
        value
    ):
        raise ValueError(
            "Invalid focused-element text."
        )

    return value


def _optional_bool(
    value,
):
    if (
        value is not None
        and type(value) is not bool
    ):
        raise ValueError(
            "Invalid focused-element boolean."
        )

    return value


def _geometry_number(
    value,
    *,
    nonnegative=False,
):
    if (
        type(value) not in (int, float)
        or not math.isfinite(value)
    ):
        raise ValueError(
            "Invalid focused-element geometry."
        )

    if (
        nonnegative
        and value < 0
    ):
        raise ValueError(
            "Invalid focused-element geometry."
        )

    return value


def _normalized_geometry(
    raw,
):
    if type(raw) is not dict:
        raise ValueError(
            "Invalid focused-element geometry contract."
        )

    position_x = raw.get(
        "position_x"
    )
    position_y = raw.get(
        "position_y"
    )

    width = raw.get(
        "width"
    )
    height = raw.get(
        "height"
    )

    if (
        (position_x is None)
        != (position_y is None)
    ):
        raise ValueError(
            "Incomplete focused-element position."
        )

    if (
        (width is None)
        != (height is None)
    ):
        raise ValueError(
            "Incomplete focused-element size."
        )

    if position_x is not None:
        position_x = _geometry_number(
            position_x
        )
        position_y = _geometry_number(
            position_y
        )

    if width is not None:
        width = _geometry_number(
            width,
            nonnegative=True,
        )
        height = _geometry_number(
            height,
            nonnegative=True,
        )

    return {
        "position_x": position_x,
        "position_y": position_y,
        "width": width,
        "height": height,
    }


def collect_focused_ui(
    provider: FocusProvider,
    *,
    expected_application: ApplicationIdentity,
    clock=time.monotonic,
) -> FocusedUIObservation:
    """Collect one stable native focused-element observation.

    Stability requires:
    - exact frontmost application before collection,
    - exact focused AX element owner PID,
    - two native focused-element reads,
    - native CFEqual identity across those reads,
    - exact frontmost application after collection.

    This function grants no keyboard authority and performs no AX writes.
    """

    if not callable(
        clock
    ):
        raise TypeError(
            "clock must be callable."
        )

    try:
        captured_at = clock()
    except Exception as error:
        raise ValueError(
            "Focused UI collection clock is unavailable."
        ) from error

    if not _timestamp(
        captured_at
    ):
        raise ValueError(
            "Focused UI collection clock is invalid."
        )

    if not _complete_application(
        expected_application
    ):
        return unavailable_focus(
            "expected_application_incomplete",
            captured_at,
        )

    try:
        trusted = (
            provider.accessibility_trusted()
        )
    except Exception:
        return unavailable_focus(
            "collection_failed",
            captured_at,
        )

    if trusted is not True:
        return unavailable_focus(
            "accessibility_permission_denied",
            captured_at,
        )

    try:
        before = (
            provider.frontmost_application()
        )
    except Exception:
        return unavailable_focus(
            "active_application_unavailable",
            captured_at,
        )

    if not _same_application(
        before,
        expected_application,
    ):
        return unavailable_focus(
            (
                "active_application_unavailable"
                if before is None
                else "active_application_changed"
            ),
            captured_at,
        )

    try:
        application_element = (
            provider.application_element(
                expected_application.pid
            )
        )

        application_pid = (
            provider.element_pid(
                application_element
            )
            if application_element is not None
            else None
        )
    except Exception:
        application_element = None
        application_pid = None

    if (
        application_element is None
        or application_pid
        != expected_application.pid
    ):
        return unavailable_focus(
            "application_element_unavailable",
            captured_at,
        )

    # -----------------------------------------------------
    # FIRST EXACT NATIVE FOCUS READ
    # -----------------------------------------------------

    try:
        focused_before = (
            provider.focused_element(
                application_element
            )
        )
    except Exception:
        return unavailable_focus(
            "focused_element_read_failed",
            captured_at,
        )

    if focused_before is None:
        return unavailable_focus(
            "focused_element_unavailable",
            captured_at,
        )

    try:
        focused_pid = (
            provider.element_pid(
                focused_before
            )
        )
    except Exception:
        focused_pid = None

    if (
        focused_pid
        != expected_application.pid
    ):
        return unavailable_focus(
            "focused_element_foreign",
            captured_at,
        )

    # -----------------------------------------------------
    # BOUNDED DESCRIPTIVE METADATA
    # -----------------------------------------------------

    try:
        raw = provider.read_node(
            focused_before
        )

        if type(raw) is not dict:
            raise ValueError(
                "Invalid focused-element node contract."
            )

        owner_pid = raw.get(
            "owner_pid"
        )

        if (
            type(owner_pid) is not int
            or owner_pid
            != expected_application.pid
        ):
            return unavailable_focus(
                "focused_element_foreign",
                captured_at,
            )

        role = raw.get(
            "role"
        )

        if (
            type(role) is not str
            or not role.strip()
            or len(role) > MAX_UI_TEXT
        ):
            return unavailable_focus(
                "focused_element_role_unavailable",
                captured_at,
            )

        subrole = _optional_text(
            raw.get(
                "subrole"
            )
        )

        title = _optional_text(
            raw.get(
                "title"
            )
        )

        description = _optional_text(
            raw.get(
                "description"
            )
        )

        enabled = _optional_bool(
            raw.get(
                "enabled"
            )
        )

        geometry = (
            _normalized_geometry(
                provider.read_geometry(
                    focused_before
                )
            )
        )

    except Exception:
        return unavailable_focus(
            "focused_element_read_failed",
            captured_at,
        )

    # -----------------------------------------------------
    # SECOND EXACT NATIVE FOCUS READ
    # -----------------------------------------------------

    try:
        focused_after = (
            provider.focused_element(
                application_element
            )
        )
    except Exception:
        return unavailable_focus(
            "focused_element_read_failed",
            captured_at,
        )

    if focused_after is None:
        return unavailable_focus(
            "focus_changed_during_collection",
            captured_at,
        )

    try:
        same_focus = provider.same_element(
            focused_before,
            focused_after,
        )
    except Exception:
        same_focus = None

    if same_focus is None:
        return unavailable_focus(
            "focus_identity_unavailable",
            captured_at,
        )

    if same_focus is not True:
        return unavailable_focus(
            "focus_changed_during_collection",
            captured_at,
        )

    try:
        focused_after_pid = (
            provider.element_pid(
                focused_after
            )
        )
    except Exception:
        focused_after_pid = None

    if (
        focused_after_pid
        != expected_application.pid
    ):
        return unavailable_focus(
            "focused_element_foreign",
            captured_at,
        )

    # -----------------------------------------------------
    # FRONTMOST APPLICATION MUST ALSO REMAIN STABLE
    # -----------------------------------------------------

    try:
        after = (
            provider.frontmost_application()
        )
    except Exception:
        return unavailable_focus(
            "active_application_unavailable",
            captured_at,
        )

    if not _same_application(
        after,
        expected_application,
    ):
        return unavailable_focus(
            "active_application_changed",
            captured_at,
        )

    return FocusedUIObservation(
        captured_at_monotonic=captured_at,
        status=FOCUS_STATUS_AVAILABLE,
        active_application=before,
        role=role,
        subrole=subrole,
        title=title,
        description=description,
        enabled=enabled,
        **geometry,
    )
