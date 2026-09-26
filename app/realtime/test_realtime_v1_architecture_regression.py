from __future__ import annotations

import ast
from dataclasses import fields
import inspect
from pathlib import Path

from app.realtime.change_detection import (
    REALTIME_SIGNAL_AUTHORITY_NONE,
    RealtimeSignal,
)
from app.realtime.contracts import (
    REALTIME_AUTHORITY_NONE,
    RealtimeEvent,
    RealtimeFact,
)
from app.realtime.event_bus import (
    RealtimeEventBus,
)
from app.realtime.runtime import (
    RealtimeRuntime,
)
from app.realtime.scheduler import (
    RealtimeScheduler,
)


ROOT = Path(__file__).resolve().parents[2]

REALTIME = ROOT / "app/realtime"

CONTRACTS = REALTIME / "contracts.py"
EVENT_BUS = REALTIME / "event_bus.py"
STORE = REALTIME / "store.py"
LOCATION = REALTIME / "location_adapter.py"
SCHEDULER = REALTIME / "scheduler.py"
WEATHER = REALTIME / "weather_provider.py"
CHANGE = REALTIME / "change_detection.py"
RUNTIME = REALTIME / "runtime.py"
WEATHER_RENDER = REALTIME / "weather_render.py"
INIT = REALTIME / "__init__.py"

KUMA_RUNTIME = (
    ROOT
    / "app/agent/kuma_runtime.py"
)

KUMA_AGENT = (
    ROOT
    / "app/agent/kuma_agent.py"
)

PROACTIVE = (
    ROOT
    / "app/agent/proactive_attention.py"
)

SURFACING = (
    ROOT
    / "app/agent/attention_surfacing.py"
)

INTEGRATED = (
    ROOT
    / "app/agent/integrated_cognitive_loop.py"
)


REALTIME_PRODUCTION = (
    INIT,
    CONTRACTS,
    EVENT_BUS,
    STORE,
    LOCATION,
    SCHEDULER,
    WEATHER,
    CHANGE,
    RUNTIME,
    WEATHER_RENDER,
)


def _imports(
    path: Path,
) -> set[str]:
    tree = ast.parse(
        path.read_text(),
        filename=str(path),
    )

    result = set()

    for node in ast.walk(
        tree
    ):
        if isinstance(
            node,
            ast.Import,
        ):
            result.update(
                alias.name
                for alias in node.names
            )

        elif (
            isinstance(
                node,
                ast.ImportFrom,
            )
            and node.module
        ):
            result.add(
                node.module
            )

    return result


def _field_names(
    cls,
) -> set[str]:
    return {
        item.name
        for item in fields(
            cls
        )
    }


def _field(
    cls,
    name,
):
    for item in fields(
        cls
    ):
        if item.name == name:
            return item

    raise AssertionError(
        f"missing field: {name}"
    )


def test_realtime_v1_phase_tests_exist():
    expected = (
        "test_realtime_1a_core.py",
        "test_realtime_1b_location_adapter.py",
        "test_realtime_1c_scheduler.py",
        "test_realtime_1d_weather_provider.py",
        "test_realtime_1e_change_detection.py",
        "test_realtime_1f_runtime_integration.py",
    )

    for name in expected:
        assert (
            REALTIME / name
        ).is_file()


def test_realtime_authority_constants_are_none():
    assert (
        REALTIME_AUTHORITY_NONE
        == "NONE"
    )

    assert (
        REALTIME_SIGNAL_AUTHORITY_NONE
        == "NONE"
    )


def test_realtime_fact_authority_defaults_none():
    assert (
        _field(
            RealtimeFact,
            "authority",
        ).default
        == "NONE"
    )


def test_realtime_signal_authority_defaults_none():
    assert (
        _field(
            RealtimeSignal,
            "authority",
        ).default
        == "NONE"
    )


def test_realtime_event_carries_no_independent_authority():
    names = _field_names(
        RealtimeEvent
    )

    assert names == {
        "event_type",
        "fact",
        "previous_fact",
    }


def test_realtime_structures_expose_no_execution_fields():
    forbidden = {
        "tool",
        "tool_name",
        "arguments",
        "command",
        "permission",
        "confirmation",
        "execute",
        "executor",
        "callback",
        "mission",
        "retry",
        "resume",
    }

    for cls in (
        RealtimeFact,
        RealtimeEvent,
        RealtimeSignal,
    ):
        assert (
            _field_names(cls)
            .isdisjoint(
                forbidden
            )
        )


def test_realtime_modules_do_not_import_agent_authority_owners():
    forbidden = (
        "app.agent",
        "app.tools",
    )

    for path in REALTIME_PRODUCTION:
        for module in _imports(
            path
        ):
            assert not module.startswith(
                forbidden
            ), (
                path,
                module,
            )


def test_realtime_dependency_direction_does_not_point_back_to_kuma_runtime():
    for path in REALTIME_PRODUCTION:
        imported = _imports(
            path
        )

        assert (
            "app.agent.kuma_runtime"
            not in imported
        )

        assert (
            "app.agent.kuma_agent"
            not in imported
        )


def test_non_weather_realtime_modules_have_no_network_dependency():
    network_roots = {
        "httpx",
        "requests",
        "urllib",
        "socket",
        "aiohttp",
        "websockets",
    }

    for path in REALTIME_PRODUCTION:
        if path == WEATHER:
            continue

        roots = {
            value.split(
                ".",
                1,
            )[0]
            for value in _imports(
                path
            )
        }

        assert roots.isdisjoint(
            network_roots
        ), path


def test_realtime_modules_have_no_database_persistence_dependency():
    for path in REALTIME_PRODUCTION:
        roots = {
            value.split(
                ".",
                1,
            )[0]
            for value in _imports(
                path
            )
        }

        assert roots.isdisjoint(
            {
                "sqlite3",
                "sqlalchemy",
                "shelve",
            }
        ), path


def test_realtime_subsystem_has_no_background_execution_loop():
    for path in REALTIME_PRODUCTION:
        source = path.read_text()

        for forbidden in (
            "threading.Thread",
            "Thread(",
            "asyncio.create_task",
            "create_task(",
            "while True",
            "run_forever(",
            "Timer(",
            "daemon=",
        ):
            assert (
                forbidden
                not in source
            ), (
                path,
                forbidden,
            )


def test_scheduler_documentation_matches_realtime_1f_binding():
    doc = inspect.getdoc(
        RealtimeScheduler
    )

    assert doc is not None

    assert (
        "REALTIME-1F"
        in doc
    )

    assert (
        "caller-owned KUMA user-turn"
        in doc
    )

    assert (
        "USER-TURN TICK != AUTONOMOUS INVOCATION"
        in doc
    )

    assert (
        "SCHEDULE DUE != PERMISSION"
        in doc
    )

    assert (
        "future runtime layer"
        not in doc.lower()
    )


def test_scheduler_tick_requires_explicit_time():
    assert tuple(
        inspect.signature(
            RealtimeScheduler.tick
        ).parameters
    ) == (
        "self",
        "at",
    )


def test_scheduler_tick_does_not_refresh_weather_directly():
    source = inspect.getsource(
        RealtimeScheduler.tick
    )

    assert (
        "weather_provider"
        not in source
    )

    assert (
        "refresh_weather"
        not in source
    )

    assert (
        "app.agent"
        not in source
    )


def test_scheduler_is_fact_refresh_boundary_not_tool_boundary():
    source = SCHEDULER.read_text()

    for marker in (
        "callbacks only return RealtimeFact objects",
        "scheduler cannot invoke KUMA tools",
        "facts retain permanent AUTHORITY: NONE",
        "callback failures are isolated per job",
    ):
        assert marker in source


def test_realtime_runtime_tick_is_payload_free():
    assert tuple(
        inspect.signature(
            RealtimeRuntime.tick
        ).parameters
    ) == (
        "self",
    )


def test_realtime_runtime_tick_only_advances_scheduler():
    source = inspect.getsource(
        RealtimeRuntime.tick
    )

    assert (
        "self.scheduler.tick("
        in source
    )

    assert (
        "self.weather_provider"
        not in source
    )

    assert (
        "refresh_weather"
        not in source
    )

    assert (
        "pending_signals"
        not in source
    )

    assert (
        "drain_signals"
        not in source
    )


def test_current_weather_refresh_is_explicit_only():
    doc = inspect.getdoc(
        RealtimeRuntime.refresh_weather
    )

    assert doc is not None

    assert (
        "Explicit read-only weather refresh"
        in doc
    )

    assert (
        "never invokes this automatically"
        in doc
    )


def test_daily_weather_refresh_is_explicit_only():
    doc = inspect.getdoc(
        RealtimeRuntime.refresh_weather_daily
    )

    assert doc is not None

    assert (
        "Explicit read-only daily weather refresh"
        in doc
    )

    assert (
        "never invoked autonomously"
        in doc
    )


def test_pending_signals_is_non_destructive_snapshot():
    source = inspect.getsource(
        RealtimeRuntime.pending_signals
    )

    assert (
        "tuple("
        in source
    )

    assert (
        ".clear()"
        not in source
    )


def test_signal_drain_is_separate_explicit_surface():
    source = inspect.getsource(
        RealtimeRuntime.drain_signals
    )

    assert (
        ".clear()"
        in source
    )


def test_event_bus_is_synchronous_notification_not_execution():
    doc = inspect.getdoc(
        RealtimeEventBus
    )

    assert doc is not None

    assert (
        "Synchronous event bus"
        in doc
    )

    assert (
        "does not execute KUMA tools"
        in doc
    )

    assert (
        "grant action authority"
        in doc
    )


def test_agent_has_exactly_one_user_turn_tick_surface():
    source = KUMA_AGENT.read_text()

    assert (
        source.count(
            "realtime_runtime.tick()"
        )
        == 1
    )


def test_agent_has_exactly_one_pending_signal_snapshot_surface():
    source = KUMA_AGENT.read_text()

    assert (
        source.count(
            "realtime_runtime.pending_signals()"
        )
        == 1
    )


def test_agent_never_drains_realtime_signals():
    source = KUMA_AGENT.read_text()

    assert (
        "realtime_runtime.drain_signals()"
        not in source
    )


def test_agent_tick_occurs_before_attention_snapshot():
    source = KUMA_AGENT.read_text()

    tick = source.index(
        "realtime_runtime.tick()"
    )

    pending = source.index(
        "realtime_runtime.pending_signals()"
    )

    assert tick < pending


def test_agent_realtime_tick_failure_is_isolated():
    source = KUMA_AGENT.read_text()

    call = source.index(
        "realtime_runtime.tick()"
    )

    marker = source.index(
        "KUMA REALTIME → tick isolated:",
        call,
    )

    assert call < marker


def test_agent_current_weather_refresh_remains_explicit_request_path():
    source = KUMA_AGENT.read_text()

    assert (
        source.count(
            "realtime_runtime.refresh_weather()"
        )
        == 1
    )

    assert (
        source.count(
            "realtime_runtime.refresh_weather_daily("
        )
        == 1
    )


def test_proactive_attention_does_not_acquire_realtime_state():
    source = PROACTIVE.read_text()

    for forbidden in (
        "realtime_runtime.tick(",
        "pending_signals(",
        "drain_signals(",
        "refresh_weather(",
        "refresh_weather_daily(",
    ):
        assert forbidden not in source


def test_attention_surfacing_does_not_acquire_realtime_state():
    source = SURFACING.read_text()

    for forbidden in (
        "realtime_runtime.tick(",
        "pending_signals(",
        "drain_signals(",
        "refresh_weather(",
        "refresh_weather_daily(",
    ):
        assert forbidden not in source


def test_integrated_loop_does_not_acquire_realtime_state():
    source = INTEGRATED.read_text()

    for forbidden in (
        "realtime_runtime.tick(",
        "pending_signals(",
        "drain_signals(",
        "refresh_weather(",
        "refresh_weather_daily(",
    ):
        assert forbidden not in source


def test_realtime_v1_is_consumed_one_way_by_kuma_runtime():
    tree = ast.parse(
        KUMA_RUNTIME.read_text(),
        filename=str(KUMA_RUNTIME),
    )

    imported_runtime_names = set()

    for node in ast.walk(
        tree
    ):
        if (
            isinstance(
                node,
                ast.ImportFrom,
            )
            and node.module
            == "app.realtime.runtime"
        ):
            imported_runtime_names.update(
                alias.asname
                or alias.name
                for alias in node.names
            )

    assert imported_runtime_names, (
        "KumaRuntime must consume the Realtime runtime boundary."
    )

    referenced_names = {
        node.id
        for node in ast.walk(
            tree
        )
        if isinstance(
            node,
            ast.Name,
        )
    }

    assert (
        imported_runtime_names
        & referenced_names
    ), (
        "The imported Realtime runtime boundary must be referenced."
    )

    for path in REALTIME_PRODUCTION:
        imported = _imports(
            path
        )

        assert (
            "app.agent.kuma_runtime"
            not in imported
        )

        assert (
            "app.agent.kuma_agent"
            not in imported
        )


def test_realtime_1f_guard_tests_remain_present():
    source = (
        REALTIME
        / "test_realtime_1f_runtime_integration.py"
    ).read_text()

    expected = (
        "test_passive_location_ingestion",
        "test_address_mode_is_not_ingested",
        "test_location_change_queues_high_zero_authority_signal",
        "test_tick_does_not_call_weather_provider",
        "test_weather_refresh_is_explicit_only",
        "test_location_permission_unchanged",
        "test_production_location_registration_uses_wrapper",
        "test_agent_has_safe_realtime_tick_hook",
        "test_location_wrapper_never_refreshes_weather",
    )

    for name in expected:
        assert (
            f"def {name}("
            in source
        )


def test_realtime_package_declares_zero_authority_nervous_system():
    source = INIT.read_text()

    assert (
        "REALTIME-1A..1F provide the zero-authority realtime nervous system."
        in source
    )


def test_realtime_v1_boundary_markers_are_explicit():
    sources = "\n".join(
        path.read_text()
        for path in (
            CONTRACTS,
            CHANGE,
            EVENT_BUS,
            SCHEDULER,
            RUNTIME,
            KUMA_AGENT,
            PROACTIVE,
            SURFACING,
            INTEGRATED,
        )
    )

    for marker in (
        "AUTHORITY: NONE",
        "REALTIME SIGNAL != COMMAND",
        "ATTENTION != AUTHORITY",
        "SURFACE != EXECUTE",
    ):
        assert marker in sources


def test_realtime_v1_sources_compile():
    for path in (
        *REALTIME_PRODUCTION,
        KUMA_RUNTIME,
        KUMA_AGENT,
        PROACTIVE,
        SURFACING,
        INTEGRATED,
    ):
        compile(
            path.read_text(),
            str(path),
            "exec",
        )
