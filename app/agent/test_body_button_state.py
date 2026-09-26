from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from app.agent.body_button_state import (
    BODY_BUTTON_CLEAR,
    BODY_BUTTON_HELD,
    BODY_BUTTON_UNKNOWN,
    BODY_MOUSE_BUTTONS,
    BodyButtonSnapshot,
    BodyButtonStateError,
    BodyButtonStateStore,
)


class FakeClock:

    def __init__(
        self,
    ):
        self.value = 100.0

    def __call__(
        self,
    ):
        value = self.value
        self.value += 1.0
        return value


def make_store():

    return BodyButtonStateStore(
        clock=FakeClock(),
    )


def test_initial_state_is_clear():

    state = make_store().snapshot()

    assert (
        state.status
        == BODY_BUTTON_CLEAR
    )

    assert state.button is None
    assert state.generation == 0


def test_press_success_records_exact_held_button():

    store = make_store()

    state = (
        store._record_press_success(
            "left"
        )
    )

    assert (
        state.status
        == BODY_BUTTON_HELD
    )

    assert state.button == "left"
    assert state.generation == 1


def test_release_success_clears_exact_held_button():

    store = make_store()

    store._record_press_success(
        "right"
    )

    state = (
        store._record_release_success(
            "right"
        )
    )

    assert (
        state.status
        == BODY_BUTTON_CLEAR
    )

    assert state.button is None
    assert state.generation == 2


def test_uncertain_from_clear_records_candidate_button():

    store = make_store()

    state = (
        store._record_uncertain(
            "middle"
        )
    )

    assert (
        state.status
        == BODY_BUTTON_UNKNOWN
    )

    assert (
        state.button
        == "middle"
    )


def test_uncertain_from_held_preserves_same_button():

    store = make_store()

    store._record_press_success(
        "left"
    )

    state = (
        store._record_uncertain(
            "left"
        )
    )

    assert (
        state.status
        == BODY_BUTTON_UNKNOWN
    )

    assert state.button == "left"


def test_unknown_from_clear_survives_clock_failure():

    calls = 0

    def clock():

        nonlocal calls
        calls += 1

        if calls == 1:
            return 100.0

        raise RuntimeError(
            "clock unavailable"
        )

    store = BodyButtonStateStore(
        clock=clock
    )

    initial = store.snapshot()

    state = (
        store._record_uncertain(
            "left"
        )
    )

    assert (
        state.status
        == BODY_BUTTON_UNKNOWN
    )

    assert state.button == "left"

    assert (
        state.generation
        == initial.generation + 1
    )

    assert (
        state.changed_at_monotonic
        == initial.changed_at_monotonic
    )


def test_unknown_from_held_survives_clock_failure():

    values = iter(
        (
            100.0,
            101.0,
        )
    )

    def clock():

        try:
            return next(values)

        except StopIteration:
            raise RuntimeError(
                "clock unavailable"
            )

    store = BodyButtonStateStore(
        clock=clock
    )

    held = (
        store._record_press_success(
            "middle"
        )
    )

    state = (
        store._record_uncertain(
            "middle"
        )
    )

    assert (
        state.status
        == BODY_BUTTON_UNKNOWN
    )

    assert (
        state.button
        == "middle"
    )

    assert (
        state.generation
        == held.generation + 1
    )

    assert (
        state.changed_at_monotonic
        == held.changed_at_monotonic
    )


def test_unknown_recording_survives_baseexception_clock():

    calls = 0

    def clock():

        nonlocal calls
        calls += 1

        if calls == 1:
            return 100.0

        raise KeyboardInterrupt()

    store = BodyButtonStateStore(
        clock=clock
    )

    state = (
        store._record_uncertain(
            "right"
        )
    )

    assert (
        state.status
        == BODY_BUTTON_UNKNOWN
    )

    assert state.button == "right"


def test_successful_recovery_release_can_clear_unknown():

    store = make_store()

    store._record_uncertain(
        "left"
    )

    state = (
        store._record_release_success(
            "left"
        )
    )

    assert (
        state.status
        == BODY_BUTTON_CLEAR
    )

    assert state.button is None


def test_second_press_is_rejected_without_state_change():

    store = make_store()

    held = (
        store._record_press_success(
            "left"
        )
    )

    with pytest.raises(
        BodyButtonStateError,
        match="CLEAR",
    ):
        store._record_press_success(
            "right"
        )

    assert (
        store.snapshot()
        == held
    )


def test_release_from_clear_is_rejected():

    store = make_store()

    initial = store.snapshot()

    with pytest.raises(
        BodyButtonStateError,
        match="no KUMA-owned button",
    ):
        store._record_release_success(
            "left"
        )

    assert (
        store.snapshot()
        == initial
    )


def test_mismatched_release_is_rejected_without_state_change():

    store = make_store()

    held = (
        store._record_press_success(
            "left"
        )
    )

    with pytest.raises(
        BodyButtonStateError,
        match="does not match",
    ):
        store._record_release_success(
            "right"
        )

    assert (
        store.snapshot()
        == held
    )


def test_conflicting_unknown_button_is_rejected():

    store = make_store()

    store._record_press_success(
        "left"
    )

    with pytest.raises(
        BodyButtonStateError,
        match="different button",
    ):
        store._record_uncertain(
            "right"
        )

    state = store.snapshot()

    assert (
        state.status
        == BODY_BUTTON_HELD
    )

    assert state.button == "left"


@pytest.mark.parametrize(
    "button",
    [
        "",
        " left",
        "left ",
        "LEFT",
        "sideways",
        True,
        1,
        None,
    ],
)
def test_button_identity_is_exact_and_fail_closed(
    button,
):

    store = make_store()

    with pytest.raises(
        BodyButtonStateError,
        match="exactly one of",
    ):
        store._record_press_success(
            button
        )

    assert (
        store.snapshot().status
        == BODY_BUTTON_CLEAR
    )


def test_supported_button_surface_is_exact():

    assert BODY_MOUSE_BUTTONS == {
        "left",
        "right",
        "middle",
    }


def test_snapshot_is_immutable():

    snapshot = make_store().snapshot()

    with pytest.raises(
        FrozenInstanceError
    ):
        snapshot.status = (
            BODY_BUTTON_HELD
        )


def test_snapshot_invariants_reject_fake_clear_with_button():

    with pytest.raises(
        BodyButtonStateError,
        match="must not name",
    ):
        BodyButtonSnapshot(
            status=BODY_BUTTON_CLEAR,
            button="left",
            generation=0,
            changed_at_monotonic=1.0,
        )


def test_snapshot_invariants_reject_held_without_button():

    with pytest.raises(
        BodyButtonStateError,
        match="exactly one of",
    ):
        BodyButtonSnapshot(
            status=BODY_BUTTON_HELD,
            button=None,
            generation=0,
            changed_at_monotonic=1.0,
        )


def test_generation_increases_on_every_valid_transition():

    store = make_store()

    assert (
        store.snapshot().generation
        == 0
    )

    assert (
        store._record_press_success(
            "left"
        ).generation
        == 1
    )

    assert (
        store._record_uncertain(
            "left"
        ).generation
        == 2
    )

    assert (
        store._record_release_success(
            "left"
        ).generation
        == 3
    )


def test_serialized_transition_is_reentrant():

    store = make_store()

    with store.serialized_transition():

        assert (
            store.snapshot().status
            == BODY_BUTTON_CLEAR
        )

        store._record_press_success(
            "left"
        )

        assert (
            store.snapshot().status
            == BODY_BUTTON_HELD
        )


def test_store_has_no_public_clear_or_restore_surface():

    store = make_store()

    assert not hasattr(
        store,
        "clear",
    )

    assert not hasattr(
        store,
        "reset",
    )

    assert not hasattr(
        store,
        "set",
    )

    assert not hasattr(
        store,
        "from_dict",
    )


def test_module_is_runtime_state_only_not_execution_or_persistence():

    source = (
        Path(__file__)
        .with_name(
            "body_button_state.py"
        )
        .read_text()
    )

    tree = ast.parse(
        source
    )

    imported_modules = set()

    for node in ast.walk(
        tree
    ):

        if isinstance(
            node,
            ast.Import,
        ):
            imported_modules.update(
                alias.name
                for alias in node.names
            )

        elif isinstance(
            node,
            ast.ImportFrom,
        ):
            imported_modules.add(
                node.module
                or ""
            )

    forbidden_import_prefixes = (
        "pyautogui",
        "app.tools",
        "app.agent.permissions",
        "app.agent.mission_service",
        "app.agent.mission_persistence",
        "app.agent.mission_state",
        "app.agent.goal_plan",
    )

    for module in imported_modules:
        assert not module.startswith(
            forbidden_import_prefixes
        )

    function_names = {
        node.name
        for node in ast.walk(
            tree
        )
        if isinstance(
            node,
            (
                ast.FunctionDef,
                ast.AsyncFunctionDef,
            ),
        )
    }

    assert "to_dict" not in function_names
    assert "from_dict" not in function_names
    assert "clear" not in function_names
    assert "reset" not in function_names
    assert "set" not in function_names
