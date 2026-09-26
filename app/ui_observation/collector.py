"""Bounded structured UI traversal over an injected read-only AX provider."""

import math
import time
from typing import Protocol

from app.desktop.contracts import ApplicationIdentity, positive_int
from app.ui_observation.contracts import (
    MAX_UI_CHILDREN,
    MAX_UI_DEPTH,
    MAX_UI_NODES,
    MAX_UI_TEXT,
    StructuredUIObservation,
    UIElementObservation,
    unavailable,
)


class AccessibilityProvider(Protocol):
    def accessibility_trusted(self) -> bool: ...
    def frontmost_application(self) -> ApplicationIdentity | None: ...
    def application_element(self, pid: int): ...
    def element_pid(self, element) -> int | None: ...
    def read_node(self, element) -> dict: ...
    def read_geometry(self, element) -> dict: ...
    def children_for_element(self, element, limit: int) -> tuple[list, bool]: ...
    def element_identity(self, element): ...


def validate_limits(max_nodes, max_depth, max_children):
    if type(max_nodes) is not int or not 1 <= max_nodes <= MAX_UI_NODES:
        raise ValueError(f"max_nodes must be an integer from 1 to {MAX_UI_NODES}.")
    if type(max_depth) is not int or not 0 <= max_depth <= MAX_UI_DEPTH:
        raise ValueError(f"max_depth must be an integer from 0 to {MAX_UI_DEPTH}.")
    if type(max_children) is not int or not 1 <= max_children <= MAX_UI_CHILDREN:
        raise ValueError(
            f"max_children must be an integer from 1 to {MAX_UI_CHILDREN}."
        )


def _same_application(left, right):
    return (
        type(left) is ApplicationIdentity
        and type(right) is ApplicationIdentity
        and left.pid == right.pid
        and left.bundle_id is not None
        and left.bundle_id == right.bundle_id
    )


def _optional_text(value):
    return value if value is None or (type(value) is str and len(value) <= MAX_UI_TEXT) else None


def _optional_bool(value):
    return value if value is None or type(value) is bool else None


def _geometry_number(value, *, nonnegative=False):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError("Invalid geometry number.")
    if nonnegative and value < 0:
        raise ValueError("Invalid geometry size.")
    return value


def _normalized_geometry(raw):
    if type(raw) is not dict:
        raise ValueError("Invalid geometry contract.")

    position_x = raw.get("position_x")
    position_y = raw.get("position_y")
    width = raw.get("width")
    height = raw.get("height")

    if (position_x is None) != (position_y is None):
        raise ValueError("Incomplete geometry position.")
    if (width is None) != (height is None):
        raise ValueError("Incomplete geometry size.")

    if position_x is not None:
        position_x = _geometry_number(position_x)
        position_y = _geometry_number(position_y)
    if width is not None:
        width = _geometry_number(width, nonnegative=True)
        height = _geometry_number(height, nonnegative=True)

    return {
        "position_x": position_x,
        "position_y": position_y,
        "width": width,
        "height": height,
    }


def assemble_structured_ui_snapshot(
    provider: AccessibilityProvider,
    *,
    expected_application: ApplicationIdentity,
    max_nodes=128,
    max_depth=6,
    max_children=32,
    clock=time.monotonic,
):
    validate_limits(max_nodes, max_depth, max_children)
    captured_at = clock()

    if (
        type(expected_application) is not ApplicationIdentity
        or expected_application.bundle_id is None
        or not expected_application.bundle_id
    ):
        return unavailable("expected_application_incomplete", captured_at)

    try:
        trusted = provider.accessibility_trusted()
    except Exception:
        return unavailable("collection_failed", captured_at)
    if trusted is not True:
        return unavailable("accessibility_permission_denied", captured_at)

    try:
        before = provider.frontmost_application()
    except Exception:
        return unavailable("active_application_unavailable", captured_at)
    if not _same_application(before, expected_application):
        return unavailable(
            "active_application_unavailable" if before is None else "active_application_changed",
            captured_at,
        )

    try:
        root = provider.application_element(expected_application.pid)
        root_pid = provider.element_pid(root) if root is not None else None
    except Exception:
        root = None
        root_pid = None
    if root is None:
        return unavailable("application_element_unavailable", captured_at)
    if root_pid != expected_application.pid:
        return unavailable("application_element_mismatch", captured_at)

    diagnostics = []

    def note(code):
        if code not in diagnostics:
            diagnostics.append(code)

    elements = []
    stack = [(root, (), 0)]
    seen = set()

    while stack and len(elements) < max_nodes:
        element, path, depth = stack.pop()
        try:
            identity = provider.element_identity(element)
        except Exception:
            identity = ("object", id(element))
        if identity in seen:
            note("cycle_or_duplicate_element")
            continue
        seen.add(identity)

        try:
            raw = provider.read_node(element)
            if type(raw) is not dict:
                raise ValueError("Invalid node contract.")
            owner_pid = raw.get("owner_pid")
            if not positive_int(owner_pid):
                raise ValueError("Invalid UI element ownership.")
            if owner_pid != expected_application.pid:
                note("foreign_element")
                continue

            role = _optional_text(raw.get("role"))
            subrole = _optional_text(raw.get("subrole"))
            title = _optional_text(raw.get("title"))
            description = _optional_text(raw.get("description"))
            enabled = _optional_bool(raw.get("enabled"))
            focused = _optional_bool(raw.get("focused"))
            selected = _optional_bool(raw.get("selected"))
            if role is None:
                note("role_unavailable")

            geometry = {
                "position_x": None,
                "position_y": None,
                "width": None,
                "height": None,
            }
            geometry_reader = getattr(provider, "read_geometry", None)
            if geometry_reader is not None:
                try:
                    if not callable(geometry_reader):
                        raise TypeError("Invalid geometry reader.")
                    geometry = _normalized_geometry(geometry_reader(element))
                except Exception:
                    note("geometry_unavailable")

            elements.append(
                UIElementObservation(
                    path=path,
                    owner_pid=owner_pid,
                    role=role,
                    subrole=subrole,
                    title=title,
                    description=description,
                    enabled=enabled,
                    focused=focused,
                    selected=selected,
                    **geometry,
                )
            )
        except Exception:
            if path == ():
                return unavailable("traversal_failed", captured_at)
            note("node_read_failed")
            continue

        if depth >= max_depth:
            try:
                probe, more = provider.children_for_element(element, 1)
                if probe or more:
                    note("depth_truncated")
            except Exception:
                note("children_unavailable")
            continue

        try:
            children, truncated = provider.children_for_element(element, max_children)
            if type(children) is not list or type(truncated) is not bool:
                raise ValueError("Invalid child traversal contract.")
            if len(children) > max_children:
                raise ValueError("Child traversal exceeded bound.")
            if truncated:
                note("children_truncated")
        except Exception:
            note("children_unavailable")
            continue

        for child_index in range(len(children) - 1, -1, -1):
            stack.append((children[child_index], path + (child_index,), depth + 1))

    if stack:
        note("nodes_truncated")

    try:
        after = provider.frontmost_application()
    except Exception:
        after = None
    if not _same_application(after, expected_application):
        return unavailable("active_application_changed", captured_at)

    if not elements or elements[0].path != ():
        return unavailable("traversal_failed", captured_at)

    return StructuredUIObservation(
        captured_at_monotonic=captured_at,
        status="partial" if diagnostics else "available",
        active_application=before,
        elements=tuple(elements),
        traversal_succeeded=True,
        diagnostics=tuple(diagnostics),
    )
