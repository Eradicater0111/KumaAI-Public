"""Native macOS Accessibility reads only; no AX actions or setters."""

import math

from app.desktop.contracts import ApplicationIdentity
from app.ui_observation.contracts import MAX_UI_TEXT


class MacOSAccessibilityProvider:
    def __init__(self):
        import AppKit
        import ApplicationServices

        required = (
            "AXUIElementCreateApplication",
            "AXUIElementCopyAttributeValue",
            "AXUIElementCopyAttributeValues",
            "AXUIElementGetAttributeValueCount",
            "AXUIElementGetPid",
            "AXIsProcessTrusted",
            "kAXErrorSuccess",
            "kAXErrorAttributeUnsupported",
            "kAXErrorNoValue",
            "kAXRoleAttribute",
            "kAXSubroleAttribute",
            "kAXTitleAttribute",
            "kAXDescriptionAttribute",
            "kAXChildrenAttribute",
            "kAXEnabledAttribute",
            "kAXFocusedAttribute",
            "kAXSelectedAttribute",
            "kAXPositionAttribute",
            "kAXSizeAttribute",
            "AXValueGetType",
            "AXValueGetValue",
            "kAXValueCGPointType",
            "kAXValueCGSizeType",
        )
        if any(not hasattr(ApplicationServices, name) for name in required):
            raise ImportError("Required macOS Accessibility API is unavailable.")

        self.appkit = AppKit
        self.ax = ApplicationServices

    @staticmethod
    def _integer(value):
        if isinstance(value, bool) or not isinstance(value, int):
            return None
        value = int(value)
        return value if value > 0 else None

    @staticmethod
    def _count(value):
        if isinstance(value, bool) or not isinstance(value, int):
            return None
        value = int(value)
        return value if value >= 0 else None

    @staticmethod
    def _text(value):
        if not isinstance(value, str):
            return None
        value = str(value)
        return value if len(value) <= MAX_UI_TEXT else None

    @staticmethod
    def _boolean(value):
        return value if type(value) is bool else None

    @staticmethod
    def _geometry_number(value):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        value = float(value)
        return value if math.isfinite(value) else None

    def _decode_ax_value(self, value, expected_type):
        if value is None:
            return None
        try:
            actual_type = self.ax.AXValueGetType(value)
            if actual_type != expected_type:
                raise ValueError("Unexpected AXValue type.")
            result = self.ax.AXValueGetValue(value, expected_type, None)
        except Exception:
            raise RuntimeError("Native Accessibility geometry decode failed.") from None

        if (
            type(result) is not tuple
            or len(result) != 2
            or result[0] is not True
            or result[1] is None
        ):
            raise RuntimeError("Native Accessibility geometry decode failed.")
        return result[1]

    def frontmost_application(self):
        app = self.appkit.NSWorkspace.sharedWorkspace().frontmostApplication()
        if app is None or app.isTerminated():
            return None
        pid = self._integer(app.processIdentifier())
        bundle = self._text(app.bundleIdentifier())
        name = self._text(app.localizedName())
        if pid is None:
            return None
        return ApplicationIdentity(pid=pid, bundle_id=bundle, name=name)

    def accessibility_trusted(self):
        # Preflight only. Never call AXIsProcessTrustedWithOptions, which can prompt.
        return bool(self.ax.AXIsProcessTrusted())

    def application_element(self, pid):
        return self.ax.AXUIElementCreateApplication(pid)

    def element_pid(self, element):
        error, pid = self.ax.AXUIElementGetPid(element, None)
        if error != self.ax.kAXErrorSuccess:
            return None
        return self._integer(pid)

    def _copy_optional_attribute(self, element, attribute):
        error, value = self.ax.AXUIElementCopyAttributeValue(element, attribute, None)
        if error == self.ax.kAXErrorSuccess:
            return value
        if error in (self.ax.kAXErrorAttributeUnsupported, self.ax.kAXErrorNoValue):
            return None
        raise RuntimeError("Native Accessibility attribute read failed.")

    def read_node(self, element):
        ax = self.ax
        return {
            "owner_pid": self.element_pid(element),
            "role": self._text(self._copy_optional_attribute(element, ax.kAXRoleAttribute)),
            "subrole": self._text(self._copy_optional_attribute(element, ax.kAXSubroleAttribute)),
            "title": self._text(self._copy_optional_attribute(element, ax.kAXTitleAttribute)),
            "description": self._text(
                self._copy_optional_attribute(element, ax.kAXDescriptionAttribute)
            ),
            "enabled": self._boolean(
                self._copy_optional_attribute(element, ax.kAXEnabledAttribute)
            ),
            "focused": self._boolean(
                self._copy_optional_attribute(element, ax.kAXFocusedAttribute)
            ),
            "selected": self._boolean(
                self._copy_optional_attribute(element, ax.kAXSelectedAttribute)
            ),
        }

    def read_geometry(self, element):
        ax = self.ax
        raw_position = self._copy_optional_attribute(element, ax.kAXPositionAttribute)
        raw_size = self._copy_optional_attribute(element, ax.kAXSizeAttribute)

        point = self._decode_ax_value(raw_position, ax.kAXValueCGPointType)
        size = self._decode_ax_value(raw_size, ax.kAXValueCGSizeType)

        position_x = position_y = width = height = None
        if point is not None:
            position_x = self._geometry_number(getattr(point, "x", None))
            position_y = self._geometry_number(getattr(point, "y", None))
            if position_x is None or position_y is None:
                raise RuntimeError("Native Accessibility position is invalid.")

        if size is not None:
            width = self._geometry_number(getattr(size, "width", None))
            height = self._geometry_number(getattr(size, "height", None))
            if width is None or height is None or width < 0 or height < 0:
                raise RuntimeError("Native Accessibility size is invalid.")

        return {
            "position_x": position_x,
            "position_y": position_y,
            "width": width,
            "height": height,
        }

    def children_for_element(self, element, limit):
        ax = self.ax
        error, raw_count = ax.AXUIElementGetAttributeValueCount(
            element, ax.kAXChildrenAttribute, None
        )
        if error in (ax.kAXErrorAttributeUnsupported, ax.kAXErrorNoValue):
            return [], False
        if error != ax.kAXErrorSuccess:
            raise RuntimeError("Native Accessibility child count failed.")
        count = self._count(raw_count)
        if count is None:
            raise ValueError("Invalid native Accessibility child count.")
        if count == 0:
            return [], False
        take = min(count, limit)
        error, values = ax.AXUIElementCopyAttributeValues(
            element, ax.kAXChildrenAttribute, 0, take, None
        )
        if error != ax.kAXErrorSuccess or values is None:
            raise RuntimeError("Native Accessibility child read failed.")
        children = list(values)
        if len(children) > take:
            raise ValueError("Native Accessibility child result exceeded request.")
        return children, count > take

    @staticmethod
    def element_identity(element):
        # Snapshot-local cycle suppression only. Bounds guarantee termination even
        # if a native bridge returns distinct wrappers for the same AX object.
        try:
            return ("hash", hash(element))
        except Exception:
            return ("object", id(element))
