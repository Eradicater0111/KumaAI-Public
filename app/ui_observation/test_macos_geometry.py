from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.ui_observation.macos import MacOSAccessibilityProvider


class Point:
    def __init__(self, x, y):
        self.x = x
        self.y = y


class Size:
    def __init__(self, width, height):
        self.width = width
        self.height = height


def provider():
    p = object.__new__(MacOSAccessibilityProvider)
    p.ax = SimpleNamespace(
        kAXErrorSuccess=0,
        kAXErrorAttributeUnsupported=-1,
        kAXErrorNoValue=-2,
        kAXPositionAttribute="AXPosition",
        kAXSizeAttribute="AXSize",
        kAXValueCGPointType=1,
        kAXValueCGSizeType=2,
        AXUIElementCopyAttributeValue=Mock(),
        AXValueGetType=Mock(),
        AXValueGetValue=Mock(),
    )
    return p


def test_geometry_uses_axvalue_type_and_decode_not_repr_parsing():
    p = provider()
    position = object()
    size = object()

    def copy(_element, attribute, _unused):
        if attribute == "AXPosition":
            return 0, position
        return 0, size

    p.ax.AXUIElementCopyAttributeValue.side_effect = copy
    p.ax.AXValueGetType.side_effect = lambda value: 1 if value is position else 2
    p.ax.AXValueGetValue.side_effect = lambda value, kind, _unused: (
        (True, Point(-12.5, 956.0)) if kind == 1
        else (True, Size(0.0, 44.25))
    )

    result = p.read_geometry("node")
    assert result == {
        "position_x": -12.5,
        "position_y": 956.0,
        "width": 0.0,
        "height": 44.25,
    }
    assert p.ax.AXValueGetValue.call_args_list[0].args == (position, 1, None)
    assert p.ax.AXValueGetValue.call_args_list[1].args == (size, 2, None)


def test_unsupported_position_or_size_remains_unknown():
    p = provider()
    p.ax.AXUIElementCopyAttributeValue.return_value = (-1, None)
    assert p.read_geometry("node") == {
        "position_x": None,
        "position_y": None,
        "width": None,
        "height": None,
    }
    p.ax.AXValueGetValue.assert_not_called()


def test_wrong_axvalue_type_fails_closed():
    p = provider()
    p.ax.AXUIElementCopyAttributeValue.return_value = (0, object())
    p.ax.AXValueGetType.return_value = 999
    with pytest.raises(RuntimeError, match="geometry decode failed"):
        p.read_geometry("node")


@pytest.mark.parametrize(
    "decoded",
    [
        False,
        (False, Point(1, 2)),
        (True, None),
        (True,),
        [True, Point(1, 2)],
    ],
)
def test_malformed_axvalue_decode_result_fails_closed(decoded):
    p = provider()
    p.ax.AXUIElementCopyAttributeValue.return_value = (0, object())
    p.ax.AXValueGetType.return_value = 1
    p.ax.AXValueGetValue.return_value = decoded
    with pytest.raises(RuntimeError, match="geometry decode failed"):
        p.read_geometry("node")


def test_nonfinite_point_is_rejected():
    p = provider()
    position = object()
    size = object()
    p.ax.AXUIElementCopyAttributeValue.side_effect = [
        (0, position),
        (0, size),
    ]
    p.ax.AXValueGetType.side_effect = [1, 2]
    p.ax.AXValueGetValue.side_effect = [
        (True, Point(float("nan"), 10.0)),
        (True, Size(1.0, 1.0)),
    ]
    with pytest.raises(RuntimeError, match="position is invalid"):
        p.read_geometry("node")


def test_negative_size_is_rejected_but_zero_size_is_preserved():
    p = provider()
    position = object()
    size = object()
    p.ax.AXUIElementCopyAttributeValue.side_effect = [(0, position), (0, size)]
    p.ax.AXValueGetType.side_effect = [1, 2]
    p.ax.AXValueGetValue.side_effect = [
        (True, Point(0.0, 956.0)),
        (True, Size(0.0, 0.0)),
    ]
    assert p.read_geometry("node")["width"] == 0.0

    p = provider()
    p.ax.AXUIElementCopyAttributeValue.side_effect = [(0, position), (0, size)]
    p.ax.AXValueGetType.side_effect = [1, 2]
    p.ax.AXValueGetValue.side_effect = [
        (True, Point(0.0, 0.0)),
        (True, Size(-1.0, 10.0)),
    ]
    with pytest.raises(RuntimeError, match="size is invalid"):
        p.read_geometry("node")
