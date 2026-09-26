from types import SimpleNamespace
from unittest.mock import Mock

from app.ui_observation.macos import MacOSAccessibilityProvider


class BridgedInt(int):
    pass


def native_provider():
    p = object.__new__(MacOSAccessibilityProvider)
    p.ax = SimpleNamespace(
        kAXErrorSuccess=0,
        kAXErrorAttributeUnsupported=-1,
        kAXErrorNoValue=-2,
        kAXRoleAttribute="AXRole",
        kAXSubroleAttribute="AXSubrole",
        kAXTitleAttribute="AXTitle",
        kAXDescriptionAttribute="AXDescription",
        kAXEnabledAttribute="AXEnabled",
        kAXFocusedAttribute="AXFocused",
        kAXSelectedAttribute="AXSelected",
        kAXChildrenAttribute="AXChildren",
        AXIsProcessTrusted=Mock(return_value=True),
        AXUIElementCreateApplication=Mock(return_value="root"),
        AXUIElementGetPid=Mock(return_value=(0, BridgedInt(123))),
        AXUIElementGetAttributeValueCount=Mock(return_value=(0, BridgedInt(100))),
        AXUIElementCopyAttributeValues=Mock(return_value=(0, ["a", "b"])),
        AXUIElementCopyAttributeValue=Mock(),
    )
    return p


def test_native_pid_normalizes_pyobjc_integer_subclass_without_coercing_bool():
    p = native_provider()
    assert p.element_pid("root") == 123
    p.ax.AXUIElementGetPid.return_value = (0, True)
    assert p.element_pid("root") is None


def test_children_are_requested_at_native_bound_not_copied_wholesale():
    p = native_provider()
    children, truncated = p.children_for_element("root", 2)
    assert children == ["a", "b"]
    assert truncated
    p.ax.AXUIElementCopyAttributeValues.assert_called_once_with(
        "root", "AXChildren", 0, 2, None
    )


def test_optional_unsupported_attribute_is_unknown_not_exception():
    p = native_provider()
    p.ax.AXUIElementCopyAttributeValue.return_value = (-1, None)
    assert p._copy_optional_attribute("node", "AXTitle") is None


def test_accessibility_trust_is_preflight_only():
    p = native_provider()
    assert p.accessibility_trusted() is True
    p.ax.AXIsProcessTrusted.assert_called_once_with()
