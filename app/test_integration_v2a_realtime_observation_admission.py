from __future__ import annotations

"""
KUMA INTEGRATION-V2A regression.

Integration-V2A is pure explicit-input composition of frozen Realtime 2A→2D.
It creates no runtime invocation and owns no realtime queue or attention state.

EXPLICIT SIGNAL INPUT ONLY
SIGNAL INPUT != INVOCATION
ELIGIBILITY != PERMISSION
ADMISSION != ATTENTION SELECTION
OBSERVATION != INVOCATION
OBSERVATION != EXECUTION
AUTHORITY: NONE
"""

import ast
import inspect
from pathlib import Path

import pytest

import app.integration_realtime_observation_admission as integration_v2a


MODULE = Path(
    "app/integration_realtime_observation_admission.py"
)


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


def _chain_symbols(path: Path) -> tuple[str, ...]:
    chain_symbols = {
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

    tree = ast.parse(
        path.read_text(),
        filename=str(path),
    )

    found = set()

    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Name)
            and node.id in chain_symbols
        ):
            found.add(node.id)

        elif (
            isinstance(node, ast.Attribute)
            and node.attr in chain_symbols
        ):
            found.add(node.attr)

        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name in chain_symbols:
                    found.add(alias.name)

    return tuple(
        sorted(found)
    )


def test_integration_v2a_module_exists():
    assert MODULE.is_file()


def test_integration_v2a_authority_constant_is_none():
    assert (
        integration_v2a.INTEGRATION_V2A_AUTHORITY_NONE
        == "NONE"
    )


def test_admission_signature_has_explicit_signal_and_keyword_thresholds():
    signature = inspect.signature(
        integration_v2a.admit_realtime_observation
    )

    assert tuple(signature.parameters) == (
        "signal",
        "minimum_level",
        "minimum_score",
    )

    assert (
        signature.parameters["minimum_level"].kind
        is inspect.Parameter.KEYWORD_ONLY
    )

    assert (
        signature.parameters["minimum_score"].kind
        is inspect.Parameter.KEYWORD_ONLY
    )


def test_admission_thresholds_have_no_defaults():
    signature = inspect.signature(
        integration_v2a.admit_realtime_observation
    )

    assert (
        signature.parameters["minimum_level"].default
        is inspect.Parameter.empty
    )

    assert (
        signature.parameters["minimum_score"].default
        is inspect.Parameter.empty
    )


def test_success_path_composes_frozen_chain_in_exact_order(
    monkeypatch,
):
    signal = object()
    minimum_level = object()
    proposal = object()
    decision = object()
    request = object()
    observation = object()
    calls = []

    def propose(value):
        calls.append(
            (
                "proposal",
                value,
            )
        )
        return proposal

    def evaluate(
        value,
        *,
        minimum_level,
        minimum_score,
    ):
        calls.append(
            (
                "eligibility",
                value,
                minimum_level,
                minimum_score,
            )
        )
        return decision

    def create(
        proposal_value,
        decision_value,
    ):
        calls.append(
            (
                "request",
                proposal_value,
                decision_value,
            )
        )
        return request

    def observe(value):
        calls.append(
            (
                "observation",
                value,
            )
        )
        return observation

    monkeypatch.setattr(
        integration_v2a,
        "propose_runtime_trigger",
        propose,
    )

    monkeypatch.setattr(
        integration_v2a,
        "evaluate_trigger_eligibility",
        evaluate,
    )

    monkeypatch.setattr(
        integration_v2a,
        "create_trigger_request",
        create,
    )

    monkeypatch.setattr(
        integration_v2a,
        "observe_trigger_request",
        observe,
    )

    result = (
        integration_v2a.admit_realtime_observation(
            signal,
            minimum_level=minimum_level,
            minimum_score=0.75,
        )
    )

    assert result is observation

    assert calls == [
        (
            "proposal",
            signal,
        ),
        (
            "eligibility",
            proposal,
            minimum_level,
            0.75,
        ),
        (
            "request",
            proposal,
            decision,
        ),
        (
            "observation",
            request,
        ),
    ]


def test_none_proposal_short_circuits_entire_remaining_chain(
    monkeypatch,
):
    signal = object()
    calls = []

    def propose(value):
        calls.append(
            (
                "proposal",
                value,
            )
        )
        return None

    monkeypatch.setattr(
        integration_v2a,
        "propose_runtime_trigger",
        propose,
    )

    monkeypatch.setattr(
        integration_v2a,
        "evaluate_trigger_eligibility",
        lambda *args, **kwargs: pytest.fail(
            "eligibility must not run when proposal is None"
        ),
    )

    monkeypatch.setattr(
        integration_v2a,
        "create_trigger_request",
        lambda *args, **kwargs: pytest.fail(
            "request must not run when proposal is None"
        ),
    )

    monkeypatch.setattr(
        integration_v2a,
        "observe_trigger_request",
        lambda *args, **kwargs: pytest.fail(
            "observation must not run when proposal is None"
        ),
    )

    result = (
        integration_v2a.admit_realtime_observation(
            signal,
            minimum_level=object(),
            minimum_score=0.5,
        )
    )

    assert result is None
    assert calls == [
        (
            "proposal",
            signal,
        ),
    ]


def test_none_request_short_circuits_observation(
    monkeypatch,
):
    proposal = object()
    decision = object()

    monkeypatch.setattr(
        integration_v2a,
        "propose_runtime_trigger",
        lambda signal: proposal,
    )

    monkeypatch.setattr(
        integration_v2a,
        "evaluate_trigger_eligibility",
        lambda proposal_value, **kwargs: decision,
    )

    monkeypatch.setattr(
        integration_v2a,
        "create_trigger_request",
        lambda proposal_value, decision_value: None,
    )

    monkeypatch.setattr(
        integration_v2a,
        "observe_trigger_request",
        lambda *args, **kwargs: pytest.fail(
            "observation must not run when request is None"
        ),
    )

    result = (
        integration_v2a.admit_realtime_observation(
            object(),
            minimum_level=object(),
            minimum_score=0.5,
        )
    )

    assert result is None


def test_admission_returns_exact_observation_identity(
    monkeypatch,
):
    observation = object()

    monkeypatch.setattr(
        integration_v2a,
        "propose_runtime_trigger",
        lambda signal: object(),
    )

    monkeypatch.setattr(
        integration_v2a,
        "evaluate_trigger_eligibility",
        lambda proposal, **kwargs: object(),
    )

    monkeypatch.setattr(
        integration_v2a,
        "create_trigger_request",
        lambda proposal, decision: object(),
    )

    monkeypatch.setattr(
        integration_v2a,
        "observe_trigger_request",
        lambda request: observation,
    )

    assert (
        integration_v2a.admit_realtime_observation(
            object(),
            minimum_level=object(),
            minimum_score=0.5,
        )
        is observation
    )


def test_admission_forwards_minimum_score_without_modification(
    monkeypatch,
):
    captured = {}

    monkeypatch.setattr(
        integration_v2a,
        "propose_runtime_trigger",
        lambda signal: object(),
    )

    def evaluate(
        proposal,
        *,
        minimum_level,
        minimum_score,
    ):
        captured["minimum_score"] = minimum_score
        return object()

    monkeypatch.setattr(
        integration_v2a,
        "evaluate_trigger_eligibility",
        evaluate,
    )

    monkeypatch.setattr(
        integration_v2a,
        "create_trigger_request",
        lambda proposal, decision: None,
    )

    integration_v2a.admit_realtime_observation(
        object(),
        minimum_level=object(),
        minimum_score=0.8125,
    )

    assert captured["minimum_score"] == 0.8125


def test_admission_forwards_minimum_level_by_identity(
    monkeypatch,
):
    minimum_level = object()
    captured = {}

    monkeypatch.setattr(
        integration_v2a,
        "propose_runtime_trigger",
        lambda signal: object(),
    )

    def evaluate(
        proposal,
        *,
        minimum_level,
        minimum_score,
    ):
        captured["minimum_level"] = minimum_level
        return object()

    monkeypatch.setattr(
        integration_v2a,
        "evaluate_trigger_eligibility",
        evaluate,
    )

    monkeypatch.setattr(
        integration_v2a,
        "create_trigger_request",
        lambda proposal, decision: None,
    )

    integration_v2a.admit_realtime_observation(
        object(),
        minimum_level=minimum_level,
        minimum_score=0.5,
    )

    assert captured["minimum_level"] is minimum_level


def test_frozen_chain_exception_propagates_unchanged(
    monkeypatch,
):
    error = RuntimeError(
        "frozen chain rejected input"
    )

    def propose(signal):
        raise error

    monkeypatch.setattr(
        integration_v2a,
        "propose_runtime_trigger",
        propose,
    )

    with pytest.raises(RuntimeError) as caught:
        integration_v2a.admit_realtime_observation(
            object(),
            minimum_level=object(),
            minimum_score=0.5,
        )

    assert caught.value is error


def test_integration_v2a_app_import_surface_is_exact():
    assert _app_imports(MODULE) == {
        "app.realtime.change_detection",
        "app.realtime.runtime_trigger",
        "app.realtime.trigger_policy",
        "app.realtime.trigger_request",
        "app.realtime.trigger_observation",
    }


def test_integration_v2a_exact_frozen_v2_consumer_surface():
    assert _chain_symbols(MODULE) == (
        "RealtimeTriggerObservation",
        "create_trigger_request",
        "evaluate_trigger_eligibility",
        "observe_trigger_request",
        "propose_runtime_trigger",
    )


def test_integration_v2a_does_not_reference_runtime_v2a():
    source = MODULE.read_text()

    assert "runtime_v2_turn_observation" not in source
    assert "KumaRuntimeTurnObservationOwner" not in source


def test_integration_v2a_does_not_acquire_or_drain_signals():
    source = MODULE.read_text()

    for forbidden in (
        "pending_signals",
        "drain_signals",
        "get_realtime_runtime",
        "RealtimeRuntime",
    ):
        assert forbidden not in source


def test_integration_v2a_does_not_select_or_rank_multiple_signals():
    source = MODULE.read_text()

    for forbidden in (
        "sorted(",
        ".sort(",
        "max(",
        "min(",
        "selected_event_id",
        "attention_score",
        "ProactiveAttentionEngine",
        "evaluate_attention_surfacing",
    ):
        assert forbidden not in source


def test_integration_v2a_owns_no_seen_or_ack_state():
    source = MODULE.read_text()

    for forbidden in (
        "remember_seen_event",
        "seen_event_ids",
        "acknowledged_event_ids",
        "_raphael_attention_seen_event_ids",
    ):
        assert forbidden not in source


def test_integration_v2a_does_not_import_agent_or_ui():
    imports = _app_imports(MODULE)

    assert not any(
        name.startswith(
            (
                "app.agent",
                "app.ui",
            )
        )
        for name in imports
    )


def test_integration_v2a_does_not_invoke_agent_gui_or_runtime_turn():
    source = MODULE.read_text()

    for forbidden in (
        "KumaAgent",
        "KumaGUIRuntime",
        ".run(",
        ".begin_turn(",
        ".end_turn(",
        "KumaRuntimeLiveTraceBinding",
        "KumaRuntimeCorrelation",
    ):
        assert forbidden not in source


def test_integration_v2a_does_not_schedule_or_background_wake():
    tree = ast.parse(
        MODULE.read_text(),
        filename=str(MODULE),
    )

    forbidden_import_roots = {
        "asyncio",
        "threading",
    }

    forbidden_names = {
        "QThread",
        "QTimer",
        "Thread",
        "scheduler",
    }

    forbidden_call_attributes = {
        "create_task",
        "start",
        "tick",
    }

    hits = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if (
                    alias.name.split(".", 1)[0]
                    in forbidden_import_roots
                ):
                    hits.append(
                        (
                            "import",
                            alias.name,
                            node.lineno,
                        )
                    )

        elif isinstance(node, ast.ImportFrom):
            if (
                node.module
                and node.module.split(".", 1)[0]
                in forbidden_import_roots
            ):
                hits.append(
                    (
                        "import-from",
                        node.module,
                        node.lineno,
                    )
                )

            for alias in node.names:
                if alias.name in forbidden_names:
                    hits.append(
                        (
                            "import-name",
                            alias.name,
                            node.lineno,
                        )
                    )

        elif (
            isinstance(node, ast.Name)
            and node.id in forbidden_names
        ):
            hits.append(
                (
                    "name",
                    node.id,
                    node.lineno,
                )
            )

        elif (
            isinstance(node, ast.Attribute)
            and node.attr in forbidden_names
        ):
            hits.append(
                (
                    "attribute",
                    node.attr,
                    node.lineno,
                )
            )

        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in forbidden_call_attributes
        ):
            hits.append(
                (
                    "call",
                    node.func.attr,
                    node.lineno,
                )
            )

        elif (
            isinstance(node, ast.While)
            and isinstance(node.test, ast.Constant)
            and node.test.value is True
        ):
            hits.append(
                (
                    "while-true",
                    "True",
                    node.lineno,
                )
            )

    assert hits == []


def test_integration_v2a_does_not_own_tools_models_or_execution():
    source = MODULE.read_text()

    for forbidden in (
        "ActionExecutor",
        "tool_registry",
        "execute_command",
        "call_mission_model",
        "chat.",
        "open_app",
        "open_file",
    ):
        assert forbidden not in source


def test_integration_v2a_does_not_own_permission_or_confirmation():
    source = MODULE.read_text()

    for forbidden in (
        "get_permission_level",
        "requires_confirmation",
        "request_confirmation",
        "confirmation_callback",
        "USER_AUTHORIZED",
        "EXECUTION_ALLOWED",
    ):
        assert forbidden not in source


def test_integration_v2a_does_not_emit_status_or_notification():
    source = MODULE.read_text()

    for forbidden in (
        "emit_status",
        "status_callback",
        ".emit(",
        "notification",
        "toast",
    ):
        assert forbidden not in source


def test_integration_v2a_does_not_record_runtime_trace():
    source = MODULE.read_text()

    assert "record_trigger_observation" not in source
    assert "runtime_trace_adapter" not in source


def test_integration_v2a_owns_no_queue_or_collection_state():
    source = MODULE.read_text()

    for forbidden in (
        "deque(",
        ".append(",
        ".popleft(",
        ".clear(",
        "set()",
        "dict()",
    ):
        assert forbidden not in source


def test_integration_v2a_has_no_hidden_threshold_constants():
    source = MODULE.read_text()

    tree = ast.parse(
        source,
        filename=str(MODULE),
    )

    suspicious = []

    for node in tree.body:
        if not isinstance(
            node,
            (
                ast.Assign,
                ast.AnnAssign,
            ),
        ):
            continue

        targets = []

        if isinstance(node, ast.Assign):
            targets.extend(node.targets)
        else:
            targets.append(node.target)

        for target in targets:
            if not isinstance(
                target,
                ast.Name,
            ):
                continue

            name = target.id.upper()

            if (
                "THRESHOLD" in name
                or "MINIMUM_LEVEL" in name
                or "MINIMUM_SCORE" in name
            ):
                suspicious.append(
                    target.id
                )

    assert suspicious == []


def test_integration_v2a_boundary_markers_are_explicit():
    source = MODULE.read_text()

    for marker in (
        "EXPLICIT SIGNAL INPUT ONLY",
        "SIGNAL INPUT != INVOCATION",
        "ELIGIBILITY != PERMISSION",
        "ADMISSION != ATTENTION SELECTION",
        "OBSERVATION != INVOCATION",
        "OBSERVATION != EXECUTION",
        "AUTHORITY: NONE",
    ):
        assert marker in source
