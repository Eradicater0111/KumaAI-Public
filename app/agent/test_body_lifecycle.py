from __future__ import annotations

import ast
import inspect
from pathlib import Path
from unittest.mock import patch

import pytest

import app.agent.body_button_state as body_state_module
import app.agent.body_lifecycle as lifecycle_module

from app.agent.body_button_state import (
    BODY_BUTTON_CLEAR,
    BODY_BUTTON_HELD,
    BODY_BUTTON_UNKNOWN,
    BodyButtonStateStore,
)

from app.agent.body_lifecycle import (
    release_owned_mouse_button_for_shutdown,
)


@pytest.fixture
def state_store(
    monkeypatch,
):

    store = BodyButtonStateStore(
        clock=lambda: 100.0,
    )

    monkeypatch.setattr(
        body_state_module,
        "BODY_BUTTON_STATE",
        store,
    )

    monkeypatch.setattr(
        lifecycle_module,
        "BODY_BUTTON_STATE",
        store,
    )

    return store


def test_shutdown_cleanup_accepts_no_arguments():

    signature = inspect.signature(
        release_owned_mouse_button_for_shutdown
    )

    assert tuple(
        signature.parameters
    ) == ()


def test_clear_state_is_successful_noop(
    state_store,
):

    with patch.object(
        lifecycle_module,
        "release_mouse",
    ) as release:

        result = (
            release_owned_mouse_button_for_shutdown()
        )

    assert result.success
    release.assert_not_called()

    assert (
        state_store.snapshot().status
        == BODY_BUTTON_CLEAR
    )


def test_held_state_uses_exact_release(
    state_store,
):

    state_store._record_press_success(
        "left"
    )

    with patch(
        "app.tools.computer_tools."
        "pyautogui.mouseUp"
    ) as mouse_up:

        result = (
            release_owned_mouse_button_for_shutdown()
        )

    assert result.success

    mouse_up.assert_called_once_with(
        button="left",
    )

    state = state_store.snapshot()

    assert (
        state.status
        == BODY_BUTTON_CLEAR
    )

    assert state.button is None


def test_unknown_state_uses_exact_recovery_release(
    state_store,
):

    state_store._record_uncertain(
        "middle"
    )

    with patch(
        "app.tools.computer_tools."
        "pyautogui.mouseUp"
    ) as mouse_up:

        result = (
            release_owned_mouse_button_for_shutdown()
        )

    assert result.success

    mouse_up.assert_called_once_with(
        button="middle",
    )

    assert (
        state_store.snapshot().status
        == BODY_BUTTON_CLEAR
    )


def test_failed_release_remains_unknown(
    state_store,
):

    state_store._record_press_success(
        "right"
    )

    with patch(
        "app.tools.computer_tools."
        "pyautogui.mouseUp",
        side_effect=RuntimeError(
            "release failed"
        ),
    ):

        result = (
            release_owned_mouse_button_for_shutdown()
        )

    assert not result.success

    state = state_store.snapshot()

    assert (
        state.status
        == BODY_BUTTON_UNKNOWN
    )

    assert state.button == "right"


def test_keyboard_interrupt_is_reported_after_fail_closed_state(
    state_store,
):

    state_store._record_press_success(
        "left"
    )

    with patch(
        "app.tools.computer_tools."
        "pyautogui.mouseUp",
        side_effect=KeyboardInterrupt(),
    ):

        result = (
            release_owned_mouse_button_for_shutdown()
        )

    assert not result.success

    assert (
        "KeyboardInterrupt"
        in result.error
    )

    state = state_store.snapshot()

    assert (
        state.status
        == BODY_BUTTON_UNKNOWN
    )

    assert state.button == "left"


def test_lifecycle_never_directly_mutates_body_state():

    source = inspect.getsource(
        release_owned_mouse_button_for_shutdown
    )

    for forbidden in (
        "_record_press_success",
        "_record_release_success",
        "_record_uncertain",
        "pyautogui.",
        "mouseDown",
        "mouseUp",
    ):
        assert forbidden not in source

    assert (
        "release_mouse()"
        in source
    )


def test_gui_runtime_has_explicit_shutdown():

    source = (
        Path(__file__)
        .with_name(
            "gui_runtime.py"
        )
        .read_text()
    )

    tree = ast.parse(
        source
    )

    runtime_class = next(
        node
        for node in tree.body
        if (
            isinstance(
                node,
                ast.ClassDef,
            )
            and node.name
            == "KumaGUIRuntime"
        )
    )

    methods = {
        node.name: node
        for node in runtime_class.body
        if isinstance(
            node,
            ast.FunctionDef,
        )
    }

    assert "shutdown" in methods

    shutdown_source = (
        ast.get_source_segment(
            source,
            methods["shutdown"],
        )
        or ""
    )

    assert (
        "release_owned_mouse_button_for_shutdown"
        in shutdown_source
    )


def test_cli_main_has_finally_cleanup():

    source = (
        Path(__file__)
        .with_name(
            "kuma_runtime.py"
        )
        .read_text()
    )

    tree = ast.parse(
        source
    )

    main = next(
        node
        for node in tree.body
        if (
            isinstance(
                node,
                ast.FunctionDef,
            )
            and node.name == "main"
        )
    )

    matched = False

    for node in ast.walk(
        main
    ):

        if (
            isinstance(
                node,
                ast.Try,
            )
            and node.finalbody
        ):

            final_source = "\n".join(
                ast.get_source_segment(
                    source,
                    item,
                )
                or ""
                for item in node.finalbody
            )

            if (
                "release_owned_mouse_button_for_shutdown"
                in final_source
            ):
                matched = True
                break

    assert matched


def _close_event_source():

    root = (
        Path(__file__)
        .parents[2]
    )

    source = (
        root
        / "app"
        / "ui"
        / "window.py"
    ).read_text()

    start = source.index(
        "    def closeEvent("
    )

    end = source.index(
        "\n        # =========================================================\n"
        "# APPLICATION ENTRY POINT",
        start,
    )

    return source[
        start:end
    ]


def test_gui_close_waits_before_cleanup():

    source = (
        _close_event_source()
    )

    assert (
        source.index(
            "worker.wait(1000)"
        )
        <
        source.index(
            "runtime.shutdown()"
        )
        <
        source.index(
            "event.accept()"
        )
    )


def test_gui_close_failure_warns_and_ignores_close():

    source = (
        _close_event_source()
    )

    cleanup = source.index(
        "runtime.shutdown()"
    )

    warning = source.index(
        "QMessageBox.warning(",
        cleanup,
    )

    ignore = source.index(
        "event.ignore()",
        cleanup,
    )

    assert (
        cleanup
        < warning
        < ignore
    )
