"""Same-process native focus/semantic-target correlation for KUMA 8D2.

The semantic target is resolved independently and completely before native
focus is consulted.

Only after exactly one semantic candidate exists may focus verify that target.

The provider retains native AX references inside one process. Native references
never appear in the returned correlation evidence.

This module performs no native import, AX write, permission decision, keyboard
action, target authorization, persistence, or physical execution.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import time
from typing import Protocol

from app.desktop.contracts import (
    ApplicationIdentity,
)
from app.ui_observation.contracts import (
    MAX_UI_TEXT,
)
import app.ui_observation.target_resolution as target_resolution
from app.ui_observation.target_resolution import (
    StructuredUITargetSelector,
)


MAX_FOCUS_TARGET_NODES = 1024
MAX_FOCUS_TARGET_DEPTH = 16
MAX_FOCUS_TARGET_CHILDREN = 128

CORRELATION_STATUS_MATCHED = (
    "matched"
)

CORRELATION_STATUS_MISMATCHED = (
    "mismatched"
)

CORRELATION_STATUS_AMBIGUOUS = (
    "ambiguous"
)

CORRELATION_STATUS_UNKNOWN = (
    "unknown"
)

VALID_CORRELATION_STATUSES = frozenset({
    CORRELATION_STATUS_MATCHED,
    CORRELATION_STATUS_MISMATCHED,
    CORRELATION_STATUS_AMBIGUOUS,
    CORRELATION_STATUS_UNKNOWN,
})

MISMATCH_CODE = (
    "focused_target_mismatch"
)

AMBIGUOUS_CODE = (
    "multiple_candidates"
)

UNKNOWN_CODES = frozenset({
    "expected_application_incomplete",
    "accessibility_permission_denied",
    "active_application_unavailable",
    "active_application_changed",
    "application_element_unavailable",
    "observation_incomplete",
    "no_semantic_match",
    "candidate_eligibility_unknown",
    "no_eligible_candidate",
    "focused_element_unavailable",
    "focused_element_foreign",
    "focused_element_read_failed",
    "focus_identity_unavailable",
    "focus_changed_during_collection",
    "unsupported_platform",
    "native_api_unavailable",
    "collection_failed",
    "collection_timeout",
    "worker_failed",
    "worker_output_invalid",
    "collection_busy",
})


class FocusTargetCorrelationProvider(
    Protocol
):
    """Injected provider retaining native identity in one process."""

    def accessibility_trusted(
        self,
    ) -> bool:
        ...

    def frontmost_application(
        self,
    ) -> ApplicationIdentity | None:
        ...

    def application_element(
        self,
        pid: int,
    ):
        ...

    def element_pid(
        self,
        element,
    ) -> int | None:
        ...

    def read_target_node(
        self,
        element,
        selector: StructuredUITargetSelector,
    ) -> dict:
        """Read selector-relevant semantic/eligibility evidence only.

        Hard failure of an attribute required by the selector must raise.
        Unsupported/no-value evidence may be represented as None when that
        absence is itself trustworthy.
        """

        ...

    def children_for_element(
        self,
        element,
        limit: int,
    ) -> tuple[list, bool]:
        ...

    def element_identity(
        self,
        element,
    ):
        ...

    def focused_element(
        self,
        application_element,
    ):
        ...

    def same_element(
        self,
        left,
        right,
    ) -> bool | None:
        ...


def _timestamp(
    value,
):
    return (
        type(value) in (
            int,
            float,
        )
        and math.isfinite(
            value
        )
        and value >= 0
    )


def _complete_application(
    value,
):
    return (
        type(value)
        is ApplicationIdentity
        and type(value.pid)
        is int
        and value.pid > 0
        and type(value.bundle_id)
        is str
        and bool(
            value.bundle_id
        )
    )


def _same_application(
    left,
    right,
):
    return (
        _complete_application(
            left
        )
        and _complete_application(
            right
        )
        and left.pid
        == right.pid
        and left.bundle_id
        == right.bundle_id
    )


def _bounded_optional_text(
    value,
):
    if value is None:
        return None

    if (
        type(value) is not str
        or len(value)
        > MAX_UI_TEXT
    ):
        raise ValueError(
            "Invalid bounded target text."
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
            "Invalid target boolean evidence."
        )

    return value


def _geometry_number(
    value,
    *,
    nonnegative=False,
):
    if value is None:
        return None

    if (
        type(value)
        not in (
            int,
            float,
        )
        or not math.isfinite(
            value
        )
    ):
        raise ValueError(
            "Invalid target geometry."
        )

    value = float(
        value
    )

    if (
        nonnegative
        and value < 0
    ):
        raise ValueError(
            "Invalid target geometry."
        )

    return value


def _validate_limits(
    max_nodes,
    max_depth,
    max_children,
):
    if (
        type(max_nodes)
        is not int
        or not (
            1
            <= max_nodes
            <= MAX_FOCUS_TARGET_NODES
        )
    ):
        raise ValueError(
            "max_nodes is outside the "
            "dedicated 8D2 bound."
        )

    if (
        type(max_depth)
        is not int
        or not (
            0
            <= max_depth
            <= MAX_FOCUS_TARGET_DEPTH
        )
    ):
        raise ValueError(
            "max_depth is outside the "
            "dedicated 8D2 bound."
        )

    if (
        type(max_children)
        is not int
        or not (
            1
            <= max_children
            <= MAX_FOCUS_TARGET_CHILDREN
        )
    ):
        raise ValueError(
            "max_children is outside the "
            "dedicated 8D2 bound."
        )


@dataclass(frozen=True)
class FocusTargetSemanticCandidate:
    """Serializable semantic candidate metadata only.

    ``path`` is a snapshot-local diagnostic/join key.
    It is not native identity and grants no authority.
    """

    path: tuple[int, ...]
    owner_pid: int
    role: str | None
    subrole: str | None
    title: str | None
    description: str | None
    enabled: bool | None
    position_x: float | None
    position_y: float | None
    width: float | None
    height: float | None

    def __post_init__(
        self,
    ):
        if (
            type(self.path)
            is not tuple
            or len(
                self.path
            )
            > MAX_FOCUS_TARGET_DEPTH
            or any(
                type(index)
                is not int
                or index < 0
                or index
                >= MAX_FOCUS_TARGET_CHILDREN
                for index
                in self.path
            )
        ):
            raise ValueError(
                "Invalid focus-target candidate path."
            )

        if (
            type(self.owner_pid)
            is not int
            or self.owner_pid <= 0
        ):
            raise ValueError(
                "Invalid focus-target candidate ownership."
            )

        for value in (
            self.role,
            self.subrole,
            self.title,
            self.description,
        ):
            _bounded_optional_text(
                value
            )

        _optional_bool(
            self.enabled
        )

        px = _geometry_number(
            self.position_x
        )

        py = _geometry_number(
            self.position_y
        )

        width = _geometry_number(
            self.width,
            nonnegative=True,
        )

        height = _geometry_number(
            self.height,
            nonnegative=True,
        )

        if (
            (
                px is None
            )
            != (
                py is None
            )
            or (
                width is None
            )
            != (
                height is None
            )
        ):
            raise ValueError(
                "Incomplete focus-target geometry."
            )


@dataclass(frozen=True)
class FocusTargetCorrelationResult:
    """Result of independent semantic resolution plus native focus verification."""

    captured_at_monotonic: float
    status: str
    expected_application: ApplicationIdentity
    selector: StructuredUITargetSelector
    candidate_count: int = 0
    candidate: FocusTargetSemanticCandidate | None = None
    diagnostics: tuple[str, ...] = ()

    def __post_init__(
        self,
    ):
        if not _timestamp(
            self.captured_at_monotonic
        ):
            raise ValueError(
                "Invalid correlation timestamp."
            )

        if (
            type(self.status)
            is not str
            or self.status
            not in VALID_CORRELATION_STATUSES
        ):
            raise ValueError(
                "Invalid focus-target correlation status."
            )

        if (
            type(self.expected_application)
            is not ApplicationIdentity
        ):
            raise ValueError(
                "Exact expected application is required."
            )

        if (
            type(self.selector)
            is not StructuredUITargetSelector
        ):
            raise ValueError(
                "Exact semantic selector is required."
            )

        if (
            type(self.candidate_count)
            is not int
            or self.candidate_count < 0
        ):
            raise ValueError(
                "Invalid correlation candidate count."
            )

        if (
            type(self.diagnostics)
            is not tuple
            or any(
                type(code)
                is not str
                for code
                in self.diagnostics
            )
            or len(
                set(
                    self.diagnostics
                )
            )
            != len(
                self.diagnostics
            )
        ):
            raise ValueError(
                "Invalid correlation diagnostics."
            )

        if (
            self.status
            == CORRELATION_STATUS_MATCHED
        ):
            if (
                type(self.candidate)
                is not FocusTargetSemanticCandidate
                or self.candidate_count != 1
                or self.diagnostics != ()
            ):
                raise ValueError(
                    "Matched correlation requires "
                    "one exact semantic candidate."
                )

            if (
                not _complete_application(
                    self.expected_application
                )
                or self.candidate.owner_pid
                != self.expected_application.pid
                or target_resolution
                ._semantic_possibility(
                    self.candidate,
                    self.selector,
                )
                is not True
                or target_resolution
                ._eligibility(
                    self.candidate,
                    self.selector,
                )
                is not True
            ):
                raise ValueError(
                    "Matched candidate does not satisfy "
                    "its exact semantic source contract."
                )

            return

        if (
            self.status
            == CORRELATION_STATUS_MISMATCHED
        ):
            if (
                type(self.candidate)
                is not FocusTargetSemanticCandidate
                or self.candidate_count != 1
                or self.diagnostics
                != (
                    MISMATCH_CODE,
                )
            ):
                raise ValueError(
                    "Mismatched correlation requires "
                    "one exact semantic candidate."
                )

            if (
                not _complete_application(
                    self.expected_application
                )
                or self.candidate.owner_pid
                != self.expected_application.pid
                or target_resolution
                ._semantic_possibility(
                    self.candidate,
                    self.selector,
                )
                is not True
                or target_resolution
                ._eligibility(
                    self.candidate,
                    self.selector,
                )
                is not True
            ):
                raise ValueError(
                    "Mismatched candidate does not satisfy "
                    "its exact semantic source contract."
                )

            return

        if self.candidate is not None:
            raise ValueError(
                "Unresolved correlation cannot "
                "carry candidate evidence."
            )

        if (
            self.status
            == CORRELATION_STATUS_AMBIGUOUS
        ):
            if (
                self.candidate_count < 2
                or self.diagnostics
                != (
                    AMBIGUOUS_CODE,
                )
            ):
                raise ValueError(
                    "Ambiguous correlation requires "
                    "multiple candidates."
                )

            return

        if (
            len(
                self.diagnostics
            )
            != 1
            or self.diagnostics[0]
            not in UNKNOWN_CODES
        ):
            raise ValueError(
                "Unknown correlation requires "
                "one structured diagnostic."
            )

    @property
    def matched(
        self,
    ):
        return (
            self.status
            == CORRELATION_STATUS_MATCHED
        )


def _candidate_from_raw(
    raw,
    *,
    path,
    owner_pid,
):
    if type(raw) is not dict:
        raise ValueError(
            "Invalid target-node contract."
        )

    position_x = _geometry_number(
        raw.get(
            "position_x"
        )
    )

    position_y = _geometry_number(
        raw.get(
            "position_y"
        )
    )

    width = _geometry_number(
        raw.get(
            "width"
        ),
        nonnegative=True,
    )

    height = _geometry_number(
        raw.get(
            "height"
        ),
        nonnegative=True,
    )

    if (
        (
            position_x is None
        )
        != (
            position_y is None
        )
        or (
            width is None
        )
        != (
            height is None
        )
    ):
        raise ValueError(
            "Incomplete target geometry."
        )

    return FocusTargetSemanticCandidate(
        path=path,
        owner_pid=owner_pid,
        role=_bounded_optional_text(
            raw.get(
                "role"
            )
        ),
        subrole=_bounded_optional_text(
            raw.get(
                "subrole"
            )
        ),
        title=_bounded_optional_text(
            raw.get(
                "title"
            )
        ),
        description=_bounded_optional_text(
            raw.get(
                "description"
            )
        ),
        enabled=_optional_bool(
            raw.get(
                "enabled"
            )
        ),
        position_x=position_x,
        position_y=position_y,
        width=width,
        height=height,
    )


def collect_focus_target_correlation(
    provider: FocusTargetCorrelationProvider,
    *,
    expected_application: ApplicationIdentity,
    selector: StructuredUITargetSelector,
    max_nodes=MAX_FOCUS_TARGET_NODES,
    max_depth=MAX_FOCUS_TARGET_DEPTH,
    max_children=MAX_FOCUS_TARGET_CHILDREN,
    clock=time.monotonic,
):
    """Resolve semantic intent first, then verify native focus identity.

    Focus is not read until the complete bounded semantic traversal has already
    established exactly one independently eligible candidate.
    """

    _validate_limits(
        max_nodes,
        max_depth,
        max_children,
    )

    if not callable(
        clock
    ):
        raise TypeError(
            "clock must be callable."
        )

    try:
        captured_at = (
            clock()
        )
    except Exception:
        raise ValueError(
            "clock is unavailable."
        ) from None

    if not _timestamp(
        captured_at
    ):
        raise ValueError(
            "clock is unavailable."
        )

    if (
        type(expected_application)
        is not ApplicationIdentity
        or type(selector)
        is not StructuredUITargetSelector
    ):
        raise TypeError(
            "Exact application and selector contracts are required."
        )

    def result(
        status,
        *,
        candidate_count=0,
        candidate=None,
        diagnostics=(),
    ):
        return FocusTargetCorrelationResult(
            captured_at_monotonic=(
                captured_at
            ),
            status=status,
            expected_application=(
                expected_application
            ),
            selector=selector,
            candidate_count=(
                candidate_count
            ),
            candidate=candidate,
            diagnostics=diagnostics,
        )

    def unknown(
        code,
        *,
        candidate_count=0,
    ):
        return result(
            CORRELATION_STATUS_UNKNOWN,
            candidate_count=(
                candidate_count
            ),
            diagnostics=(
                code,
            ),
        )

    if not _complete_application(
        expected_application
    ):
        return unknown(
            "expected_application_incomplete"
        )

    try:
        trusted = (
            provider.accessibility_trusted()
        )
    except Exception:
        trusted = False

    if trusted is not True:
        return unknown(
            "accessibility_permission_denied"
        )

    try:
        before = (
            provider.frontmost_application()
        )
    except Exception:
        before = None

    if not _same_application(
        before,
        expected_application,
    ):
        return unknown(
            (
                "active_application_unavailable"
                if before is None
                else "active_application_changed"
            )
        )

    try:
        root = (
            provider.application_element(
                expected_application.pid
            )
        )

        root_pid = (
            provider.element_pid(
                root
            )
            if root is not None
            else None
        )
    except Exception:
        root = None
        root_pid = None

    if (
        root is None
        or root_pid
        != expected_application.pid
    ):
        return unknown(
            "application_element_unavailable"
        )

    stack = [
        (
            root,
            (),
            0,
        )
    ]

    seen = set()
    observed = []

    visited = 0
    incomplete = False

    while (
        stack
        and visited < max_nodes
    ):
        element, path, depth = (
            stack.pop()
        )

        visited += 1

        try:
            identity = (
                provider.element_identity(
                    element
                )
            )
        except Exception:
            incomplete = True
            break

        if identity in seen:
            incomplete = True
            break

        seen.add(
            identity
        )

        try:
            owner_pid = (
                provider.element_pid(
                    element
                )
            )
        except Exception:
            owner_pid = None

        if (
            owner_pid
            != expected_application.pid
        ):
            incomplete = True
            break

        try:
            raw = (
                provider.read_target_node(
                    element,
                    selector,
                )
            )

            candidate = (
                _candidate_from_raw(
                    raw,
                    path=path,
                    owner_pid=owner_pid,
                )
            )
        except Exception:
            incomplete = True
            break

        observed.append(
            (
                element,
                candidate,
            )
        )

        if depth >= max_depth:
            try:
                probe, more = (
                    provider.children_for_element(
                        element,
                        1,
                    )
                )

                if (
                    type(probe) is not list
                    or type(more) is not bool
                    or probe
                    or more
                ):
                    incomplete = True
                    break

            except Exception:
                incomplete = True
                break

            continue

        try:
            children, truncated = (
                provider.children_for_element(
                    element,
                    max_children,
                )
            )

            if (
                type(children) is not list
                or type(truncated) is not bool
                or len(children)
                > max_children
                or truncated
            ):
                incomplete = True
                break

        except Exception:
            incomplete = True
            break

        for child_index in range(
            len(children) - 1,
            -1,
            -1,
        ):
            stack.append(
                (
                    children[
                        child_index
                    ],
                    path
                    + (
                        child_index,
                    ),
                    depth + 1,
                )
            )

    if stack:
        incomplete = True

    if incomplete:
        return unknown(
            "observation_incomplete"
        )

    semantic = []
    semantic_unknown = False

    for native_element, candidate in observed:
        state = (
            target_resolution
            ._semantic_possibility(
                candidate,
                selector,
            )
        )

        if state is True:
            semantic.append(
                (
                    native_element,
                    candidate,
                )
            )

        elif state is None:
            semantic_unknown = True

    eligible = []
    uncertain = []

    for native_element, candidate in semantic:
        state = (
            target_resolution
            ._eligibility(
                candidate,
                selector,
            )
        )

        if state is True:
            eligible.append(
                (
                    native_element,
                    candidate,
                )
            )

        elif state is None:
            uncertain.append(
                (
                    native_element,
                    candidate,
                )
            )

    if len(
        eligible
    ) >= 2:
        return result(
            CORRELATION_STATUS_AMBIGUOUS,
            candidate_count=len(
                eligible
            ),
            diagnostics=(
                AMBIGUOUS_CODE,
            ),
        )

    if uncertain:
        return unknown(
            "candidate_eligibility_unknown",
            candidate_count=(
                len(
                    eligible
                )
                + len(
                    uncertain
                )
            ),
        )

    if semantic_unknown:
        return unknown(
            "observation_incomplete",
            candidate_count=len(
                eligible
            ),
        )

    if not semantic:
        return unknown(
            "no_semantic_match"
        )

    if not eligible:
        return unknown(
            "no_eligible_candidate"
        )

    native_candidate, candidate = (
        eligible[0]
    )

    try:
        middle = (
            provider.frontmost_application()
        )
    except Exception:
        middle = None

    if not _same_application(
        middle,
        expected_application,
    ):
        return unknown(
            (
                "active_application_unavailable"
                if middle is None
                else "active_application_changed"
            ),
            candidate_count=1,
        )

    try:
        focus_before = (
            provider.focused_element(
                root
            )
        )
    except Exception:
        return unknown(
            "focused_element_read_failed",
            candidate_count=1,
        )

    if focus_before is None:
        return unknown(
            "focused_element_unavailable",
            candidate_count=1,
        )

    try:
        focus_before_pid = (
            provider.element_pid(
                focus_before
            )
        )
    except Exception:
        focus_before_pid = None

    if (
        focus_before_pid
        != expected_application.pid
    ):
        return unknown(
            "focused_element_foreign",
            candidate_count=1,
        )

    try:
        candidate_matches_before = (
            provider.same_element(
                native_candidate,
                focus_before,
            )
        )
    except Exception:
        candidate_matches_before = None

    if (
        type(candidate_matches_before)
        is not bool
    ):
        return unknown(
            "focus_identity_unavailable",
            candidate_count=1,
        )

    try:
        focus_after = (
            provider.focused_element(
                root
            )
        )
    except Exception:
        return unknown(
            "focused_element_read_failed",
            candidate_count=1,
        )

    if focus_after is None:
        return unknown(
            "focus_changed_during_collection",
            candidate_count=1,
        )

    try:
        focus_after_pid = (
            provider.element_pid(
                focus_after
            )
        )
    except Exception:
        focus_after_pid = None

    if (
        focus_after_pid
        != expected_application.pid
    ):
        return unknown(
            "focused_element_foreign",
            candidate_count=1,
        )

    try:
        same_focus = (
            provider.same_element(
                focus_before,
                focus_after,
            )
        )
    except Exception:
        same_focus = None

    if (
        type(same_focus)
        is not bool
    ):
        return unknown(
            "focus_identity_unavailable",
            candidate_count=1,
        )

    if same_focus is not True:
        return unknown(
            "focus_changed_during_collection",
            candidate_count=1,
        )

    try:
        candidate_matches_after = (
            provider.same_element(
                native_candidate,
                focus_after,
            )
        )
    except Exception:
        candidate_matches_after = None

    if (
        type(candidate_matches_after)
        is not bool
        or candidate_matches_after
        is not candidate_matches_before
    ):
        return unknown(
            "focus_identity_unavailable",
            candidate_count=1,
        )

    try:
        after = (
            provider.frontmost_application()
        )
    except Exception:
        after = None

    if not _same_application(
        after,
        expected_application,
    ):
        return unknown(
            (
                "active_application_unavailable"
                if after is None
                else "active_application_changed"
            ),
            candidate_count=1,
        )

    if candidate_matches_after:
        return result(
            CORRELATION_STATUS_MATCHED,
            candidate_count=1,
            candidate=candidate,
            diagnostics=(),
        )

    return result(
        CORRELATION_STATUS_MISMATCHED,
        candidate_count=1,
        candidate=candidate,
        diagnostics=(
            MISMATCH_CODE,
        ),
    )

APPLICATION_WIRE_FIELDS = frozenset({
    "pid",
    "bundle_id",
    "name",
})

SELECTOR_WIRE_FIELDS = frozenset({
    "role",
    "subrole",
    "text",
    "require_enabled",
    "require_positive_area",
})

CANDIDATE_WIRE_FIELDS = frozenset({
    "path",
    "owner_pid",
    "role",
    "subrole",
    "title",
    "description",
    "enabled",
    "position_x",
    "position_y",
    "width",
    "height",
})

CORRELATION_WIRE_FIELDS = frozenset({
    "captured_at_monotonic",
    "status",
    "expected_application",
    "selector",
    "candidate_count",
    "candidate",
    "diagnostics",
})


def _exact_mapping(
    value,
    expected_fields,
    label,
):
    if type(value) is not dict:
        raise ValueError(
            f"{label} must be an exact mapping."
        )

    if set(
        value
    ) != set(
        expected_fields
    ):
        raise ValueError(
            f"{label} fields are invalid."
        )

    return value


def _application_to_wire(
    application,
):
    if (
        type(application)
        is not ApplicationIdentity
    ):
        raise ValueError(
            "Invalid application wire source."
        )

    return {
        "pid": application.pid,
        "bundle_id": application.bundle_id,
        "name": application.name,
    }


def _application_from_wire(
    payload,
):
    payload = _exact_mapping(
        payload,
        APPLICATION_WIRE_FIELDS,
        "Application wire payload",
    )

    pid = payload[
        "pid"
    ]

    bundle_id = payload[
        "bundle_id"
    ]

    name = payload[
        "name"
    ]

    if (
        type(pid) is not int
        or pid <= 0
    ):
        raise ValueError(
            "Invalid application wire PID."
        )

    if (
        type(bundle_id) is not str
        or not bundle_id
    ):
        raise ValueError(
            "Invalid application wire bundle ID."
        )

    if (
        name is not None
        and type(name) is not str
    ):
        raise ValueError(
            "Invalid application wire name."
        )

    return ApplicationIdentity(
        pid,
        bundle_id,
        name,
    )


def _selector_to_wire(
    selector,
):
    if (
        type(selector)
        is not StructuredUITargetSelector
    ):
        raise ValueError(
            "Invalid selector wire source."
        )

    return {
        "role": selector.role,
        "subrole": selector.subrole,
        "text": selector.text,
        "require_enabled": (
            selector.require_enabled
        ),
        "require_positive_area": (
            selector.require_positive_area
        ),
    }


def _selector_from_wire(
    payload,
):
    payload = _exact_mapping(
        payload,
        SELECTOR_WIRE_FIELDS,
        "Selector wire payload",
    )

    for name in (
        "role",
        "subrole",
        "text",
    ):
        value = payload[
            name
        ]

        if (
            value is not None
            and type(value) is not str
        ):
            raise ValueError(
                "Invalid selector wire text."
            )

    for name in (
        "require_enabled",
        "require_positive_area",
    ):
        if (
            type(
                payload[
                    name
                ]
            )
            is not bool
        ):
            raise ValueError(
                "Invalid selector wire boolean."
            )

    return StructuredUITargetSelector(
        role=payload[
            "role"
        ],
        subrole=payload[
            "subrole"
        ],
        text=payload[
            "text"
        ],
        require_enabled=payload[
            "require_enabled"
        ],
        require_positive_area=payload[
            "require_positive_area"
        ],
    )


def _candidate_to_wire(
    candidate,
):
    if (
        type(candidate)
        is not FocusTargetSemanticCandidate
    ):
        raise ValueError(
            "Invalid candidate wire source."
        )

    return {
        "path": list(
            candidate.path
        ),
        "owner_pid": (
            candidate.owner_pid
        ),
        "role": candidate.role,
        "subrole": candidate.subrole,
        "title": candidate.title,
        "description": (
            candidate.description
        ),
        "enabled": candidate.enabled,
        "position_x": (
            candidate.position_x
        ),
        "position_y": (
            candidate.position_y
        ),
        "width": candidate.width,
        "height": candidate.height,
    }


def _candidate_from_wire(
    payload,
):
    payload = _exact_mapping(
        payload,
        CANDIDATE_WIRE_FIELDS,
        "Candidate wire payload",
    )

    path = payload[
        "path"
    ]

    if (
        type(path) is not list
        or any(
            type(index) is not int
            for index in path
        )
    ):
        raise ValueError(
            "Invalid candidate wire path."
        )

    return FocusTargetSemanticCandidate(
        path=tuple(
            path
        ),
        owner_pid=payload[
            "owner_pid"
        ],
        role=payload[
            "role"
        ],
        subrole=payload[
            "subrole"
        ],
        title=payload[
            "title"
        ],
        description=payload[
            "description"
        ],
        enabled=payload[
            "enabled"
        ],
        position_x=payload[
            "position_x"
        ],
        position_y=payload[
            "position_y"
        ],
        width=payload[
            "width"
        ],
        height=payload[
            "height"
        ],
    )


def focus_target_correlation_to_dict(
    result,
):
    """Serialize correlation evidence only.

    Native AX references and native identity objects are intentionally absent.
    """

    if (
        type(result)
        is not FocusTargetCorrelationResult
    ):
        raise ValueError(
            "Exact correlation result is required."
        )

    return {
        "captured_at_monotonic": (
            result.captured_at_monotonic
        ),
        "status": result.status,
        "expected_application": (
            _application_to_wire(
                result.expected_application
            )
        ),
        "selector": (
            _selector_to_wire(
                result.selector
            )
        ),
        "candidate_count": (
            result.candidate_count
        ),
        "candidate": (
            None
            if result.candidate is None
            else _candidate_to_wire(
                result.candidate
            )
        ),
        "diagnostics": list(
            result.diagnostics
        ),
    }


def focus_target_correlation_from_dict(
    payload,
):
    """Strictly reconstruct one correlation result from JSON-safe evidence."""

    payload = _exact_mapping(
        payload,
        CORRELATION_WIRE_FIELDS,
        "Correlation wire payload",
    )

    diagnostics = payload[
        "diagnostics"
    ]

    if (
        type(diagnostics) is not list
        or any(
            type(code) is not str
            for code in diagnostics
        )
        or len(
            diagnostics
        )
        != len(
            set(
                diagnostics
            )
        )
    ):
        raise ValueError(
            "Invalid correlation wire diagnostics."
        )

    candidate_payload = payload[
        "candidate"
    ]

    candidate = (
        None
        if candidate_payload is None
        else _candidate_from_wire(
            candidate_payload
        )
    )

    return FocusTargetCorrelationResult(
        captured_at_monotonic=payload[
            "captured_at_monotonic"
        ],
        status=payload[
            "status"
        ],
        expected_application=(
            _application_from_wire(
                payload[
                    "expected_application"
                ]
            )
        ),
        selector=(
            _selector_from_wire(
                payload[
                    "selector"
                ]
            )
        ),
        candidate_count=payload[
            "candidate_count"
        ],
        candidate=candidate,
        diagnostics=tuple(
            diagnostics
        ),
    )

def validate_focus_target_limits(
    max_nodes,
    max_depth,
    max_children,
):
    """Public strict validation for the isolated 8D2 runtime."""

    _validate_limits(
        max_nodes,
        max_depth,
        max_children,
    )


def focus_target_selector_to_dict(
    selector,
):
    """Serialize only one exact semantic selector."""

    return _selector_to_wire(
        selector
    )


def focus_target_selector_from_dict(
    payload,
):
    """Strictly reconstruct one semantic selector."""

    return _selector_from_wire(
        payload
    )


def unknown_focus_target_correlation(
    code,
    *,
    expected_application,
    selector,
    captured_at_monotonic,
):
    """Construct one structured fail-closed correlation result."""

    if (
        type(code) is not str
        or code not in UNKNOWN_CODES
    ):
        raise ValueError(
            "Invalid unknown correlation diagnostic."
        )

    if (
        type(expected_application)
        is not ApplicationIdentity
        or type(selector)
        is not StructuredUITargetSelector
    ):
        raise ValueError(
            "Exact unknown correlation sources are required."
        )

    return FocusTargetCorrelationResult(
        captured_at_monotonic=(
            captured_at_monotonic
        ),
        status=(
            CORRELATION_STATUS_UNKNOWN
        ),
        expected_application=(
            expected_application
        ),
        selector=selector,
        candidate_count=0,
        candidate=None,
        diagnostics=(
            code,
        ),
    )
