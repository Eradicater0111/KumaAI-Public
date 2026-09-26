from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GUI = ROOT / "app/agent/gui_runtime.py"
CLI = ROOT / "app/agent/kuma_runtime.py"
AGENT = ROOT / "app/agent/kuma_agent.py"
LIVE_OWNER = ROOT / "app/integration_v2_live_turn_owner.py"
POLICY = ROOT / "app/integration_v2_production_policy.py"


def imported_from(
    path,
):
    tree = ast.parse(
        path.read_text(),
        filename=str(path),
    )

    result = {}

    for node in ast.walk(
        tree
    ):
        if (
            isinstance(
                node,
                ast.ImportFrom,
            )
            and node.module
        ):
            result.setdefault(
                node.module,
                set(),
            ).update(
                alias.name
                for alias in node.names
            )

    return result


def function_source(
    path,
    name,
):
    source = path.read_text()
    tree = ast.parse(
        source,
        filename=str(path),
    )

    node = next(
        item
        for item in tree.body
        if (
            isinstance(
                item,
                ast.FunctionDef,
            )
            and item.name == name
        )
    )

    return ast.get_source_segment(
        source,
        node,
    ) or ""


def test_gui_constructs_one_runtime_owner_and_one_integration_owner():
    source = GUI.read_text()

    assert source.count(
        "KumaRuntimeV2LiveOwner()"
    ) == 1

    assert source.count(
        "KumaIntegrationV2LiveTurnOwner("
    ) == 1

    assert (
        "runtime_owner=self._runtime_v2_owner"
        in source
    )

    assert (
        "realtime_runtime=self.kuma.realtime_runtime"
        in source
    )

    assert (
        "PRODUCTION_REALTIME_TRIGGER_POLICY"
        in source
    )


def test_gui_invokes_integration_owner_and_passes_exact_preflight_to_agent():
    source = GUI.read_text()

    assert (
        "self._integration_v2_owner.run("
        in source
    )

    assert (
        "self._runtime_v2_owner.run("
        not in source
    )

    assert (
        "lambda prepared_realtime_turn: self.kuma.run("
        in source
    )

    assert (
        "prepared_realtime_turn=prepared_realtime_turn"
        in source
    )


def test_gui_runtime_v2d_remains_trace_observer_events_and_close_owner():
    source = GUI.read_text()

    assert (
        "self._runtime_v2_owner.observe_pipeline_event"
        in source
    )

    assert (
        "self._runtime_v2_owner.events()"
        in source
    )

    assert (
        "self._runtime_v2_owner.close()"
        in source
    )

    assert (
        "self._integration_v2_owner.close("
        not in source
    )

    assert (
        "self._integration_v2_owner.events("
        not in source
    )


def test_cli_constructs_one_runtime_owner_and_one_integration_owner():
    source = function_source(
        CLI,
        "main",
    )

    assert source.count(
        "KumaRuntimeV2LiveOwner()"
    ) == 1

    assert source.count(
        "KumaIntegrationV2LiveTurnOwner("
    ) == 1

    assert "runtime_owner=runtime_owner" in source
    assert "realtime_runtime=kuma.realtime_runtime" in source
    assert "PRODUCTION_REALTIME_TRIGGER_POLICY" in source


def test_cli_invokes_integration_owner_and_passes_exact_preflight_to_agent():
    source = function_source(
        CLI,
        "main",
    )

    assert "integration_owner.run(" in source
    assert "runtime_owner.run(" not in source

    assert (
        "lambda prepared_realtime_turn: kuma.run("
        in source
    )

    assert "prepared_realtime_turn=(" in source


def test_cli_runtime_v2d_remains_observer_and_close_owner():
    source = function_source(
        CLI,
        "main",
    )

    assert (
        "runtime_owner.observe_pipeline_event"
        in source
    )

    assert (
        "runtime_owner.close()"
        in source
    )

    assert "integration_owner.close(" not in source


def test_gui_cli_share_exact_same_central_policy_symbol():
    for path in (
        GUI,
        CLI,
    ):
        imports = imported_from(
            path
        )

        assert (
            imports[
                "app.integration_v2_production_policy"
            ]
            == {
                "PRODUCTION_REALTIME_TRIGGER_POLICY"
            }
        )


def test_gui_cli_do_not_touch_realtime_queue_or_selection_primitives():
    for path in (
        GUI,
        CLI,
    ):
        source = path.read_text()

        for forbidden in (
            "pending_signals(",
            "drain_signals(",
            "prepare_realtime_turn(",
            "propose_runtime_trigger(",
            "evaluate_trigger_eligibility(",
            "admit_realtime_observation(",
            "create_trigger_request(",
            "observe_trigger_request(",
        ):
            assert forbidden not in source


def test_gui_cli_do_not_duplicate_threshold_values():
    for path in (
        GUI,
        CLI,
    ):
        source = path.read_text()

        assert "minimum_level" not in source
        assert "minimum_score" not in source
        assert "RealtimeRelevanceLevel.HIGH" not in source
        assert "0.80" not in source


def test_create_kuma_remains_agent_factory_not_turn_composition_owner():
    source = function_source(
        CLI,
        "create_kuma",
    )

    assert "KumaIntegrationV2LiveTurnOwner" not in source
    assert "PRODUCTION_REALTIME_TRIGGER_POLICY" not in source


def test_agent_frozen_v2e_prepared_seam_remains_present():
    source = AGENT.read_text()

    assert "prepared_realtime_turn=None" in source
    assert "resolve_prepared_realtime_signals" in source
    assert source.count(
        "realtime_runtime.tick()"
    ) == 1
    assert source.count(
        "realtime_runtime.pending_signals()"
    ) == 1


def test_integration_owner_and_policy_remain_zero_authority():
    live = LIVE_OWNER.read_text()
    policy = POLICY.read_text()

    assert "AUTHORITY: NONE" in live
    assert "AUTHORITY: NONE" in policy
    assert "INTEGRATION OWNER != EXECUTION AUTHORITY" in live
    assert "TRACE ELIGIBILITY != EXECUTION" in policy
