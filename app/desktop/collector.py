"""Snapshot assembly over an injected, read-only native boundary.

Use runtime.collect_desktop_context for production: the enclosing process
provides the hard deadline, including time spent inside native calls.
"""

import time
from typing import Protocol

from app.desktop.contracts import (
    ApplicationIdentity, DesktopContextObservation,
    MAX_TEXT, MAX_WINDOWS, WindowBounds, WindowObservation, positive_int,
    unavailable,
)


class DesktopProvider(Protocol):
    def frontmost_application(self) -> ApplicationIdentity | None: ...
    def screen_capture_access(self) -> bool | None: ...
    def windows_for_pid(self, pid: int, limit: int) -> tuple[list[dict], bool] | None: ...


def validate_window_limit(max_windows):
    if type(max_windows) is not int or not 1 <= max_windows <= MAX_WINDOWS:
        raise ValueError(f"max_windows must be an integer from 1 to {MAX_WINDOWS}.")


def assemble_snapshot(provider: DesktopProvider, *, max_windows=32, clock=time.monotonic):
    validate_window_limit(max_windows)
    captured_at = clock()
    diagnostics = []

    def note(code):
        if code not in diagnostics:
            diagnostics.append(code)

    try:
        before = provider.frontmost_application()
    except Exception:
        return unavailable("active_application_unavailable", captured_at)
    if type(before) is not ApplicationIdentity:
        return unavailable("active_application_unavailable", captured_at)

    windows = []
    enumeration_succeeded = False
    try:
        access = provider.screen_capture_access()
    except Exception:
        access = None
    if access is not True:
        note("screen_capture_access_unavailable" if access is False
             else "screen_capture_access_unknown")
        note("window_enumeration_unavailable")
    else:
        try:
            result = provider.windows_for_pid(before.pid, max_windows)
            if result is None:
                raise ValueError("Enumeration unavailable.")
            rows, truncated = result
            if type(rows) is not list or type(truncated) is not bool:
                raise ValueError("Invalid enumeration contract.")
            enumeration_succeeded = True
            if truncated or len(rows) > max_windows:
                note("windows_truncated")
            seen = set()
            duplicate_ids = set()
            for row in rows[:max_windows]:
                try:
                    if type(row) is not dict or not positive_int(row.get("owner_pid")):
                        raise ValueError("Invalid window ownership.")
                    if row["owner_pid"] != before.pid:
                        raise ValueError("Window belongs to a different process.")
                    native_id = row.get("native_window_id")
                    if native_id is not None and not positive_int(native_id):
                        raise ValueError("Invalid window identity.")
                    if native_id is not None and native_id in seen:
                        duplicate_ids.add(native_id)
                        note("duplicate_window_identity")
                        continue
                    seen.add(native_id)
                    title = row.get("title")
                    if title is not None and (type(title) is not str or len(title) > MAX_TEXT):
                        title = None
                        note("window_metadata_missing")
                    raw_bounds = row.get("bounds")
                    bounds = None
                    if raw_bounds is not None:
                        try:
                            bounds = WindowBounds(**raw_bounds)
                        except (TypeError, ValueError, OverflowError):
                            note("malformed_window_record")
                    if native_id is None or title is None or bounds is None:
                        note("window_metadata_missing")
                    # Quartz front-to-back order does not prove keyboard focus.
                    windows.append(WindowObservation(
                        owner_pid=before.pid, native_window_id=native_id,
                        title=title, bounds=bounds, focused=None,
                    ))
                except Exception:
                    note("malformed_window_record")
            # Neither side of a duplicate identity is trusted.
            windows = [w for w in windows if w.native_window_id not in duplicate_ids]
        except Exception:
            enumeration_succeeded = False
            windows = []
            note("window_enumeration_unavailable")

    if windows:
        # A second bounded sample detects vanished or changed native windows.
        # Unidentified records remain partial evidence, never synthetic IDs.
        try:
            latest_rows, latest_truncated = provider.windows_for_pid(before.pid, max_windows)
            if type(latest_rows) is not list or type(latest_truncated) is not bool:
                raise ValueError("Invalid revalidation result.")
            if latest_truncated or len(latest_rows) > max_windows:
                note("windows_truncated")
            stable_windows = []
            for window in windows:
                if window.native_window_id is None:
                    stable_windows.append(window)
                    continue
                matches = [r for r in latest_rows[:max_windows]
                           if type(r) is dict and type(r.get("owner_pid")) is int
                           and r["owner_pid"] == before.pid
                           and type(r.get("native_window_id")) is int
                           and r["native_window_id"] == window.native_window_id]
                if len(matches) != 1:
                    note("window_changed_during_collection")
                    continue
                current = matches[0]
                try:
                    current_bounds = WindowBounds(**current["bounds"])
                except (KeyError, TypeError, ValueError, OverflowError):
                    current_bounds = None
                current_title = current.get("title")
                if type(current_title) is not str or len(current_title) > MAX_TEXT:
                    current_title = None
                if current_bounds != window.bounds or current_title != window.title:
                    note("window_changed_during_collection")
                    continue
                stable_windows.append(window)
            windows = stable_windows
        except Exception:
            windows = []
            note("window_revalidation_unavailable")

    try:
        after = provider.frontmost_application()
    except Exception:
        after = None
    if (type(after) is not ApplicationIdentity or before.pid != after.pid
            or before.bundle_id != after.bundle_id):
        return unavailable("active_application_changed", captured_at)
    if windows:
        note("focus_unavailable")
    return DesktopContextObservation(
        captured_at_monotonic=captured_at,
        status="partial" if diagnostics else "available",
        active_application=before, windows=tuple(windows),
        enumeration_succeeded=enumeration_succeeded,
        diagnostics=tuple(diagnostics),
    )
