from dataclasses import replace
import json
import math

import pytest

from app.desktop.contracts import ApplicationIdentity
from app.ui_observation.contracts import StructuredUIObservation, UIElementObservation


APP = ApplicationIdentity(123, "test.app", "Example")


def element(**changes):
    values = dict(
        path=(),
        owner_pid=123,
        role="AXApplication",
        position_x=10.5,
        position_y=-20.25,
        width=0.0,
        height=300.0,
    )
    values.update(changes)
    return UIElementObservation(**values)


def snapshot(item=None, *, status="available", diagnostics=()):
    return StructuredUIObservation(
        captured_at_monotonic=100.0,
        status=status,
        active_application=APP,
        elements=(item or element(),),
        traversal_succeeded=True,
        diagnostics=diagnostics,
    )


def test_geometry_preserves_finite_negative_position_and_zero_size():
    item = element()
    assert item.position_x == 10.5
    assert item.position_y == -20.25
    assert item.width == 0.0
    assert item.height == 300.0


def test_position_and_size_may_each_be_independently_unknown():
    assert element(position_x=None, position_y=None).position_x is None
    assert element(width=None, height=None).width is None
    unknown = element(position_x=None, position_y=None, width=None, height=None)
    assert unknown.position_x is unknown.width is None


@pytest.mark.parametrize(
    "changes",
    [
        {"position_x": None},
        {"position_y": None},
        {"width": None},
        {"height": None},
    ],
)
def test_geometry_pairs_must_be_complete_or_unknown(changes):
    with pytest.raises(ValueError):
        element(**changes)


@pytest.mark.parametrize(
    "field,value",
    [
        ("position_x", float("nan")),
        ("position_y", float("inf")),
        ("position_x", True),
        ("position_y", "1"),
        ("width", float("nan")),
        ("height", float("inf")),
        ("width", True),
        ("height", "1"),
        ("width", -0.01),
        ("height", -1),
    ],
)
def test_invalid_geometry_is_rejected_without_coercion(field, value):
    with pytest.raises(ValueError):
        element(**{field: value})


def test_geometry_round_trips_through_worker_payload_contract():
    original = snapshot(
        element(
            position_x=-100.5,
            position_y=42.25,
            width=800.0,
            height=600.0,
            title="Visible title",
        )
    )
    payload = json.loads(
        json.dumps(original.to_dict(include_text=True))
    )
    restored = StructuredUIObservation.from_dict(payload)
    assert restored == original
    assert restored.elements[0].position_x == -100.5
    assert restored.elements[0].height == 600.0


def test_text_redaction_does_not_redact_trusted_geometry():
    original = snapshot(element(title="Secret", description="Untrusted text"))
    payload = original.to_dict()
    raw = payload["elements"][0]
    assert raw["title"] is None
    assert raw["description"] is None
    assert raw["position_x"] == 10.5
    assert raw["width"] == 0.0


def test_geometry_unavailable_is_valid_partial_source_diagnostic():
    result = snapshot(
        element(position_x=None, position_y=None, width=None, height=None),
        status="partial",
        diagnostics=("geometry_unavailable",),
    )
    assert result.status == "partial"
    assert result.diagnostics == ("geometry_unavailable",)


def test_geometry_fields_are_immutable_evidence():
    item = element()
    with pytest.raises(Exception):
        item.position_x = 999
    changed = replace(item, position_x=99.0)
    assert changed.position_x == 99.0
    assert item.position_x == 10.5
