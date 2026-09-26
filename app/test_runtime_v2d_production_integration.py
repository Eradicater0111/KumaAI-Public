from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GUI = ROOT / "app/agent/gui_runtime.py"
CLI = ROOT / "app/agent/kuma_runtime.py"
OWNER = ROOT / "app/runtime_v2_live_owner.py"


def imported_from(path):
    tree = ast.parse(path.read_text(), filename=str(path))
    result = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            result.setdefault(node.module, set()).update(
                alias.name for alias in node.names
            )
    return result


def function_source(path, name):
    source = path.read_text()
    tree = ast.parse(source, filename=str(path))
    node = next(
        item
        for item in tree.body
        if isinstance(item, ast.FunctionDef) and item.name == name
    )
    return ast.get_source_segment(source, node) or ""


def test_gui_preserves_runtime_v2_owner_under_integration_v2_turn_owner():
    text = GUI.read_text()
    imports = imported_from(GUI)

    assert imports["app.runtime_v2_live_owner"] == {
        "KumaRuntimeV2LiveOwner"
    }
    assert imports["app.integration_v2_live_turn_owner"] == {
        "KumaIntegrationV2LiveTurnOwner"
    }
    assert imports["app.integration_v2_production_policy"] == {
        "PRODUCTION_REALTIME_TRIGGER_POLICY"
    }
    assert "app.runtime_live_binding" not in imports
    assert text.count("KumaRuntimeV2LiveOwner()") == 1
    assert text.count("KumaIntegrationV2LiveTurnOwner(") == 1
    assert "self._integration_v2_owner.run(" in text
    assert "self._runtime_v2_owner.run(" not in text
    assert "self.kuma.run(" in text
    assert "prepared_realtime_turn=prepared_realtime_turn" in text
    assert "RuntimeInvocation" not in text


def test_gui_pipeline_observer_uses_same_runtime_v2_owner():
    text = GUI.read_text()
    assert (
        "self._runtime_v2_owner.observe_pipeline_event"
        in text
    )
    assert "self._runtime_v2_owner.events()" in text
    assert "self._runtime_v2_owner.close()" in text


def test_gui_does_not_acquire_or_admit_realtime_v2():
    text = GUI.read_text()
    for forbidden in (
        "admit_realtime_observation",
        "pending_signals",
        "drain_signals",
        "minimum_level",
        "minimum_score",
        "RealtimeSignal",
    ):
        assert forbidden not in text


def test_cli_preserves_runtime_v2_owner_under_integration_v2_turn_owner():
    text = CLI.read_text()
    imports = imported_from(CLI)

    assert imports["app.runtime_v2_live_owner"] == {
        "KumaRuntimeV2LiveOwner"
    }
    assert imports["app.integration_v2_live_turn_owner"] == {
        "KumaIntegrationV2LiveTurnOwner"
    }
    assert imports["app.integration_v2_production_policy"] == {
        "PRODUCTION_REALTIME_TRIGGER_POLICY"
    }
    assert text.count("KumaRuntimeV2LiveOwner()") == 1
    assert text.count("KumaIntegrationV2LiveTurnOwner(") == 1
    assert "integration_owner.run(" in text
    assert "runtime_owner.run(" not in text
    assert "lambda prepared_realtime_turn: kuma.run(" in text
    assert "prepared_realtime_turn=(" in text
    assert "runtime_owner.observe_pipeline_event" in text
    assert "runtime_owner.close()" in text


def test_cli_runtime_owner_close_is_in_finally():
    source = function_source(CLI, "main")
    tree = ast.parse(source)

    closes = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "close"
    ]
    assert len(closes) == 1
    assert "finally:\n            runtime_owner.close()" in source


def test_create_kuma_remains_agent_factory_not_runtime_turn_owner():
    source = function_source(CLI, "create_kuma")
    for forbidden in (
        "KumaRuntimeV2LiveOwner",
        "RuntimeInvocation",
        "KumaRuntimeInvocationDispatcher",
        "runtime_owner.run(",
    ):
        assert forbidden not in source


def test_cli_does_not_admit_realtime_v2_or_select_signals():
    source = function_source(CLI, "main")
    for forbidden in (
        "admit_realtime_observation",
        "pending_signals",
        "drain_signals",
        "minimum_level",
        "minimum_score",
    ):
        assert forbidden not in source


def test_runtime_v2d_is_only_external_private_plain_binding_bridge():
    allowed = {
        "app/runtime_v2_dispatch.py",
        "app/runtime_v2_live_owner.py",
    }

    hits = set()

    for path in sorted((ROOT / "app").rglob("*.py")):
        if path.name.startswith("test_"):
            continue

        relative = path.relative_to(ROOT).as_posix()
        if "_plain_binding" in path.read_text():
            hits.add(relative)

    assert hits == allowed


def test_runtime_v2d_owner_import_surface_is_exact():
    assert imported_from(OWNER) == {
        "__future__": {"annotations"},
        "typing": {"Callable", "TypeVar"},
        "app.runtime_v2_dispatch": {
            "KumaRuntimeInvocationDispatcher",
        },
        "app.runtime_v2_invocation": {
            "RuntimeInvocation",
        },
    }


def test_production_paths_do_not_construct_frozen_v1_binding_directly():
    for path in (GUI, CLI):
        text = path.read_text()
        assert "KumaRuntimeLiveTraceBinding" not in text
        assert "KumaRuntimeLiveTraceBinding()" not in text


def test_runtime_v2d_integration_boundary_markers_are_explicit():
    text = OWNER.read_text()
    for marker in (
        "OWNER != ADMISSION",
        "OWNER != SCHEDULER",
        "OWNER != PERMISSION",
        "OWNER != EXECUTION AUTHORITY",
        "PIPELINE OBSERVATION != CONTROL",
        "OBSERVATION != INVOCATION",
        "AUTHORITY: NONE",
    ):
        assert marker in text
