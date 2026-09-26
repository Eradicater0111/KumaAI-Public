"""Immutable, read-only evidence for one native focused AX element.

8D1 focus evidence is deliberately separate from StructuredUIObservation.

The bounded structured UI tree describes discoverable AX structure.
FocusedUIObservation describes the one exact native element returned through
the application's kAXFocusedUIElementAttribute during an isolated collection.

This contract contains no AX object, tree path, model authority, permission,
keyboard authority, execution state, or stable cross-snapshot identity.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import math
from uuid import uuid4

from app.desktop.contracts import ApplicationIdentity
from app.ui_observation.contracts import (
    MAX_UI_TEXT,
    optional_ui_text,
)


FOCUS_STATUS_AVAILABLE = "available"
FOCUS_STATUS_UNAVAILABLE = "unavailable"

FOCUS_STATUSES = frozenset({
    FOCUS_STATUS_AVAILABLE,
    FOCUS_STATUS_UNAVAILABLE,
})


FOCUS_DIAGNOSTICS = frozenset({
    "unsupported_platform",
    "native_api_unavailable",
    "collection_failed",
    "expected_application_incomplete",
    "accessibility_permission_denied",
    "active_application_unavailable",
    "active_application_changed",
    "application_element_unavailable",
    "focused_element_unavailable",
    "focused_element_foreign",
    "focused_element_read_failed",
    "focused_element_role_unavailable",
    "focus_identity_unavailable",
    "focus_changed_during_collection",
    "collection_timeout",
    "worker_failed",
    "worker_output_invalid",
    "collection_busy",
})


FOCUS_OBSERVATION_SCOPE = (
    "frontmost_application_focused_ui_element"
)


FOCUS_OBSERVATION_FIELDS = frozenset({
    "captured_at_monotonic",
    "status",
    "active_application",
    "role",
    "subrole",
    "title",
    "description",
    "enabled",
    "position_x",
    "position_y",
    "width",
    "height",
    "diagnostics",
    "observation_id",
    "scope",
})


def _timestamp(value: object) -> bool:
    return (
        type(value) in (int, float)
        and math.isfinite(value)
        and value >= 0
    )


def _identifier(value: object) -> bool:
    return (
        type(value) is str
        and len(value) == 32
        and all(
            character in "0123456789abcdef"
            for character in value
        )
    )


def _complete_application(
    value: object,
) -> bool:
    return (
        type(value) is ApplicationIdentity
        and type(value.pid) is int
        and value.pid > 0
        and type(value.bundle_id) is str
        and bool(value.bundle_id.strip())
    )


def _role(value: object) -> bool:
    return (
        type(value) is str
        and 0 < len(value) <= MAX_UI_TEXT
        and bool(value.strip())
    )


def _geometry_number(
    value: object,
    *,
    nonnegative: bool = False,
) -> bool:
    if (
        type(value) not in (int, float)
        or not math.isfinite(value)
    ):
        return False

    if (
        nonnegative
        and value < 0
    ):
        return False

    return True


@dataclass(frozen=True)
class FocusedUIObservation:
    """One immutable snapshot of the native focused AX element.

    ``available`` means a trusted collector established focus through the
    application's native focused-element attribute and emitted the element's
    bounded descriptive metadata.

    The serialized record does not contain the native AX object itself.
    Therefore it cannot claim stable native identity across collections.

    It is evidence only and grants no permission or keyboard authority.
    """

    captured_at_monotonic: float
    status: str

    active_application: (
        ApplicationIdentity | None
    ) = None

    role: str | None = None
    subrole: str | None = None

    title: str | None = field(
        default=None,
        repr=False,
    )
    description: str | None = field(
        default=None,
        repr=False,
    )

    enabled: bool | None = None

    position_x: float | None = None
    position_y: float | None = None
    width: float | None = None
    height: float | None = None

    diagnostics: tuple[str, ...] = ()

    observation_id: str = field(
        default_factory=lambda: uuid4().hex
    )

    scope: str = FOCUS_OBSERVATION_SCOPE

    def __post_init__(self):
        if not _timestamp(
            self.captured_at_monotonic
        ):
            raise ValueError(
                "Invalid focused UI observation timestamp."
            )

        if (
            type(self.status) is not str
            or self.status not in FOCUS_STATUSES
        ):
            raise ValueError(
                "Invalid focused UI observation status."
            )

        if not _identifier(
            self.observation_id
        ):
            raise ValueError(
                "Invalid focused UI observation identity."
            )

        if (
            self.scope
            != FOCUS_OBSERVATION_SCOPE
        ):
            raise ValueError(
                "Invalid focused UI observation scope."
            )

        if (
            type(self.diagnostics) is not tuple
            or any(
                type(code) is not str
                or code not in FOCUS_DIAGNOSTICS
                for code in self.diagnostics
            )
            or len(set(self.diagnostics))
            != len(self.diagnostics)
        ):
            raise ValueError(
                "Invalid focused UI diagnostics."
            )

        for value in (
            self.subrole,
            self.title,
            self.description,
        ):
            if not optional_ui_text(value):
                raise ValueError(
                    "Invalid focused UI bounded text."
                )

        if (
            self.enabled is not None
            and type(self.enabled) is not bool
        ):
            raise ValueError(
                "Focused UI enabled state must be "
                "boolean or unknown."
            )

        point = (
            self.position_x,
            self.position_y,
        )

        if (
            (point[0] is None)
            != (point[1] is None)
        ):
            raise ValueError(
                "Focused UI position must be "
                "complete or unknown."
            )

        for value in point:
            if (
                value is not None
                and not _geometry_number(value)
            ):
                raise ValueError(
                    "Focused UI position must be finite."
                )

        size = (
            self.width,
            self.height,
        )

        if (
            (size[0] is None)
            != (size[1] is None)
        ):
            raise ValueError(
                "Focused UI size must be "
                "complete or unknown."
            )

        for value in size:
            if (
                value is not None
                and not _geometry_number(
                    value,
                    nonnegative=True,
                )
            ):
                raise ValueError(
                    "Focused UI size must be finite "
                    "and nonnegative."
                )

        if (
            self.status
            == FOCUS_STATUS_AVAILABLE
        ):
            if not _complete_application(
                self.active_application
            ):
                raise ValueError(
                    "Available focus evidence requires "
                    "complete application identity."
                )

            if not _role(
                self.role
            ):
                raise ValueError(
                    "Available focus evidence requires "
                    "an exact AX role."
                )

            if self.diagnostics:
                raise ValueError(
                    "Available focus evidence cannot "
                    "contain diagnostics."
                )

            return

        # Unavailable evidence is deliberately non-partial.
        #
        # No stale application, semantic, geometry, or state
        # claims survive a failed focus collection.
        if (
            self.active_application is not None
            or self.role is not None
            or self.subrole is not None
            or self.title is not None
            or self.description is not None
            or self.enabled is not None
            or self.position_x is not None
            or self.position_y is not None
            or self.width is not None
            or self.height is not None
        ):
            raise ValueError(
                "Unavailable focus evidence cannot "
                "carry focused-element claims."
            )

        if len(self.diagnostics) != 1:
            raise ValueError(
                "Unavailable focus evidence requires "
                "one diagnostic."
            )

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(
        cls,
        payload,
    ) -> "FocusedUIObservation":
        if type(payload) is not dict:
            raise ValueError(
                "Focused UI observation payload "
                "must be an object."
            )

        data = dict(payload)

        unknown = (
            set(data)
            - FOCUS_OBSERVATION_FIELDS
        )

        if unknown:
            raise ValueError(
                "Focused UI observation contains "
                "unsupported fields."
            )

        diagnostics = data.get(
            "diagnostics"
        )

        if type(diagnostics) is not list:
            raise ValueError(
                "Focused UI observation diagnostics "
                "must be a list payload."
            )

        data["diagnostics"] = tuple(
            diagnostics
        )

        application = data.get(
            "active_application"
        )

        if application is not None:
            if type(application) is not dict:
                raise ValueError(
                    "Focused UI application identity "
                    "payload is invalid."
                )

            data["active_application"] = (
                ApplicationIdentity(
                    **application
                )
            )

        return cls(
            **data
        )


def unavailable_focus(
    code: str,
    captured_at_monotonic: float,
) -> FocusedUIObservation:
    return FocusedUIObservation(
        captured_at_monotonic=(
            captured_at_monotonic
        ),
        status=FOCUS_STATUS_UNAVAILABLE,
        diagnostics=(code,),
    )
