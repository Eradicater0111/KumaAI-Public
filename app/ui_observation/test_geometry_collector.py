from unittest.mock import Mock

from app.desktop.contracts import ApplicationIdentity
from app.ui_observation.collector import assemble_structured_ui_snapshot


APP = ApplicationIdentity(123, "test.app", "Example")


class Node:
    def __init__(self, name, children=None):
        self.name = name
        self.children = list(children or [])


class Provider:
    def __init__(self, root, *, geometry=None, geometry_error=None):
        self.root = root
        self.frontmost = Mock(side_effect=[APP, APP])
        self.geometry = geometry or {}
        self.geometry_error = geometry_error or set()

    def accessibility_trusted(self):
        return True

    def frontmost_application(self):
        return self.frontmost()

    def application_element(self, pid):
        return self.root

    def element_pid(self, element):
        return 123

    def read_node(self, element):
        return {
            "owner_pid": 123,
            "role": "AXApplication" if element is self.root else "AXButton",
            "subrole": None,
            "title": element.name,
            "description": None,
            "enabled": True,
            "focused": False,
            "selected": None,
        }

    def read_geometry(self, element):
        if element.name in self.geometry_error:
            raise RuntimeError("private geometry bridge failure")
        return self.geometry.get(
            element.name,
            {
                "position_x": None,
                "position_y": None,
                "width": None,
                "height": None,
            },
        )

    def children_for_element(self, element, limit):
        return element.children[:limit], len(element.children) > limit

    def element_identity(self, element):
        return id(element)


def collect(provider):
    return assemble_structured_ui_snapshot(
        provider,
        expected_application=APP,
        clock=lambda: 100.0,
    )


def test_collector_preserves_native_geometry_without_coordinate_conversion():
    root = Node("App", [Node("Button")])
    provider = Provider(
        root,
        geometry={
            "App": {
                "position_x": 0.0,
                "position_y": 956.0,
                "width": 0.0,
                "height": 0.0,
            },
            "Button": {
                "position_x": 250.5,
                "position_y": 300.25,
                "width": 120.0,
                "height": 44.0,
            },
        },
    )
    result = collect(provider)
    assert result.status == "available"
    assert result.elements[0].position_y == 956.0
    assert result.elements[0].width == 0.0
    assert result.elements[1].position_x == 250.5
    assert result.elements[1].height == 44.0


def test_missing_optional_ax_geometry_is_unknown_without_inventing_zeroes():
    result = collect(Provider(Node("App")))
    assert result.status == "available"
    item = result.elements[0]
    assert item.position_x is None
    assert item.position_y is None
    assert item.width is None
    assert item.height is None




def test_provider_without_geometry_reader_remains_semantic_only_compatible():
    root = Node("App")
    provider = Provider(root)
    provider.read_geometry = None
    result = collect(provider)
    assert result.status == "available"
    assert result.diagnostics == ()
    assert result.elements[0].position_x is None


def test_geometry_bridge_failure_is_partial_but_semantic_node_survives():
    root = Node("App", [Node("Button")])
    result = collect(Provider(root, geometry_error={"Button"}))
    assert result.status == "partial"
    assert result.diagnostics == ("geometry_unavailable",)
    assert [item.title for item in result.elements] == ["App", "Button"]
    assert result.elements[1].position_x is None
    assert "private" not in repr(result)


def test_malformed_geometry_pair_is_partial_and_not_promoted_to_coordinates():
    root = Node("App")
    provider = Provider(
        root,
        geometry={
            "App": {
                "position_x": 10.0,
                "position_y": None,
                "width": 100.0,
                "height": 100.0,
            }
        },
    )
    result = collect(provider)
    assert result.status == "partial"
    assert result.diagnostics == ("geometry_unavailable",)
    item = result.elements[0]
    assert item.position_x is None
    assert item.width is None


def test_invalid_geometry_number_is_partial_not_node_read_failure():
    root = Node("App")
    provider = Provider(
        root,
        geometry={
            "App": {
                "position_x": float("nan"),
                "position_y": 1.0,
                "width": 100.0,
                "height": 100.0,
            }
        },
    )
    result = collect(provider)
    assert result.status == "partial"
    assert result.diagnostics == ("geometry_unavailable",)
    assert len(result.elements) == 1
    assert result.elements[0].role == "AXApplication"


def test_negative_ax_position_is_preserved_but_negative_size_is_rejected():
    root = Node("App", [Node("BadSize")])
    provider = Provider(
        root,
        geometry={
            "App": {
                "position_x": -500.0,
                "position_y": -20.0,
                "width": 200.0,
                "height": 100.0,
            },
            "BadSize": {
                "position_x": 0.0,
                "position_y": 0.0,
                "width": -1.0,
                "height": 10.0,
            },
        },
    )
    result = collect(provider)
    assert result.status == "partial"
    assert result.elements[0].position_x == -500.0
    assert result.elements[1].width is None
    assert "geometry_unavailable" in result.diagnostics
