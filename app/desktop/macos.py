"""Native metadata reads only. Import native frameworks lazily in the worker."""

import math

from app.desktop.contracts import ApplicationIdentity, COORDINATE_SPACE, MAX_TEXT


MAX_SCANNED_WINDOWS = 4096


class MacOSDesktopProvider:
    def __init__(self):
        import AppKit
        import Quartz
        self.appkit = AppKit
        self.quartz = Quartz

    @staticmethod
    def _integer(value):
        # PyObjC bridges NSNumber integers as int subclasses (OC_PythonLong).
        # Normalize here; portable contracts continue to require exact types.
        # Do not coerce booleans, numeric strings, or floating-point identities.
        if isinstance(value, bool) or not isinstance(value, int):
            return None
        value = int(value)
        return value if value > 0 else None

    @staticmethod
    def _number(value):
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            value = int(value)
        elif isinstance(value, float):
            value = float(value)
        else:
            return None
        try:
            return value if math.isfinite(value) else None
        except OverflowError:
            return None

    @staticmethod
    def _text(value):
        if not isinstance(value, str):
            return None
        value = str(value)
        return value if len(value) <= MAX_TEXT else None

    def frontmost_application(self):
        app = self.appkit.NSWorkspace.sharedWorkspace().frontmostApplication()
        if app is None or app.isTerminated():
            return None
        return ApplicationIdentity(
            pid=self._integer(app.processIdentifier()),
            bundle_id=self._text(app.bundleIdentifier()),
            name=self._text(app.localizedName()),
        )

    def screen_capture_access(self):
        # Preflight only: never call CGRequestScreenCaptureAccess.
        return bool(self.quartz.CGPreflightScreenCaptureAccess())

    def windows_for_pid(self, pid, limit):
        q = self.quartz
        native_rows = q.CGWindowListCopyWindowInfo(
            q.kCGWindowListOptionOnScreenOnly | q.kCGWindowListExcludeDesktopElements,
            q.kCGNullWindowID,
        )
        if native_rows is None:
            return None  # NULL is failure; [] is a successful empty enumeration.
        result = []
        truncated = len(native_rows) > MAX_SCANNED_WINDOWS
        for row in native_rows[:MAX_SCANNED_WINDOWS]:
            owner = self._integer(row.get(q.kCGWindowOwnerPID))
            if owner is None:
                # Unknown ownership must not masquerade as zero app windows.
                raise ValueError("Invalid native window owner PID.")
            if owner != pid:
                continue
            if len(result) >= limit:
                truncated = True
                break
            bounds = row.get(q.kCGWindowBounds)
            native_id = self._integer(row.get(q.kCGWindowNumber))
            result.append({
                "owner_pid": owner,
                "native_window_id": native_id,
                "title": self._text(row.get(q.kCGWindowName)),
                "bounds": {
                    "x": self._number(bounds.get("X")),
                    "y": self._number(bounds.get("Y")),
                    "width": self._number(bounds.get("Width")),
                    "height": self._number(bounds.get("Height")),
                    "coordinate_space": COORDINATE_SPACE,
                } if bounds is not None else None,
            })
        return result, truncated
