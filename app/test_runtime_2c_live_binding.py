from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from app.runtime_correlation import (
    KumaRuntimeCorrelation,
    RuntimeTurnEndKind,
)
from app.runtime_live_binding import (
    LIVE_TRACE_AUTHORITY_NONE,
    KumaRuntimeLiveTraceBinding,
)
from app.runtime_trace import KumaRuntimeTrace


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "app/runtime_live_binding.py"
GUI_RUNTIME = ROOT / "app/agent/gui_runtime.py"
AGENT = ROOT / "app/agent/kuma_agent.py"
INTEGRATED = ROOT / "app/agent/integrated_cognitive_loop.py"
WINDOW = ROOT / "app/ui/window.py"


def make_pair():
    ticks = iter((100, 200, 300, 400, 500, 600, 700, 800))
    trace_ids = iter(("trace-a", "trace-b"))
    turn_ids = iter(("turn-a", "turn-b"))

    trace = KumaRuntimeTrace(
        clock_ns=lambda: next(ticks),
        trace_id_factory=lambda: next(trace_ids),
    )
    correlation = KumaRuntimeCorrelation(
        trace=trace,
        session_id_factory=lambda: "session-a",
        turn_id_factory=lambda: next(turn_ids),
    )
    binding = KumaRuntimeLiveTraceBinding(
        correlation=correlation
    )
    return binding, correlation


def imported_modules(path):
    tree = ast.parse(
        path.read_text(),
        filename=str(path),
    )
    result = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            result.add(node.module)
    return result


def test_authority_is_none():
    binding, _ = make_pair()
    assert LIVE_TRACE_AUTHORITY_NONE == "NONE"
    assert binding.authority == "NONE"


def test_run_signature_has_no_payload_inputs():
    assert tuple(
        inspect.signature(
            KumaRuntimeLiveTraceBinding.run
        ).parameters
    ) == ("self", "operation")


def test_success_runs_once_and_returns_exact_value():
    binding, _ = make_pair()
    calls = []
    result = binding.run(
        lambda: calls.append("ran") or "private-result"
    )
    assert result == "private-result"
    assert calls == ["ran"]


def test_success_event_sequence():
    binding, correlation = make_pair()
    binding.run(lambda: "private-result")
    events = binding.events()
    assert [e.event_kind for e in events] == [
        "turn.started",
        "agent.run.started",
        "agent.run.returned",
        "turn.ended",
    ]
    assert [e.stage for e in events] == [
        "correlation",
        "runtime",
        "runtime",
        "correlation",
    ]
    assert correlation.last_closure.end_kind is RuntimeTurnEndKind.RESPONSE
    assert correlation.active_turn is None


def test_success_payload_never_enters_trace():
    binding, _ = make_pair()
    marker = "private-result-payload"
    assert binding.run(lambda: marker) == marker
    assert marker not in repr(binding.events())


def test_error_preserves_exception_and_closes_error():
    binding, correlation = make_pair()
    error = RuntimeError("private-exception-payload")

    def operation():
        raise error

    with pytest.raises(RuntimeError) as captured:
        binding.run(operation)

    assert captured.value is error
    assert correlation.last_closure.end_kind is RuntimeTurnEndKind.ERROR
    assert [e.event_kind for e in binding.events()] == [
        "turn.started",
        "agent.run.started",
        "agent.run.raised",
        "turn.ended",
    ]
    assert "private-exception-payload" not in repr(binding.events())


def test_trace_failure_never_denies_operation():
    binding, _ = make_pair()
    binding.close()
    calls = []
    result = binding.run(
        lambda: calls.append("ran") or "ok"
    )
    assert result == "ok"
    assert calls == ["ran"]


def test_close_cancels_active_turn():
    binding, correlation = make_pair()
    active = correlation.begin_turn()
    closure = binding.close()
    assert closure.context is active
    assert closure.end_kind is RuntimeTurnEndKind.CANCELLED


def test_all_events_authority_none():
    binding, _ = make_pair()
    binding.run(lambda: "ok")
    assert all(
        event.authority == "NONE"
        for event in binding.events()
    )


def test_metadata_is_structural_only():
    binding, _ = make_pair()
    binding.run(lambda: "ok")
    for event in binding.events():
        keys = set(dict(event.metadata))
        assert keys <= {
            "session.id",
            "turn.id",
            "turn.index",
            "turn.end_kind",
        }


def test_two_turns_share_session_but_not_turn_or_trace():
    binding, _ = make_pair()
    binding.run(lambda: "one")
    binding.run(lambda: "two")
    events = binding.events()
    session_ids = {
        dict(e.metadata)["session.id"]
        for e in events
    }
    turn_ids = {
        dict(e.metadata)["turn.id"]
        for e in events
    }
    trace_ids = {
        e.trace_id
        for e in events
    }
    assert session_ids == {"session-a"}
    assert turn_ids == {"turn-a", "turn-b"}
    assert trace_ids == {"trace-a", "trace-b"}


def test_live_binding_imports_only_runtime_correlation_inside_kuma():
    app_imports = {
        value
        for value in imported_modules(MODULE)
        if value.startswith("app.")
    }
    assert app_imports == {
        "app.runtime_correlation"
    }


def test_live_binding_has_no_network_persistence_or_background_runtime():
    imports = imported_modules(MODULE)
    roots = {
        value.split(".", 1)[0]
        for value in imports
    }
    assert roots.isdisjoint({
        "requests",
        "httpx",
        "urllib",
        "socket",
        "aiohttp",
        "websockets",
        "sqlite3",
        "pathlib",
        "tempfile",
        "shelve",
        "subprocess",
        "threading",
        "asyncio",
    })
    text = MODULE.read_text()
    for forbidden in (
        "while True",
        "Thread(",
        "QThread",
        "QTimer",
        "request_confirmation(",
        "register_tool(",
        ".execute(",
        "ask_model(",
        "generate_content(",
    ):
        assert forbidden not in text


def test_gui_runtime_preserves_runtime_v2_owner_under_integration_v2_owner():
    text = GUI_RUNTIME.read_text()
    assert "KumaRuntimeV2LiveOwner" in text
    assert text.count("KumaRuntimeV2LiveOwner()") == 1
    assert "KumaIntegrationV2LiveTurnOwner" in text
    assert text.count("KumaIntegrationV2LiveTurnOwner(") == 1
    assert "self._integration_v2_owner.run(" in text
    assert "self._runtime_v2_owner.run(" not in text
    assert "self.kuma.run(" in text
    assert "prepared_realtime_turn=prepared_realtime_turn" in text
    assert "KumaRuntimeLiveTraceBinding" not in text


def test_gui_runtime_exposes_bounded_trace_read():
    text = GUI_RUNTIME.read_text()
    assert "def runtime_trace_events(" in text
    assert "self._runtime_v2_owner.events()" in text


def test_gui_shutdown_preserves_cleanup_and_closes_runtime_owner():
    text = GUI_RUNTIME.read_text()
    start = text.index("    def shutdown(")
    block = text[start:]
    assert "release_owned_mouse_button_for_shutdown()" in block
    assert "finally:" in block
    assert "self._runtime_v2_owner.close()" in block


def test_frozen_agent_not_instrumented():
    assert "runtime_live_binding" not in AGENT.read_text()


def test_frozen_integrated_loop_not_instrumented():
    assert "runtime_live_binding" not in INTEGRATED.read_text()


def test_frozen_window_not_instrumented():
    assert "runtime_live_binding" not in WINDOW.read_text()
