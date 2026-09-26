from pathlib import Path
from types import SimpleNamespace

import app.agent.gui_runtime as gui_runtime
import app.agent.kuma_runtime as kuma_runtime

from app.memory.formation import (
    FormationDisposition,
)
from app.memory.completed_turn_observation_owner import (
    CompletedTurnObservationStatus,
)
from app.memory.turn_candidate_composition import (
    TurnCandidateCompositionStatus,
)


ROOT = Path(__file__).resolve().parent

GUI = (
    ROOT
    / "agent"
    / "gui_runtime.py"
)

CLI = (
    ROOT
    / "agent"
    / "kuma_runtime.py"
)


class FakeRuntimeOwner:
    def __init__(
        self,
    ):
        self.closed = False
        self.pipeline_events = []

    @property
    def authority(
        self,
    ):
        return "NONE"

    def observe_pipeline_event(
        self,
        *,
        event_kind,
        outcome,
    ):
        self.pipeline_events.append(
            (
                event_kind,
                outcome,
            )
        )

    def events(
        self,
    ):
        return tuple(
            self.pipeline_events
        )

    def close(
        self,
    ):
        self.closed = True


class FakeIntegrationOwner:
    instances = []

    def __init__(
        self,
        *,
        runtime_owner,
        realtime_runtime,
        trigger_policy,
    ):
        self.runtime_owner = (
            runtime_owner
        )
        self.realtime_runtime = (
            realtime_runtime
        )
        self.trigger_policy = (
            trigger_policy
        )
        self.run_calls = 0
        self.prepared = object()

        type(
            self
        ).instances.append(
            self
        )

    def run(
        self,
        operation,
    ):
        self.run_calls += 1
        return operation(
            self.prepared
        )


class FakeKuma:
    def __init__(
        self,
    ):
        self.realtime_runtime = (
            object()
        )
        self.confirmation_callback = None
        self.status_callback = None
        self._runtime_observer = None
        self.run_calls = []
        self.classification_calls = []
        self.classification_error = False

    def explicitly_requests_tool_action(
        self,
        user_message,
        tool_name,
        arguments,
    ):
        self.classification_calls.append(
            (
                user_message,
                tool_name,
                arguments,
            )
        )

        if self.classification_error:
            raise RuntimeError(
                "classification failed"
            )

        lowered = str(
            user_message
        ).casefold()

        if tool_name == "remember":
            return any(
                marker in lowered
                for marker in (
                    "remember ",
                    "remember that",
                    "remember this",
                    "save this",
                    "save that",
                    "keep in mind",
                )
            )

        if tool_name == "recall":
            return any(
                marker in lowered
                for marker in (
                    "what do you remember",
                    "what did i tell you",
                    "do you remember",
                    "recall ",
                    "remember what",
                )
            )

        if tool_name == "forget":
            return any(
                marker in lowered
                for marker in (
                    "forget ",
                    "remove from memory",
                    "delete from memory",
                )
            )

        return False

    def run(
        self,
        user_message,
        *,
        prepared_realtime_turn=None,
    ):
        self.run_calls.append(
            (
                user_message,
                prepared_realtime_turn,
            )
        )

        return "assistant-response"


def test_v2e_classifier_treats_memory_operations_as_union():
    kuma = FakeKuma()

    assert not (
        kuma_runtime
        ._explicit_memory_operation_requested(
            kuma,
            "I prefer VS Code.",
        )
    )

    assert (
        kuma_runtime
        ._explicit_memory_operation_requested(
            kuma,
            "Remember that I prefer VS Code.",
        )
    )

    assert (
        kuma_runtime
        ._explicit_memory_operation_requested(
            kuma,
            "Recall my editor preference.",
        )
    )

    assert (
        kuma_runtime
        ._explicit_memory_operation_requested(
            kuma,
            "Forget that I prefer VS Code.",
        )
    )

    assert (
        kuma_runtime
        ._explicit_memory_operation_requested(
            kuma,
            "What do you remember about me?",
        )
    )


def test_v2e_classifier_failure_fails_closed_for_implicit_extraction():
    kuma = FakeKuma()
    kuma.classification_error = True

    assert (
        kuma_runtime
        ._explicit_memory_operation_requested(
            kuma,
            "I prefer VS Code.",
        )
        is True
    )


def test_v2e_gui_runs_integration_and_agent_exactly_once_then_observes(
    monkeypatch,
):
    fake_kuma = FakeKuma()

    FakeIntegrationOwner.instances.clear()

    monkeypatch.setattr(
        gui_runtime,
        "create_kuma",
        lambda: fake_kuma,
    )

    monkeypatch.setattr(
        gui_runtime,
        "KumaRuntimeV2LiveOwner",
        FakeRuntimeOwner,
    )

    monkeypatch.setattr(
        gui_runtime,
        "KumaIntegrationV2LiveTurnOwner",
        FakeIntegrationOwner,
    )

    runtime = (
        gui_runtime.KumaGUIRuntime()
    )

    result = runtime.run(
        "I prefer VS Code."
    )

    assert result == "assistant-response"

    assert len(
        FakeIntegrationOwner.instances
    ) == 1

    integration = (
        FakeIntegrationOwner.instances[
            0
        ]
    )

    assert integration.run_calls == 1

    assert fake_kuma.run_calls == [
        (
            "I prefer VS Code.",
            integration.prepared,
        )
    ]

    observation = (
        runtime
        ._memory_v2_owner
        .last_observation()
    )

    assert observation is not None

    assert (
        observation.status
        is CompletedTurnObservationStatus.COMPOSED
    )

    assert observation.composition is not None

    assert (
        observation.composition.status
        is TurnCandidateCompositionStatus.OBSERVED
    )

    assert (
        observation
        .composition
        .observation
        .disposition
        is FormationDisposition.CANDIDATE_ONLY
    )

    assert (
        observation
        .composition
        .observation
        .candidate
        .value
        == "VS Code"
    )


def test_v2e_gui_explicit_memory_turn_skips_implicit_extraction(
    monkeypatch,
):
    fake_kuma = FakeKuma()

    FakeIntegrationOwner.instances.clear()

    monkeypatch.setattr(
        gui_runtime,
        "create_kuma",
        lambda: fake_kuma,
    )

    monkeypatch.setattr(
        gui_runtime,
        "KumaRuntimeV2LiveOwner",
        FakeRuntimeOwner,
    )

    monkeypatch.setattr(
        gui_runtime,
        "KumaIntegrationV2LiveTurnOwner",
        FakeIntegrationOwner,
    )

    runtime = (
        gui_runtime.KumaGUIRuntime()
    )

    result = runtime.run(
        "Remember that I prefer VS Code."
    )

    assert result == "assistant-response"
    assert len(
        fake_kuma.run_calls
    ) == 1

    observation = (
        runtime
        ._memory_v2_owner
        .last_observation()
    )

    assert observation is not None

    assert (
        observation.status
        is (
            CompletedTurnObservationStatus
            .SKIPPED_EXPLICIT_MEMORY_OPERATION
        )
    )


def test_v2e_gui_classification_failure_still_runs_turn_and_skips_implicit(
    monkeypatch,
):
    fake_kuma = FakeKuma()
    fake_kuma.classification_error = True

    FakeIntegrationOwner.instances.clear()

    monkeypatch.setattr(
        gui_runtime,
        "create_kuma",
        lambda: fake_kuma,
    )

    monkeypatch.setattr(
        gui_runtime,
        "KumaRuntimeV2LiveOwner",
        FakeRuntimeOwner,
    )

    monkeypatch.setattr(
        gui_runtime,
        "KumaIntegrationV2LiveTurnOwner",
        FakeIntegrationOwner,
    )

    runtime = (
        gui_runtime.KumaGUIRuntime()
    )

    result = runtime.run(
        "I prefer VS Code."
    )

    assert result == "assistant-response"
    assert len(
        fake_kuma.run_calls
    ) == 1

    observation = (
        runtime
        ._memory_v2_owner
        .last_observation()
    )

    assert observation is not None

    assert (
        observation.status
        is (
            CompletedTurnObservationStatus
            .SKIPPED_EXPLICIT_MEMORY_OPERATION
        )
    )


def test_v2e_cli_wraps_one_integration_turn_and_one_agent_run(
    monkeypatch,
    capsys,
):
    fake_kuma = FakeKuma()
    integration_instances = []
    memory_calls = []

    class CLIFakeIntegrationOwner(
        FakeIntegrationOwner
    ):
        def __init__(
            self,
            **kwargs,
        ):
            super().__init__(
                **kwargs
            )
            integration_instances.append(
                self
            )

    class FakeMemoryOwner:
        def run(
            self,
            operation,
            *,
            user_message,
            explicit_memory_operation_requested,
        ):
            memory_calls.append(
                (
                    user_message,
                    explicit_memory_operation_requested,
                )
            )

            return operation()

    inputs = iter(
        (
            "I prefer VS Code.",
            "exit",
        )
    )

    monkeypatch.setattr(
        kuma_runtime,
        "create_kuma",
        lambda: fake_kuma,
    )

    monkeypatch.setattr(
        kuma_runtime,
        "KumaRuntimeV2LiveOwner",
        FakeRuntimeOwner,
    )

    monkeypatch.setattr(
        kuma_runtime,
        "KumaIntegrationV2LiveTurnOwner",
        CLIFakeIntegrationOwner,
    )

    monkeypatch.setattr(
        kuma_runtime,
        "KumaMemoryV2CompletedTurnOwner",
        FakeMemoryOwner,
    )

    monkeypatch.setattr(
        kuma_runtime,
        "release_owned_mouse_button_for_shutdown",
        lambda: SimpleNamespace(
            success=True,
            result="already CLEAR",
            error=None,
        ),
    )

    monkeypatch.setattr(
        "builtins.input",
        lambda _prompt: next(
            inputs
        ),
    )

    kuma_runtime.main()

    assert len(
        integration_instances
    ) == 1

    integration = (
        integration_instances[
            0
        ]
    )

    assert integration.run_calls == 1

    assert fake_kuma.run_calls == [
        (
            "I prefer VS Code.",
            integration.prepared,
        )
    ]

    assert memory_calls == [
        (
            "I prefer VS Code.",
            False,
        )
    ]

    output = (
        capsys
        .readouterr()
        .out
    )

    assert (
        "KUMA → assistant-response"
        in output
    )


def test_v2e_preserves_frozen_integration_v2_source_expectations():
    gui = GUI.read_text()
    cli = CLI.read_text()

    assert (
        "self._integration_v2_owner.run("
        in gui
    )

    assert (
        "self._runtime_v2_owner.run("
        not in gui
    )

    assert (
        "lambda prepared_realtime_turn: self.kuma.run("
        in gui
    )

    assert (
        "prepared_realtime_turn=prepared_realtime_turn"
        in gui
    )

    assert "integration_owner.run(" in cli
    assert "runtime_owner.run(" not in cli

    assert (
        "lambda prepared_realtime_turn: kuma.run("
        in cli
    )

    assert "prepared_realtime_turn=(" in cli


def test_v2e_constructs_one_memory_owner_per_gui_and_cli_session_source():
    gui = GUI.read_text()
    cli = CLI.read_text()

    assert (
        gui.count(
            "KumaMemoryV2CompletedTurnOwner()"
        )
        == 1
    )

    assert (
        cli.count(
            "KumaMemoryV2CompletedTurnOwner()"
        )
        == 1
    )

    assert (
        "self._memory_v2_owner.run("
        in gui
    )

    assert "memory_owner.run(" in cli


def test_v2e_does_not_add_persistence_or_runtime_trace_payloads():
    gui = GUI.read_text()
    cli = CLI.read_text()

    combined = (
        gui
        + "\n"
        + cli
    )

    for forbidden in (
        "MemoryStore(",
        "save_memory(",
        "sqlite3",
        "RuntimeInvocation(",
        "trigger.observed",
        "candidate.value",
        "assistant_response",
    ):
        assert forbidden not in combined


def test_v2e_production_markers_are_present():
    cli = CLI.read_text()

    for marker in (
        "ANY EXPLICIT MEMORY OPERATION -> SKIP IMPLICIT EXTRACTION",
        "CLASSIFICATION != EXECUTION",
        "CLASSIFICATION FAILURE -> SKIP IMPLICIT EXTRACTION",
        "MEMORY OBSERVATION != RUNTIME TRACE",
        "MEMORY OBSERVATION != PERSISTENCE",
        "AUTHORITY: NONE",
    ):
        assert marker in cli
