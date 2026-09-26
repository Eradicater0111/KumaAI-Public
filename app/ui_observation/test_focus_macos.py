from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.ui_observation.focus_macos import (
    MacOSFocusProvider,
)


def provider():
    result = object.__new__(
        MacOSFocusProvider
    )

    result.ax = SimpleNamespace(
        kAXFocusedUIElementAttribute=(
            "AXFocusedUIElement"
        ),
        kAXRoleAttribute="AXRole",
        kAXSubroleAttribute="AXSubrole",
        kAXTitleAttribute="AXTitle",
        kAXDescriptionAttribute="AXDescription",
        kAXEnabledAttribute="AXEnabled",
        kAXErrorSuccess=0,
        kAXErrorAttributeUnsupported=-1,
        kAXErrorNoValue=-2,
        kAXErrorFailure=-3,
        kAXErrorCannotComplete=-4,
        AXUIElementCopyAttributeValue=Mock(),
    )

    result.cf = SimpleNamespace(
        CFEqual=Mock(
            return_value=True
        )
    )

    return result


def test_focused_element_uses_exact_native_application_attribute():
    p = provider()

    p.ax.AXUIElementCopyAttributeValue.return_value = (
        0,
        "focused",
    )

    assert (
        p.focused_element(
            "application"
        )
        == "focused"
    )

    p.ax.AXUIElementCopyAttributeValue.assert_called_once_with(
        "application",
        "AXFocusedUIElement",
        None,
    )


def test_missing_native_focus_is_unknown_not_invented():
    p = provider()

    p.ax.AXUIElementCopyAttributeValue.return_value = (
        -2,
        None,
    )

    assert (
        p.focused_element(
            "application"
        )
        is None
    )


def test_native_cfequal_is_exact_focus_identity_comparator():
    p = provider()

    left = object()
    right = object()

    assert (
        p.same_element(
            left,
            right,
        )
        is True
    )

    p.cf.CFEqual.assert_called_once_with(
        left,
        right,
    )


def test_native_identity_failure_becomes_unknown():
    p = provider()

    p.cf.CFEqual.side_effect = RuntimeError(
        "private"
    )

    assert (
        p.same_element(
            object(),
            object(),
        )
        is None
    )


def test_non_boolean_native_identity_result_is_unknown():
    p = provider()

    p.cf.CFEqual.return_value = 1

    assert (
        p.same_element(
            object(),
            object(),
        )
        is None
    )


def test_missing_elements_do_not_enter_native_identity_comparison():
    p = provider()

    assert (
        p.same_element(
            None,
            object(),
        )
        is None
    )

    p.cf.CFEqual.assert_not_called()

def test_focus_optional_native_failure_erases_description_only():
    p = provider()

    p.element_pid = Mock(
        return_value=123
    )

    def read(
        element,
        attribute,
        _unused,
    ):
        assert element == "focused"

        if attribute == "AXRole":
            return (
                0,
                "AXTextArea",
            )

        if attribute == "AXDescription":
            return (
                -3,
                None,
            )

        return (
            -2,
            None,
        )

    p.ax.AXUIElementCopyAttributeValue.side_effect = read

    node = p.read_node(
        "focused"
    )

    assert node == {
        "owner_pid": 123,
        "role": "AXTextArea",
        "subrole": None,
        "title": None,
        "description": None,
        "enabled": None,
    }


def test_focus_role_native_failure_remains_strict():
    p = provider()

    p.element_pid = Mock(
        return_value=123
    )

    p.ax.AXUIElementCopyAttributeValue.return_value = (
        -3,
        None,
    )

    with pytest.raises(
        RuntimeError,
        match="attribute read failed",
    ):
        p.read_node(
            "focused"
        )


def test_focus_optional_cannot_complete_remains_fail_closed():
    p = provider()

    p.ax.AXUIElementCopyAttributeValue.return_value = (
        -4,
        None,
    )

    with pytest.raises(
        RuntimeError,
        match="focus metadata read failed",
    ):
        p._copy_focus_optional_metadata_attribute(
            "focused",
            "AXDescription",
        )


def test_focus_optional_invalid_element_remains_fail_closed():
    p = provider()

    p.ax.AXUIElementCopyAttributeValue.return_value = (
        -25202,
        None,
    )

    with pytest.raises(
        RuntimeError,
        match="focus metadata read failed",
    ):
        p._copy_focus_optional_metadata_attribute(
            "focused",
            "AXDescription",
        )


def test_focus_read_node_does_not_query_unused_focus_selected_flags():
    p = provider()

    p.element_pid = Mock(
        return_value=123
    )

    def read(
        element,
        attribute,
        _unused,
    ):
        if attribute == "AXRole":
            return (
                0,
                "AXTextArea",
            )

        return (
            -2,
            None,
        )

    p.ax.AXUIElementCopyAttributeValue.side_effect = read

    node = p.read_node(
        "focused"
    )

    assert node["role"] == "AXTextArea"

    attributes = [
        call.args[1]
        for call in (
            p.ax.AXUIElementCopyAttributeValue
            .call_args_list
        )
    ]

    assert "AXFocused" not in attributes
    assert "AXSelected" not in attributes
