from dataclasses import FrozenInstanceError
import json

import pytest

from app.desktop.contracts import ApplicationIdentity
from app.ui_observation.contracts import (
    MAX_UI_CHILDREN,
    MAX_UI_DEPTH,
    MAX_UI_NODES,
    StructuredUIObservation,
    UIElementObservation,
)


APP = ApplicationIdentity(123, "test.app", "Example")


def sample():
    return StructuredUIObservation(
        captured_at_monotonic=10.0,
        status="available",
        active_application=APP,
        elements=(
            UIElementObservation(path=(), owner_pid=123, role="AXApplication"),
            UIElementObservation(
                path=(0,), owner_pid=123, role="AXButton",
                title="Settings", description="Untrusted visible text", enabled=True,
            ),
        ),
        traversal_succeeded=True,
    )


def test_contracts_are_frozen_and_text_is_redacted_by_default():
    result = sample()
    with pytest.raises(FrozenInstanceError):
        result.status = "partial"
    assert "Settings" not in repr(result)
    redacted = result.to_dict()
    assert redacted["elements"][1]["title"] is None
    assert redacted["elements"][1]["description"] is None
    visible = result.to_dict(include_text=True)
    assert visible["elements"][1]["title"] == "Settings"


def test_round_trip_preserves_exact_types():
    result = sample()
    encoded = json.loads(json.dumps(result.to_dict(include_text=True)))
    assert StructuredUIObservation.from_dict(encoded) == result


def test_extra_fields_and_invalid_paths_are_rejected():
    payload = json.loads(json.dumps(sample().to_dict(include_text=True)))
    payload["extra_authority"] = True
    with pytest.raises(TypeError):
        StructuredUIObservation.from_dict(payload)
    with pytest.raises(ValueError):
        UIElementObservation(path=(MAX_UI_CHILDREN,), owner_pid=123)
    with pytest.raises(ValueError):
        UIElementObservation(path=tuple(0 for _ in range(MAX_UI_DEPTH + 1)), owner_pid=123)


def test_parent_path_and_process_ownership_are_required():
    with pytest.raises(ValueError):
        StructuredUIObservation(
            captured_at_monotonic=1,
            status="available",
            active_application=APP,
            elements=(UIElementObservation(path=(0,), owner_pid=123, role="AXButton"),),
            traversal_succeeded=True,
        )
    with pytest.raises(ValueError):
        StructuredUIObservation(
            captured_at_monotonic=1,
            status="available",
            active_application=APP,
            elements=(UIElementObservation(path=(), owner_pid=456, role="AXApplication"),),
            traversal_succeeded=True,
        )


def test_unavailable_cannot_claim_tree_evidence():
    with pytest.raises(ValueError):
        StructuredUIObservation(
            captured_at_monotonic=1,
            status="unavailable",
            active_application=APP,
            elements=(UIElementObservation(path=(), owner_pid=123),),
            traversal_succeeded=True,
            diagnostics=("collection_failed",),
        )


def test_node_bound_is_enforced():
    elements = [UIElementObservation(path=(), owner_pid=123, role="AXApplication")]
    # Constructing > MAX_UI_NODES is rejected before any consumer can use it.
    elements.extend(UIElementObservation(path=(0,), owner_pid=123) for _ in range(MAX_UI_NODES))
    with pytest.raises(ValueError):
        StructuredUIObservation(
            captured_at_monotonic=1,
            status="partial",
            active_application=APP,
            elements=tuple(elements),
            traversal_succeeded=True,
            diagnostics=("nodes_truncated",),
        )
