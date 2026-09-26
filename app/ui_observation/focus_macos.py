"""Read-only native macOS focused-element access for KUMA 8D1.

Native AX object identity exists only inside this provider/process boundary.
No AX object is serialized or promoted into durable KUMA evidence.
"""

from __future__ import annotations

from app.ui_observation.macos import (
    MacOSAccessibilityProvider,
)


class MacOSFocusProvider(
    MacOSAccessibilityProvider
):
    """Extend the existing read-only AX provider with focus identity reads."""

    def __init__(self):
        super().__init__()

        import CoreFoundation

        required_ax = (
            "kAXFocusedUIElementAttribute",
            "kAXErrorFailure",
        )

        required_cf = (
            "CFEqual",
        )

        if any(
            not hasattr(
                self.ax,
                name,
            )
            for name in required_ax
        ):
            raise ImportError(
                "Required focused-element Accessibility "
                "API is unavailable."
            )

        if any(
            not hasattr(
                CoreFoundation,
                name,
            )
            for name in required_cf
        ):
            raise ImportError(
                "Required CoreFoundation identity "
                "API is unavailable."
            )

        self.cf = CoreFoundation

    def focused_element(
        self,
        application_element,
    ):
        """Read the application's currently focused AX element."""

        return self._copy_optional_attribute(
            application_element,
            self.ax.kAXFocusedUIElementAttribute,
        )

    def _copy_focus_optional_metadata_attribute(
        self,
        element,
        attribute,
    ):
        """Read non-authoritative descriptive focus metadata.

        Focus identity, owner PID, and role remain strict elsewhere.

        Some valid focused controls return kAXErrorFailure for optional
        descriptive attributes even while exact native focus identity remains
        available. That error may erase only optional descriptive metadata.

        Structural/native reliability failures remain errors.
        """

        error, value = (
            self.ax.AXUIElementCopyAttributeValue(
                element,
                attribute,
                None,
            )
        )

        if (
            error
            == self.ax.kAXErrorSuccess
        ):
            return value

        if error in (
            self.ax.kAXErrorAttributeUnsupported,
            self.ax.kAXErrorNoValue,
            self.ax.kAXErrorFailure,
        ):
            return None

        raise RuntimeError(
            "Native Accessibility focus metadata read failed."
        )

    def read_node(
        self,
        element,
    ):
        """Read the minimal semantic metadata needed by 8D1.

        Owner PID and role remain strict trust inputs.

        Subrole, title, description, and enabled are descriptive only and may
        be absent without destroying an otherwise exact focused-element
        observation.
        """

        ax = self.ax

        return {
            "owner_pid": self.element_pid(
                element
            ),
            "role": self._text(
                self._copy_optional_attribute(
                    element,
                    ax.kAXRoleAttribute,
                )
            ),
            "subrole": self._text(
                self._copy_focus_optional_metadata_attribute(
                    element,
                    ax.kAXSubroleAttribute,
                )
            ),
            "title": self._text(
                self._copy_focus_optional_metadata_attribute(
                    element,
                    ax.kAXTitleAttribute,
                )
            ),
            "description": self._text(
                self._copy_focus_optional_metadata_attribute(
                    element,
                    ax.kAXDescriptionAttribute,
                )
            ),
            "enabled": self._boolean(
                self._copy_focus_optional_metadata_attribute(
                    element,
                    ax.kAXEnabledAttribute,
                )
            ),
        }

    def same_element(
        self,
        left,
        right,
    ) -> bool | None:
        """Compare two live AX references using native CF identity semantics.

        ``None`` means identity could not be established safely.
        """

        if (
            left is None
            or right is None
        ):
            return None

        try:
            result = self.cf.CFEqual(
                left,
                right,
            )
        except Exception:
            return None

        if type(result) is not bool:
            return None

        return result
