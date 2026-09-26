from dataclasses import (
    FrozenInstanceError,
    replace,
)

import pytest

from app.desktop.contracts import (
    ApplicationIdentity,
)

from app.ui_observation.focus_contracts import (
    FOCUS_OBSERVATION_SCOPE,
    FOCUS_STATUS_AVAILABLE,
    FOCUS_STATUS_UNAVAILABLE,
    FocusedUIObservation,
    unavailable_focus,
)


APP = ApplicationIdentity(
    123,
    "test.app",
    "Example",
)


def focus(**changes):
    values = dict(
        captured_at_monotonic=100.0,
        status=FOCUS_STATUS_AVAILABLE,
        active_application=APP,
        role="AXTextField",
        subrole=None,
        title="",
        description="Search",
        enabled=True,
        position_x=10.0,
        position_y=20.0,
        width=300.0,
        height=30.0,
        observation_id="1" * 32,
    )

    values.update(
        changes
    )

    return FocusedUIObservation(
        **values
    )


def test_available_focus_is_exact_immutable_evidence():
    result = focus()

    assert (
        result.status
        == FOCUS_STATUS_AVAILABLE
    )

    assert (
        result.active_application
        is APP
    )

    assert result.role == "AXTextField"
    assert result.description == "Search"

    assert (
        result.scope
        == FOCUS_OBSERVATION_SCOPE
    )

    assert result.diagnostics == ()

    with pytest.raises(
        FrozenInstanceError
    ):
        result.role = "AXButton"


def test_json_shaped_round_trip_preserves_evidence():
    original = focus()

    payload = original.to_dict()

    # JSON transport converts tuples to lists.
    payload["diagnostics"] = list(
        payload["diagnostics"]
    )

    restored = (
        FocusedUIObservation.from_dict(
            payload
        )
    )

    assert restored == original
    assert (
        restored.active_application
        == original.active_application
    )


@pytest.mark.parametrize(
    "app",
    [
        None,
        ApplicationIdentity(123),
        ApplicationIdentity(
            123,
            "",
            "Example",
        ),
    ],
)
def test_available_focus_requires_complete_application_identity(
    app,
):
    with pytest.raises(
        ValueError,
        match="complete application identity",
    ):
        focus(
            active_application=app
        )


@pytest.mark.parametrize(
    "role",
    [
        None,
        "",
        "   ",
    ],
)
def test_available_focus_requires_exact_role(
    role,
):
    with pytest.raises(
        ValueError,
        match="exact AX role",
    ):
        focus(
            role=role
        )


def test_available_focus_cannot_carry_failure_diagnostic():
    with pytest.raises(
        ValueError,
        match="cannot contain diagnostics",
    ):
        focus(
            diagnostics=(
                "collection_failed",
            )
        )


def test_unavailable_focus_carries_only_one_reason():
    result = unavailable_focus(
        "focused_element_unavailable",
        100.0,
    )

    assert (
        result.status
        == FOCUS_STATUS_UNAVAILABLE
    )

    assert result.active_application is None
    assert result.role is None
    assert result.title is None
    assert result.description is None
    assert result.enabled is None

    assert result.diagnostics == (
        "focused_element_unavailable",
    )


def test_unavailable_focus_cannot_retain_element_claims():
    unavailable = unavailable_focus(
        "collection_failed",
        100.0,
    )

    with pytest.raises(
        ValueError,
        match="cannot carry",
    ):
        replace(
            unavailable,
            role="AXTextField",
        )

    with pytest.raises(
        ValueError,
        match="cannot carry",
    ):
        replace(
            unavailable,
            active_application=APP,
        )


@pytest.mark.parametrize(
    "changes",
    [
        dict(
            position_x=1.0,
            position_y=None,
        ),
        dict(
            width=10.0,
            height=None,
        ),
        dict(
            position_x=float("nan"),
            position_y=1.0,
        ),
        dict(
            width=-1.0,
            height=10.0,
        ),
        dict(
            enabled="yes",
        ),
    ],
)
def test_malformed_element_metadata_is_rejected(
    changes,
):
    with pytest.raises(
        ValueError
    ):
        focus(
            **changes
        )


@pytest.mark.parametrize(
    "captured",
    [
        -1,
        float("nan"),
        float("inf"),
        True,
        "100",
    ],
)
def test_invalid_capture_time_is_rejected(
    captured,
):
    with pytest.raises(
        ValueError,
        match="timestamp",
    ):
        focus(
            captured_at_monotonic=captured
        )


def test_unknown_status_and_scope_are_rejected():
    with pytest.raises(
        ValueError,
        match="status",
    ):
        focus(
            status="focused"
        )

    with pytest.raises(
        ValueError,
        match="scope",
    ):
        focus(
            scope="tree_path"
        )


def test_payload_rejects_path_and_authority_claims():
    payload = focus().to_dict()
    payload["diagnostics"] = []

    for forbidden in (
        "path",
        "ax_object",
        "authorized",
        "permission",
        "keyboard_authority",
        "semantic_target_verified",
        "type_text",
    ):
        forged = dict(payload)
        forged[forbidden] = True

        with pytest.raises(
            ValueError,
            match="unsupported fields",
        ):
            FocusedUIObservation.from_dict(
                forged
            )


def test_contract_has_no_tree_path_or_execution_surface():
    result = focus()

    for name in (
        "path",
        "ax_object",
        "focused_window_id",
        "permission",
        "authorized",
        "semantic_target_verified",
        "execute",
        "type_text",
    ):
        assert not hasattr(
            result,
            name,
        )
