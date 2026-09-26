from __future__ import annotations

"""
KUMA RUNTIME-V2B regression.

Runtime-V2B is an immutable zero-authority carrier only.

CALLER INTENT -> INVOCATION
OPTIONAL OBSERVATION -> EVIDENCE ONLY
CARRIER != EXECUTION
OBSERVATION != INVOCATION
OBSERVATION != PERMISSION
TRACE != CONTROL
AUTHORITY: NONE
"""

import ast
from dataclasses import (
    FrozenInstanceError,
    fields,
    is_dataclass,
)
import inspect
from pathlib import Path

import pytest

import app.runtime_v2_invocation as runtime_v2b


MODULE = Path(
    "app/runtime_v2_invocation.py"
)


def _app_imports(
    path: Path,
) -> set[str]:
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
            imports.add(
                node.module
            )

        elif isinstance(
            node,
            ast.Import,
        ):
            for alias in node.names:
                if alias.name.startswith(
                    "app."
                ):
                    imports.add(
                        alias.name
                    )

    return imports


def _v2_chain_symbols(
    path: Path,
) -> tuple[str, ...]:
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
            found.add(
                node.id
            )

        elif (
            isinstance(node, ast.Attribute)
            and node.attr in chain_symbols
        ):
            found.add(
                node.attr
            )

        elif isinstance(
            node,
            ast.ImportFrom,
        ):
            for alias in node.names:
                if alias.name in chain_symbols:
                    found.add(
                        alias.name
                    )

    return tuple(
        sorted(
            found
        )
    )


def test_runtime_v2b_module_exists():
    assert MODULE.is_file()


def test_runtime_v2b_authority_constant_is_none():
    assert (
        runtime_v2b.RUNTIME_V2B_AUTHORITY_NONE
        == "NONE"
    )


def test_runtime_invocation_is_dataclass():
    assert is_dataclass(
        runtime_v2b.RuntimeInvocation
    )


def test_runtime_invocation_is_frozen():
    invocation = runtime_v2b.RuntimeInvocation(
        operation=lambda: "ok",
    )

    with pytest.raises(
        FrozenInstanceError
    ):
        invocation.operation = lambda: "changed"


def test_runtime_invocation_uses_slots():
    assert "__slots__" in (
        runtime_v2b.RuntimeInvocation.__dict__
    )


def test_runtime_invocation_constructor_signature_is_carrier_only():
    signature = inspect.signature(
        runtime_v2b.RuntimeInvocation
    )

    assert tuple(
        signature.parameters
    ) == (
        "operation",
        "observation",
    )


def test_observation_defaults_to_none():
    signature = inspect.signature(
        runtime_v2b.RuntimeInvocation
    )

    assert (
        signature.parameters[
            "observation"
        ].default
        is None
    )


def test_authority_field_is_not_constructor_input():
    runtime_fields = {
        item.name: item
        for item in fields(
            runtime_v2b.RuntimeInvocation
        )
    }

    assert (
        runtime_fields[
            "authority"
        ].init
        is False
    )


def test_authority_is_always_none_on_constructed_carrier():
    invocation = runtime_v2b.RuntimeInvocation(
        operation=lambda: "ok",
    )

    assert invocation.authority == "NONE"


def test_operation_is_preserved_by_identity():
    operation = lambda: "result"

    invocation = runtime_v2b.RuntimeInvocation(
        operation=operation,
    )

    assert invocation.operation is operation


def test_observation_none_is_preserved():
    invocation = runtime_v2b.RuntimeInvocation(
        operation=lambda: None,
        observation=None,
    )

    assert invocation.observation is None


def test_construction_never_invokes_operation():
    calls = []

    def operation():
        calls.append(
            "called"
        )
        return "result"

    invocation = runtime_v2b.RuntimeInvocation(
        operation=operation,
    )

    assert invocation.operation is operation
    assert calls == []


def test_non_callable_operation_is_rejected():
    with pytest.raises(
        TypeError,
        match="operation must be callable",
    ):
        runtime_v2b.RuntimeInvocation(
            operation="not-callable",
        )


def test_wrong_observation_type_is_rejected():
    with pytest.raises(
        TypeError,
        match="RealtimeTriggerObservation or None",
    ):
        runtime_v2b.RuntimeInvocation(
            operation=lambda: None,
            observation=object(),
        )


def test_valid_observation_is_preserved_by_identity(
    monkeypatch,
):
    class FakeObservation:
        def __init__(
            self,
            authority,
        ):
            self.authority = authority

    monkeypatch.setattr(
        runtime_v2b,
        "RealtimeTriggerObservation",
        FakeObservation,
    )

    observation = FakeObservation(
        "NONE"
    )

    invocation = runtime_v2b.RuntimeInvocation(
        operation=lambda: None,
        observation=observation,
    )

    assert (
        invocation.observation
        is observation
    )


def test_non_none_observation_must_retain_zero_authority(
    monkeypatch,
):
    class FakeObservation:
        def __init__(
            self,
            authority,
        ):
            self.authority = authority

    monkeypatch.setattr(
        runtime_v2b,
        "RealtimeTriggerObservation",
        FakeObservation,
    )

    with pytest.raises(
        ValueError,
        match="authority must remain NONE",
    ):
        runtime_v2b.RuntimeInvocation(
            operation=lambda: None,
            observation=FakeObservation(
                "EXECUTE"
            ),
        )


def test_carrier_has_no_run_execute_or_dispatch_method():
    for name in (
        "run",
        "execute",
        "dispatch",
        "invoke",
    ):
        assert not hasattr(
            runtime_v2b.RuntimeInvocation,
            name,
        )


def test_runtime_v2b_app_import_surface_is_exact():
    assert _app_imports(
        MODULE
    ) == {
        "app.realtime.trigger_observation",
    }


def test_runtime_v2b_exact_realtime_v2_consumer_surface():
    assert _v2_chain_symbols(
        MODULE
    ) == (
        "RealtimeTriggerObservation",
    )


def test_runtime_v2b_does_not_import_runtime_v2a():
    source = MODULE.read_text()

    assert (
        "runtime_v2_turn_observation"
        not in source
    )

    assert (
        "KumaRuntimeTurnObservationOwner"
        not in source
    )


def test_runtime_v2b_does_not_import_integration_v2a():
    source = MODULE.read_text()

    assert (
        "integration_realtime_observation_admission"
        not in source
    )

    assert (
        "admit_realtime_observation"
        not in source
    )


def test_runtime_v2b_does_not_reference_realtime_creation_chain():
    source = MODULE.read_text()

    for forbidden in (
        "propose_runtime_trigger",
        "evaluate_trigger_eligibility",
        "create_trigger_request",
        "observe_trigger_request",
        "record_trigger_observation",
    ):
        assert forbidden not in source


def test_runtime_v2b_does_not_reference_queue_or_signal_selection():
    source = MODULE.read_text()

    for forbidden in (
        "pending_signals",
        "drain_signals",
        "get_realtime_runtime",
        "RealtimeRuntime",
        "evaluate_attention_surfacing",
        "remember_seen_event",
        "selected_event_id",
        "attention_score",
    ):
        assert forbidden not in source


def test_runtime_v2b_does_not_import_agent_gui_or_live_binding():
    imports = _app_imports(
        MODULE
    )

    for forbidden_prefix in (
        "app.agent",
        "app.ui",
        "app.runtime_live_binding",
        "app.runtime_correlation",
        "app.runtime_trace",
    ):
        assert not any(
            name.startswith(
                forbidden_prefix
            )
            for name in imports
        )


def test_runtime_v2b_has_no_runtime_turn_calls():
    tree = ast.parse(
        MODULE.read_text(),
        filename=str(MODULE),
    )

    forbidden = {
        "begin_turn",
        "end_turn",
        "run",
        "execute",
        "dispatch",
        "invoke",
    }

    hits = []

    for node in ast.walk(tree):
        if not isinstance(
            node,
            ast.Call,
        ):
            continue

        func = node.func

        if (
            isinstance(
                func,
                ast.Name,
            )
            and func.id in forbidden
        ):
            hits.append(
                (
                    func.id,
                    node.lineno,
                )
            )

        elif (
            isinstance(
                func,
                ast.Attribute,
            )
            and func.attr in forbidden
        ):
            hits.append(
                (
                    func.attr,
                    node.lineno,
                )
            )

    assert hits == []


def test_runtime_v2b_does_not_call_carried_operation():
    tree = ast.parse(
        MODULE.read_text(),
        filename=str(MODULE),
    )

    hits = []

    for node in ast.walk(tree):
        if not isinstance(
            node,
            ast.Call,
        ):
            continue

        func = node.func

        if (
            isinstance(
                func,
                ast.Attribute,
            )
            and func.attr == "operation"
        ):
            hits.append(
                node.lineno
            )

        elif (
            isinstance(
                func,
                ast.Name,
            )
            and func.id == "operation"
        ):
            hits.append(
                node.lineno
            )

    assert hits == []


def test_runtime_v2b_has_no_scheduler_background_structure():
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
        if isinstance(
            node,
            ast.Import,
        ):
            for alias in node.names:
                if (
                    alias.name.split(
                        ".",
                        1,
                    )[0]
                    in forbidden_import_roots
                ):
                    hits.append(
                        (
                            "import",
                            alias.name,
                            node.lineno,
                        )
                    )

        elif isinstance(
            node,
            ast.ImportFrom,
        ):
            if (
                node.module
                and node.module.split(
                    ".",
                    1,
                )[0]
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
            isinstance(
                node,
                ast.Name,
            )
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
            isinstance(
                node,
                ast.Attribute,
            )
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
            isinstance(
                node,
                ast.Call,
            )
            and isinstance(
                node.func,
                ast.Attribute,
            )
            and node.func.attr
            in forbidden_call_attributes
        ):
            hits.append(
                (
                    "call",
                    node.func.attr,
                    node.lineno,
                )
            )

        elif (
            isinstance(
                node,
                ast.While,
            )
            and isinstance(
                node.test,
                ast.Constant,
            )
            and node.test.value is True
        ):
            hits.append(
                (
                    "while-true",
                    node.lineno,
                )
            )

    assert hits == []


def test_runtime_v2b_owns_no_tool_model_permission_or_execution_surface():
    source = MODULE.read_text()

    for forbidden in (
        "ActionExecutor",
        "tool_registry",
        "execute_command",
        "call_mission_model",
        "get_permission_level",
        "requires_confirmation",
        "request_confirmation",
        "confirmation_callback",
        "USER_AUTHORIZED",
        "EXECUTION_ALLOWED",
    ):
        assert forbidden not in source


def test_runtime_v2b_has_no_mutable_collection_state():
    tree = ast.parse(
        MODULE.read_text(),
        filename=str(MODULE),
    )

    forbidden_calls = {
        "dict",
        "list",
        "set",
        "deque",
    }

    hits = []

    for node in ast.walk(tree):
        if (
            isinstance(
                node,
                ast.Call,
            )
            and isinstance(
                node.func,
                ast.Name,
            )
            and node.func.id
            in forbidden_calls
        ):
            hits.append(
                (
                    node.func.id,
                    node.lineno,
                )
            )

    assert hits == []


def test_runtime_v2b_boundary_markers_are_explicit():
    source = MODULE.read_text()

    for marker in (
        "CALLER INTENT -> INVOCATION",
        "OPTIONAL OBSERVATION -> EVIDENCE ONLY",
        "CARRIER != EXECUTION",
        "OBSERVATION != INVOCATION",
        "OBSERVATION != PERMISSION",
        "TRACE != CONTROL",
        "AUTHORITY: NONE",
    ):
        assert marker in source


def test_runtime_v2b_public_class_surface_is_minimal():
    public = {
        name
        for name in (
            runtime_v2b.RuntimeInvocation.__dict__
        )
        if not name.startswith("_")
    }

    assert public <= {
        "authority",
        "observation",
        "operation",
    }
