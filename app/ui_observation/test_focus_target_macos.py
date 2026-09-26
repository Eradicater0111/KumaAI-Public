from pathlib import Path
from types import SimpleNamespace
from unittest.mock import (
    Mock,
)

import pytest

from app.ui_observation.focus_target_macos import (
    MacOSFocusTargetProvider,
)
from app.ui_observation.target_resolution import (
    StructuredUITargetSelector,
)


def provider():
    result = object.__new__(
        MacOSFocusTargetProvider
    )

    result.ax = SimpleNamespace(
        kAXRoleAttribute="AXRole",
        kAXSubroleAttribute="AXSubrole",
        kAXTitleAttribute="AXTitle",
        kAXDescriptionAttribute="AXDescription",
        kAXEnabledAttribute="AXEnabled",
        kAXErrorSuccess=0,
        kAXErrorAttributeUnsupported=-25205,
        kAXErrorNoValue=-25212,
        kAXErrorFailure=-25200,
        AXUIElementCopyAttributeValue=Mock(),
    )

    result.read_geometry = Mock(
        return_value={
            "position_x": 10.0,
            "position_y": 20.0,
            "width": 200.0,
            "height": 30.0,
        }
    )

    return result


def attributes_read(
    p,
):
    return [
        call.args[
            1
        ]
        for call
        in (
            p.ax
            .AXUIElementCopyAttributeValue
            .call_args_list
        )
    ]


def test_role_only_selector_reads_role_only():
    p = provider()

    p.ax.AXUIElementCopyAttributeValue.return_value = (
        0,
        "AXTextArea",
    )

    result = p.read_target_node(
        "node",
        StructuredUITargetSelector(
            role="AXTextArea"
        ),
    )

    assert (
        result[
            "role"
        ]
        == "AXTextArea"
    )

    assert (
        attributes_read(
            p
        )
        == [
            "AXRole",
        ]
    )

    p.read_geometry.assert_not_called()


def test_role_mismatch_short_circuits_text_and_eligibility_reads():
    p = provider()

    p.ax.AXUIElementCopyAttributeValue.return_value = (
        0,
        "AXButton",
    )

    result = p.read_target_node(
        "node",
        StructuredUITargetSelector(
            role="AXTextField",
            text="Search",
            require_enabled=True,
            require_positive_area=True,
        ),
    )

    assert (
        result[
            "role"
        ]
        == "AXButton"
    )

    assert (
        attributes_read(
            p
        )
        == [
            "AXRole",
        ]
    )

    p.read_geometry.assert_not_called()


def test_subrole_mismatch_short_circuits_later_reads():
    p = provider()

    def read(
        element,
        attribute,
        unused,
    ):
        assert element == "node"
        assert unused is None

        if attribute == "AXRole":
            return (
                0,
                "AXTextField",
            )

        if attribute == "AXSubrole":
            return (
                0,
                "AXSecureTextField",
            )

        raise AssertionError(
            attribute
        )

    p.ax.AXUIElementCopyAttributeValue.side_effect = (
        read
    )

    result = p.read_target_node(
        "node",
        StructuredUITargetSelector(
            role="AXTextField",
            subrole="AXSearchField",
            text="Search",
            require_enabled=True,
        ),
    )

    assert (
        result[
            "subrole"
        ]
        == "AXSecureTextField"
    )

    assert (
        attributes_read(
            p
        )
        == [
            "AXRole",
            "AXSubrole",
        ]
    )


def test_text_selector_uses_title_without_reading_description():
    p = provider()

    p.ax.AXUIElementCopyAttributeValue.return_value = (
        0,
        "Search",
    )

    result = p.read_target_node(
        "node",
        StructuredUITargetSelector(
            text="search"
        ),
    )

    assert (
        result[
            "title"
        ]
        == "Search"
    )

    assert (
        result[
            "description"
        ]
        is None
    )

    assert (
        attributes_read(
            p
        )
        == [
            "AXTitle",
        ]
    )


def test_missing_title_falls_back_to_description():
    p = provider()

    def read(
        element,
        attribute,
        unused,
    ):
        if attribute == "AXTitle":
            return (
                -25212,
                None,
            )

        if attribute == "AXDescription":
            return (
                0,
                "Search",
            )

        raise AssertionError(
            attribute
        )

    p.ax.AXUIElementCopyAttributeValue.side_effect = (
        read
    )

    result = p.read_target_node(
        "node",
        StructuredUITargetSelector(
            text="Search"
        ),
    )

    assert (
        result[
            "title"
        ]
        is None
    )

    assert (
        result[
            "description"
        ]
        == "Search"
    )

    assert (
        attributes_read(
            p
        )
        == [
            "AXTitle",
            "AXDescription",
        ]
    )


def test_required_title_hard_native_failure_fails_closed():
    p = provider()

    p.ax.AXUIElementCopyAttributeValue.return_value = (
        -25200,
        None,
    )

    with pytest.raises(
        RuntimeError,
        match="attribute read failed",
    ):
        p.read_target_node(
            "node",
            StructuredUITargetSelector(
                text="Search"
            ),
        )


def test_required_description_hard_native_failure_fails_closed():
    p = provider()

    p.ax.AXUIElementCopyAttributeValue.side_effect = [
        (
            -25212,
            None,
        ),
        (
            -25200,
            None,
        ),
    ]

    with pytest.raises(
        RuntimeError,
        match="attribute read failed",
    ):
        p.read_target_node(
            "node",
            StructuredUITargetSelector(
                text="Search"
            ),
        )


def test_missing_text_is_known_nonmatch_and_skips_eligibility():
    p = provider()

    p.ax.AXUIElementCopyAttributeValue.side_effect = [
        (
            -25212,
            None,
        ),
        (
            -25205,
            None,
        ),
    ]

    result = p.read_target_node(
        "node",
        StructuredUITargetSelector(
            text="Search",
            require_enabled=True,
            require_positive_area=True,
        ),
    )

    assert result[
        "title"
    ] is None

    assert result[
        "description"
    ] is None

    assert result[
        "enabled"
    ] is None

    assert (
        attributes_read(
            p
        )
        == [
            "AXTitle",
            "AXDescription",
        ]
    )

    p.read_geometry.assert_not_called()


def test_enabled_is_read_only_after_semantic_match():
    p = provider()

    def read(
        element,
        attribute,
        unused,
    ):
        if attribute == "AXRole":
            return (
                0,
                "AXTextField",
            )

        if attribute == "AXEnabled":
            return (
                0,
                True,
            )

        raise AssertionError(
            attribute
        )

    p.ax.AXUIElementCopyAttributeValue.side_effect = (
        read
    )

    result = p.read_target_node(
        "node",
        StructuredUITargetSelector(
            role="AXTextField",
            require_enabled=True,
        ),
    )

    assert (
        result[
            "enabled"
        ]
        is True
    )

    assert (
        attributes_read(
            p
        )
        == [
            "AXRole",
            "AXEnabled",
        ]
    )


def test_unknown_required_enabled_state_remains_none():
    p = provider()

    def read(
        element,
        attribute,
        unused,
    ):
        if attribute == "AXRole":
            return (
                0,
                "AXTextField",
            )

        if attribute == "AXEnabled":
            return (
                -25212,
                None,
            )

        raise AssertionError(
            attribute
        )

    p.ax.AXUIElementCopyAttributeValue.side_effect = (
        read
    )

    result = p.read_target_node(
        "node",
        StructuredUITargetSelector(
            role="AXTextField",
            require_enabled=True,
        ),
    )

    assert (
        result[
            "enabled"
        ]
        is None
    )


def test_positive_area_reads_geometry_only_after_semantic_match():
    p = provider()

    p.ax.AXUIElementCopyAttributeValue.return_value = (
        0,
        "AXTextField",
    )

    result = p.read_target_node(
        "node",
        StructuredUITargetSelector(
            role="AXTextField",
            require_positive_area=True,
        ),
    )

    p.read_geometry.assert_called_once_with(
        "node"
    )

    assert (
        result[
            "position_x"
        ]
        == 10.0
    )

    assert (
        result[
            "position_y"
        ]
        == 20.0
    )

    assert (
        result[
            "width"
        ]
        == 200.0
    )

    assert (
        result[
            "height"
        ]
        == 30.0
    )


def test_combined_selector_reads_only_required_surface():
    p = provider()

    def read(
        element,
        attribute,
        unused,
    ):
        values = {
            "AXRole": (
                0,
                "AXTextField",
            ),
            "AXTitle": (
                0,
                "Search",
            ),
            "AXEnabled": (
                0,
                True,
            ),
        }

        return values[
            attribute
        ]

    p.ax.AXUIElementCopyAttributeValue.side_effect = (
        read
    )

    result = p.read_target_node(
        "node",
        StructuredUITargetSelector(
            role="AXTextField",
            text="search",
            require_enabled=True,
            require_positive_area=True,
        ),
    )

    assert (
        result[
            "role"
        ]
        == "AXTextField"
    )

    assert (
        result[
            "title"
        ]
        == "Search"
    )

    assert (
        result[
            "enabled"
        ]
        is True
    )

    assert (
        attributes_read(
            p
        )
        == [
            "AXRole",
            "AXTitle",
            "AXEnabled",
        ]
    )

    p.read_geometry.assert_called_once_with(
        "node"
    )


def test_selector_required_ax_failure_is_not_focus_metadata_relaxation():
    p = provider()

    p.ax.AXUIElementCopyAttributeValue.return_value = (
        -25200,
        None,
    )

    with pytest.raises(
        RuntimeError
    ):
        p.read_target_node(
            "node",
            StructuredUITargetSelector(
                role="AXTextArea"
            ),
        )


def test_invalid_selector_type_is_rejected():
    p = provider()

    with pytest.raises(
        TypeError,
        match="selector",
    ):
        p.read_target_node(
            "node",
            object(),
        )

    p.ax.AXUIElementCopyAttributeValue.assert_not_called()


def test_focused_and_selected_are_never_read():
    p = provider()

    p.ax.AXUIElementCopyAttributeValue.return_value = (
        0,
        "AXTextArea",
    )

    p.read_target_node(
        "node",
        StructuredUITargetSelector(
            role="AXTextArea"
        ),
    )

    attributes = attributes_read(
        p
    )

    assert "AXFocused" not in attributes
    assert "AXSelected" not in attributes


def test_module_is_read_only_and_has_no_execution_surface():
    path = Path(
        __file__
    ).with_name(
        "focus_target_macos.py"
    )

    text = path.read_text(
        encoding="utf-8"
    )

    forbidden = (
        "AXUIElementSetAttributeValue",
        "AXUIElementPerformAction",
        "AXPress",
        "AXConfirm",
        "AXRaise",
        "pyautogui",
        "computer_tools",
        "mission_service",
    )

    for marker in forbidden:
        assert marker not in text
