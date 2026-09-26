from __future__ import annotations

"""
KUMA REALTIME-2G — Realtime V2 architecture regression.

RealtimeSignal
    ↓
RealtimeTriggerProposal                 [2A]
    ↓
explicit caller-supplied eligibility    [2B]
    ↓
RealtimeTriggerRequest                  [2C]
    ↓
RealtimeTriggerObservation              [2D]
    ↓
[2E intentionally NO-OP]
    ↓
explicit-caller runtime trace recording [2F]
    ↓
STOP

TRIGGER PROPOSAL != COMMAND
ELIGIBILITY != PERMISSION
REQUEST != WAKE
OBSERVATION != DELIVERY
RECORDING != CONTROL
TRACE != AUTHORITY
OBSERVATION != EXECUTION
AUTHORITY: NONE
"""

from dataclasses import fields
import ast
import inspect
from pathlib import Path

from app.realtime.change_detection import (
    RealtimeRelevanceLevel,
    RealtimeSignal,
)
from app.realtime.runtime_trace_adapter import (
    REALTIME_RUNTIME_TRACE_AUTHORITY_NONE,
    record_trigger_observation,
)
from app.realtime.runtime_trigger import (
    REALTIME_TRIGGER_AUTHORITY_NONE,
    RealtimeTriggerProposal,
    propose_runtime_trigger,
)
from app.realtime.trigger_observation import (
    REALTIME_TRIGGER_OBSERVATION_AUTHORITY_NONE,
    RealtimeTriggerObservation,
    RealtimeTriggerObservationStatus,
    observe_trigger_request,
)
from app.realtime.trigger_policy import (
    REALTIME_TRIGGER_POLICY_AUTHORITY_NONE,
    RealtimeTriggerEligibilityDecision,
    RealtimeTriggerEligibilityStatus,
    evaluate_trigger_eligibility,
)
from app.realtime.trigger_request import (
    REALTIME_TRIGGER_REQUEST_AUTHORITY_NONE,
    RealtimeTriggerRequest,
    create_trigger_request,
)
from app.runtime_correlation import (
    CORRELATION_AUTHORITY_NONE,
    KumaRuntimeCorrelation,
    RuntimeTurnCorrelation,
)
from app.runtime_trace import (
    TRACE_AUTHORITY_NONE,
    KumaRuntimeTrace,
    RuntimeTraceEvent,
)


REALTIME_DIR = Path("app/realtime")

PRODUCTION_FILES = (
    REALTIME_DIR / "runtime_trigger.py",
    REALTIME_DIR / "trigger_policy.py",
    REALTIME_DIR / "trigger_request.py",
    REALTIME_DIR / "trigger_observation.py",
    REALTIME_DIR / "runtime_trace_adapter.py",
)

CHAIN_SYMBOLS = {
    "RealtimeTriggerProposal",
    "propose_runtime_trigger",
    "RealtimeTriggerEligibilityDecision",
    "evaluate_trigger_eligibility",
    "RealtimeTriggerRequest",
    "create_trigger_request",
    "RealtimeTriggerObservation",
    "observe_trigger_request",
    "record_trigger_observation",
}


# ============================================================
# REALTIME-2H — EXPLICIT CONSUMER EVOLVABILITY
# ============================================================
#
# The original V2 freeze proved that no external production consumer
# existed at freeze time. That was a point-in-time fact, not a permanent
# architectural prohibition.
#
# Future consumers remain fail-closed: only an exact path + exact frozen
# V2 symbol surface may be admitted here. An allowlisted path is optional;
# its absence is valid. Any unlisted path or extra/missing V2 symbol fails.
#
# ALLOWLIST != AUTHORITY
# EXTERNAL CONSUMER != PERMISSION
# EXTERNAL CONSUMER != EXECUTION
# AUTHORITY: NONE
#
# Runtime-V2A was independently discovered and dry-run proven as the
# narrow public-only first consumer. This allowlist does not create it,
# invoke it, import it, or change production behavior.
# ============================================================

ALLOWED_EXTERNAL_PRODUCTION_REFERENCES = {
    "app/runtime_v2_turn_observation.py": (
        "RealtimeTriggerObservation",
        "record_trigger_observation",
    ),
    "app/integration_realtime_observation_admission.py": (
        "RealtimeTriggerObservation",
        "create_trigger_request",
        "evaluate_trigger_eligibility",
        "observe_trigger_request",
        "propose_runtime_trigger",
    ),
    "app/integration_v2_realtime_turn_preflight.py": (
        "evaluate_trigger_eligibility",
        "propose_runtime_trigger",
    ),
    "app/runtime_v2_invocation.py": (
        "RealtimeTriggerObservation",
    ),
}


def _app_imports(path: Path) -> set[str]:
    tree = ast.parse(
        path.read_text(),
        filename=str(path),
    )

    imports = set()

    for node in ast.walk(tree):
        if (
            isinstance(node, ast.ImportFrom)
            and node.module
            and node.module.startswith("app.")
        ):
            imports.add(node.module)

        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("app."):
                    imports.add(alias.name)

    return imports


def _external_production_references():
    owner_files = set(PRODUCTION_FILES)
    hits = []

    for path in sorted(Path("app").rglob("*.py")):
        if path.name.startswith("test_"):
            continue

        if path in owner_files:
            continue

        try:
            tree = ast.parse(
                path.read_text(),
                filename=str(path),
            )
        except SyntaxError:
            continue

        found = set()

        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Name)
                and node.id in CHAIN_SYMBOLS
            ):
                found.add(node.id)

            elif (
                isinstance(node, ast.Attribute)
                and node.attr in CHAIN_SYMBOLS
            ):
                found.add(node.attr)

            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if alias.name in CHAIN_SYMBOLS:
                        found.add(alias.name)

        if found:
            hits.append(
                (
                    str(path),
                    tuple(sorted(found)),
                )
            )

    return tuple(hits)


def test_v2_candidate_production_files_exist():
    for path in PRODUCTION_FILES:
        assert path.is_file()


def test_v2_has_no_2e_production_module():
    assert not (
        REALTIME_DIR
        / "realtime_2e.py"
    ).exists()

    assert not (
        REALTIME_DIR
        / "trigger_dedup.py"
    ).exists()

    assert not (
        REALTIME_DIR
        / "trigger_mailbox.py"
    ).exists()


def test_v2_authority_constants_remain_none():
    assert REALTIME_TRIGGER_AUTHORITY_NONE == "NONE"
    assert (
        REALTIME_TRIGGER_POLICY_AUTHORITY_NONE
        == "NONE"
    )
    assert (
        REALTIME_TRIGGER_REQUEST_AUTHORITY_NONE
        == "NONE"
    )
    assert (
        REALTIME_TRIGGER_OBSERVATION_AUTHORITY_NONE
        == "NONE"
    )
    assert (
        REALTIME_RUNTIME_TRACE_AUTHORITY_NONE
        == "NONE"
    )
    assert CORRELATION_AUTHORITY_NONE == "NONE"
    assert TRACE_AUTHORITY_NONE == "NONE"


def test_v2_proposal_shape_is_frozen():
    assert tuple(
        item.name
        for item in fields(
            RealtimeTriggerProposal
        )
    ) == (
        "proposal_id",
        "kind",
        "level",
        "score",
        "reason",
        "authority",
    )

    assert tuple(
        inspect.signature(
            propose_runtime_trigger
        ).parameters
    ) == (
        "signal",
    )


def test_v2_eligibility_shape_is_frozen():
    assert tuple(
        item.name
        for item in fields(
            RealtimeTriggerEligibilityDecision
        )
    ) == (
        "proposal_id",
        "status",
        "reason",
        "authority",
    )

    assert tuple(
        item.value
        for item in RealtimeTriggerEligibilityStatus
    ) == (
        "ineligible",
        "eligible",
    )

    signature = inspect.signature(
        evaluate_trigger_eligibility
    )

    assert tuple(
        signature.parameters
    ) == (
        "proposal",
        "minimum_level",
        "minimum_score",
    )

    assert (
        signature.parameters[
            "minimum_level"
        ].kind
        is inspect.Parameter.KEYWORD_ONLY
    )

    assert (
        signature.parameters[
            "minimum_score"
        ].kind
        is inspect.Parameter.KEYWORD_ONLY
    )

    assert (
        signature.parameters[
            "minimum_level"
        ].default
        is inspect.Parameter.empty
    )

    assert (
        signature.parameters[
            "minimum_score"
        ].default
        is inspect.Parameter.empty
    )


def test_v2_request_shape_is_frozen():
    assert tuple(
        item.name
        for item in fields(
            RealtimeTriggerRequest
        )
    ) == (
        "request_id",
        "proposal_id",
        "kind",
        "reason",
        "authority",
    )

    assert tuple(
        inspect.signature(
            create_trigger_request
        ).parameters
    ) == (
        "proposal",
        "decision",
    )


def test_v2_observation_shape_is_frozen():
    assert tuple(
        item.name
        for item in fields(
            RealtimeTriggerObservation
        )
    ) == (
        "observation_id",
        "request_id",
        "proposal_id",
        "kind",
        "status",
        "reason",
        "authority",
    )

    assert tuple(
        item.value
        for item in RealtimeTriggerObservationStatus
    ) == (
        "observed",
    )

    assert tuple(
        inspect.signature(
            observe_trigger_request
        ).parameters
    ) == (
        "request",
    )


def test_v2_trace_adapter_is_explicit_caller_only():
    signature = inspect.signature(
        record_trigger_observation
    )

    assert tuple(
        signature.parameters
    ) == (
        "observation",
        "correlation",
        "turn",
    )

    assert (
        signature.parameters[
            "correlation"
        ].kind
        is inspect.Parameter.KEYWORD_ONLY
    )

    assert (
        signature.parameters[
            "turn"
        ].kind
        is inspect.Parameter.KEYWORD_ONLY
    )


def test_v2_import_direction_2a():
    assert _app_imports(
        REALTIME_DIR
        / "runtime_trigger.py"
    ) == {
        "app.realtime.change_detection",
    }


def test_v2_import_direction_2b():
    assert _app_imports(
        REALTIME_DIR
        / "trigger_policy.py"
    ) == {
        "app.realtime.change_detection",
        "app.realtime.runtime_trigger",
    }


def test_v2_import_direction_2c():
    assert _app_imports(
        REALTIME_DIR
        / "trigger_request.py"
    ) == {
        "app.realtime.runtime_trigger",
        "app.realtime.trigger_policy",
    }


def test_v2_import_direction_2d():
    assert _app_imports(
        REALTIME_DIR
        / "trigger_observation.py"
    ) == {
        "app.realtime.trigger_request",
    }


def test_v2_import_direction_2f():
    assert _app_imports(
        REALTIME_DIR
        / "runtime_trace_adapter.py"
    ) == {
        "app.realtime.trigger_observation",
        "app.runtime_correlation",
        "app.runtime_trace",
    }


def test_v2_runtime_v1_does_not_import_realtime():
    for path in (
        Path("app/runtime_trace.py"),
        Path("app/runtime_correlation.py"),
        Path("app/runtime_live_binding.py"),
        Path("app/runtime_observability.py"),
    ):
        assert not any(
            name.startswith(
                "app.realtime"
            )
            for name in _app_imports(path)
        )


def test_v2_external_production_consumers_are_explicitly_allowlisted():
    for path, symbols in _external_production_references():
        assert path in ALLOWED_EXTERNAL_PRODUCTION_REFERENCES
        assert (
            symbols
            == ALLOWED_EXTERNAL_PRODUCTION_REFERENCES[
                path
            ]
        )


def test_v2_external_consumer_allowlist_is_exact_and_narrow():
    assert (
        ALLOWED_EXTERNAL_PRODUCTION_REFERENCES
        == {
            "app/runtime_v2_turn_observation.py": (
                "RealtimeTriggerObservation",
                "record_trigger_observation",
            ),
            "app/integration_realtime_observation_admission.py": (
                "RealtimeTriggerObservation",
                "create_trigger_request",
                "evaluate_trigger_eligibility",
                "observe_trigger_request",
                "propose_runtime_trigger",
            ),
            "app/integration_v2_realtime_turn_preflight.py": (
                "evaluate_trigger_eligibility",
                "propose_runtime_trigger",
            ),
            "app/runtime_v2_invocation.py": (
                "RealtimeTriggerObservation",
            ),
        }
    )


def test_v2_realtime_does_not_duplicate_attention_seen_state():
    observation_source = (
        REALTIME_DIR
        / "trigger_observation.py"
    ).read_text()

    adapter_source = (
        REALTIME_DIR
        / "runtime_trace_adapter.py"
    ).read_text()

    assert "seen_event_ids" not in observation_source
    assert "remember_seen_event" not in observation_source
    assert "seen_event_ids" not in adapter_source
    assert "remember_seen_event" not in adapter_source
    assert "acknowledged_event_ids" not in adapter_source


def test_v2_attention_seen_state_remains_with_attention_owner():
    attention = Path(
        "app/agent/proactive_attention.py"
    ).read_text()

    surfacing = Path(
        "app/agent/attention_surfacing.py"
    ).read_text()

    assert "seen_event_ids" in attention
    assert "acknowledged_event_ids" in attention
    assert "remember_seen_event" in surfacing


def test_v2_2f_uses_public_runtime_surfaces_only():
    source = (
        REALTIME_DIR
        / "runtime_trace_adapter.py"
    ).read_text()

    assert "correlation.active_turn" in source
    assert "correlation.trace" in source

    for forbidden in (
        "._correlation",
        "._trace",
        "._active_turn",
        "._record",
    ):
        assert forbidden not in source


def test_v2_2f_cannot_start_or_end_runtime_turns():
    source = (
        REALTIME_DIR
        / "runtime_trace_adapter.py"
    ).read_text()

    for forbidden in (
        ".begin_turn(",
        ".end_turn(",
        ".close_session(",
    ):
        assert forbidden not in source


def test_v2_2f_has_no_global_runtime_lookup():
    source = (
        REALTIME_DIR
        / "runtime_trace_adapter.py"
    ).read_text()

    assert "get_realtime_runtime" not in source
    tree = ast.parse(
        source,
        filename=str(
            REALTIME_DIR
            / "runtime_trace_adapter.py"
        ),
    )

    assert not any(
        isinstance(node, ast.Name)
        and node.id == "_RUNTIME"
        for node in ast.walk(tree)
    )

    assert not any(
        isinstance(node, ast.Attribute)
        and node.attr == "_RUNTIME"
        for node in ast.walk(tree)
    )


def test_v2_2f_has_no_realtime_queue_or_scheduler_control():
    source = (
        REALTIME_DIR
        / "runtime_trace_adapter.py"
    ).read_text()

    for forbidden in (
        "pending_signals",
        "drain_signals",
        ".tick(",
        "deque(",
        ".append(",
        ".clear(",
    ):
        assert forbidden not in source


def test_v2_2f_has_no_agent_ui_tool_or_model_dependency():
    source = (
        REALTIME_DIR
        / "runtime_trace_adapter.py"
    ).read_text()

    for forbidden in (
        "app.agent",
        "app.ui",
        "app.tools",
        "KumaAgent",
        "KumaGUIRuntime",
        "emit_status",
        ".emit(",
        ".connect(",
        "QTimer",
        "QThread",
        "create_task(",
        ".run(",
    ):
        assert forbidden not in source


def test_v2_boundary_markers_remain_explicit():
    required = {
        "runtime_trigger.py": (
            "TRIGGER PROPOSAL != COMMAND",
            "TRIGGER PROPOSAL != PERMISSION",
            "TRIGGER PROPOSAL != EXECUTION",
            "TRIGGER PROPOSAL != VERIFIED COMPLETION",
            "AUTHORITY: NONE",
        ),
        "trigger_policy.py": (
            "ELIGIBILITY != COMMAND",
            "ELIGIBILITY != PERMISSION",
            "ELIGIBILITY != WAKE",
            "ELIGIBILITY != EXECUTION",
            "ELIGIBILITY != VERIFIED COMPLETION",
            "AUTHORITY: NONE",
        ),
        "trigger_request.py": (
            "REQUEST != COMMAND",
            "REQUEST != PERMISSION",
            "REQUEST != WAKE",
            "REQUEST != EXECUTION",
            "REQUEST != VERIFIED COMPLETION",
            "AUTHORITY: NONE",
        ),
        "trigger_observation.py": (
            "OBSERVATION != ACKNOWLEDGMENT",
            "OBSERVATION != DELIVERY",
            "OBSERVATION != WAKE",
            "OBSERVATION != EXECUTION",
            "OBSERVATION != VERIFIED COMPLETION",
            "AUTHORITY: NONE",
        ),
        "runtime_trace_adapter.py": (
            "RECORDING != CONTROL",
            "TRACE != AUTHORITY",
            "OBSERVATION != EXECUTION",
            "RECORDING != DELIVERY",
            "RECORDING != ACKNOWLEDGMENT",
            "RECORDING != VERIFIED COMPLETION",
            "AUTHORITY: NONE",
        ),
    }

    for filename, markers in required.items():
        source = (
            REALTIME_DIR
            / filename
        ).read_text()

        for marker in markers:
            assert marker in source


def test_v2_runtime_boundary_types_remain_zero_authority():
    correlation = KumaRuntimeCorrelation()

    assert correlation.authority == "NONE"
    assert isinstance(
        correlation.trace,
        KumaRuntimeTrace,
    )
    assert correlation.trace.authority == "NONE"

    turn = correlation.begin_turn()

    assert isinstance(
        turn,
        RuntimeTurnCorrelation,
    )
    assert turn.authority == "NONE"


def test_v2_2f_trace_event_shape_is_structural():
    source = (
        REALTIME_DIR
        / "runtime_trace_adapter.py"
    ).read_text()

    assert (
        '_REALTIME_TRACE_STAGE = "realtime"'
        in source
    )
    assert (
        '_REALTIME_TRACE_EVENT_KIND = "trigger.observed"'
        in source
    )
    assert (
        '_REALTIME_TRACE_OUTCOME = "observed"'
        in source
    )

    for forbidden in (
        "previous_fact",
        "raw_value",
        "latitude",
        "longitude",
        "user_message",
        "tool_payload",
    ):
        assert forbidden not in source


def test_v2_architecture_regression_adds_no_production_v2_module():
    assert not (
        REALTIME_DIR
        / "realtime_v2.py"
    ).exists()


def test_v2_core_types_remain_class_contracts():
    for value in (
        RealtimeSignal,
        RealtimeRelevanceLevel,
        RealtimeTriggerProposal,
        RealtimeTriggerEligibilityDecision,
        RealtimeTriggerRequest,
        RealtimeTriggerObservation,
        KumaRuntimeCorrelation,
        KumaRuntimeTrace,
        RuntimeTraceEvent,
    ):
        assert inspect.isclass(value)
