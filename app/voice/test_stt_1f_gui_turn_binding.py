from __future__ import annotations

import inspect
from pathlib import Path

import pytest

import app.ui.window as window_module

from app.ui.window import (
    KumaWindow,
)
from app.voice.stt_turn_admission import (
    KumaSTTTurnAdmission,
)
from app.voice.voice_runtime import (
    VoiceTranscript,
)


WINDOW_SOURCE = Path(
    "app/ui/window.py"
)


class FakeSignal:
    def __init__(
        self,
    ):
        self.connections = []

    def connect(
        self,
        slot,
    ):
        self.connections.append(
            slot
        )


class FakeWorker:
    created = []

    def __init__(
        self,
        runtime,
        message,
    ):
        self.runtime = runtime
        self.message = message

        self.status_changed = (
            FakeSignal()
        )

        self.response_finished = (
            FakeSignal()
        )

        self.error = (
            FakeSignal()
        )

        self.finished = (
            FakeSignal()
        )

        self.started = False
        self.running = False

        type(
            self
        ).created.append(
            self
        )

    def start(
        self,
    ):
        self.started = True
        self.running = True

    def isRunning(
        self,
    ):
        return self.running


class BusyWorker:
    def isRunning(
        self,
    ):
        return True


class FakeInput:
    def __init__(
        self,
        text="",
    ):
        self.value = text
        self.clear_calls = 0
        self.enabled = True

    def text(
        self,
    ):
        return self.value

    def clear(
        self,
    ):
        self.clear_calls += 1
        self.value = ""

    def setEnabled(
        self,
        enabled,
    ):
        self.enabled = enabled


class FakeLabel:
    def __init__(
        self,
    ):
        self.value = ""

    def setText(
        self,
        value,
    ):
        self.value = value


class FakeButton:
    def __init__(
        self,
    ):
        self.enabled = True

    def setEnabled(
        self,
        enabled,
    ):
        self.enabled = enabled


class FakeCharacter:
    def __init__(
        self,
    ):
        self.states = []

    def set_state(
        self,
        state,
    ):
        self.states.append(
            state
        )


class FakeSpeech:
    def __init__(
        self,
    ):
        self.stop_calls = 0

    def stop(
        self,
    ):
        self.stop_calls += 1


class FakeBodyController:
    def __init__(
        self,
    ):
        self.snapshots = []
        self.statuses = []

    def handle_runtime_status(
        self,
        status,
    ):
        self.statuses.append(
            status
        )

    def present_avatar_snapshot(
        self,
        snapshot,
    ):
        self.snapshots.append(
            snapshot
        )


class FakeWindow:
    """
    Lightweight receiver for KumaWindow's production scheduling methods.

    It intentionally avoids constructing QWidget/QApplication while exercising
    the exact production method bodies and the exact KumaWorker construction
    surface.
    """

    def __init__(
        self,
        *,
        typed_text="",
    ):
        self.input = (
            FakeInput(
                typed_text
            )
        )

        self.response = FakeLabel()
        self.status = FakeLabel()
        self.send_button = FakeButton()
        self.character = FakeCharacter()
        self.speech = FakeSpeech()
        self.body_controller = (
            FakeBodyController()
        )

        self.runtime = object()
        self.worker = None

        self.current_response = (
            "old response"
        )

        self.emotions = []
        self.resize_calls = 0
        self.cancel_calls = 0
        self.errors = []

    def _capture_user_emotion(
        self,
        message,
    ):
        self.emotions.append(
            message
        )

    def _resize_companion_panel_for_response(
        self,
    ):
        self.resize_calls += 1

    def request_confirmation(
        self,
        *_args,
        **_kwargs,
    ):
        raise AssertionError(
            "confirmation is not part of scheduling proof"
        )

    def on_status_changed(
        self,
        _status,
    ):
        pass

    def on_response(
        self,
        _response,
    ):
        pass

    def on_error(
        self,
        error,
    ):
        self.errors.append(
            error
        )

    def on_worker_finished(
        self,
    ):
        pass

    def _cancel_body_idle_reset(
        self,
    ):
        self.cancel_calls += 1

    def submit_user_turn_text(
        self,
        message,
        *,
        clear_input=False,
    ):
        return (
            KumaWindow.submit_user_turn_text(
                self,
                message,
                clear_input=clear_input,
            )
        )


@pytest.fixture(
    autouse=True
)
def fake_worker(
    monkeypatch,
):
    FakeWorker.created = []

    monkeypatch.setattr(
        window_module,
        "KumaWorker",
        FakeWorker,
    )


def test_stt_1f_window_exposes_one_shared_text_scheduler():
    signature = (
        inspect.signature(
            KumaWindow.submit_user_turn_text
        )
    )

    assert tuple(
        signature.parameters
    ) == (
        "self",
        "message",
        "clear_input",
    )

    assert (
        signature.parameters[
            "clear_input"
        ].kind
        is inspect.Parameter.KEYWORD_ONLY
    )

    assert (
        signature.parameters[
            "clear_input"
        ].default
        is False
    )


def test_stt_1f_keyboard_send_delegates_to_shared_scheduler():
    source = (
        inspect.getsource(
            KumaWindow.send_message
        )
    )

    assert (
        "self.submit_user_turn_text("
        in source
    )

    assert (
        "clear_input=True"
        in source
    )

    assert (
        "KumaWorker("
        not in source
    )

    assert (
        "self.runtime.run("
        not in source
    )


def test_stt_1f_shared_scheduler_owns_exact_worker_path():
    source = (
        inspect.getsource(
            KumaWindow.submit_user_turn_text
        )
    )

    assert (
        "worker = KumaWorker("
        in source
    )

    assert (
        "worker.start()"
        in source
    )

    assert (
        "self.runtime.run("
        not in source
    )

    assert (
        "KumaAgent("
        not in source
    )

    assert (
        "self.kuma.run("
        not in source
    )

    for marker in (
        "TEXT SOURCE != EXECUTION AUTHORITY",
        "TEXT TURN SCHEDULING != TOOL PERMISSION",
        "GUI SCHEDULER != RUNTIME OWNER",
        "AUTHORITY = NONE",
    ):
        assert marker in source


def test_stt_1f_keyboard_and_voice_admission_schedule_same_kumaworker_path():
    typed = (
        FakeWindow(
            typed_text="  hello kuma  "
        )
    )

    KumaWindow.send_message(
        typed
    )

    assert len(
        FakeWorker.created
    ) == 1

    typed_worker = (
        FakeWorker.created[0]
    )

    assert (
        typed_worker.message
        == "hello kuma"
    )

    assert (
        typed_worker.runtime
        is typed.runtime
    )

    assert (
        typed_worker.started
        is True
    )

    assert (
        typed.input.clear_calls
        == 1
    )

    assert typed.emotions == [
        "hello kuma",
    ]

    FakeWorker.created = []

    spoken = FakeWindow(
        typed_text=(
            "draft the user is still typing"
        )
    )

    admission = (
        KumaSTTTurnAdmission(
            submit_user_turn=(
                spoken.submit_user_turn_text
            ),
        )
    )

    transcript = (
        VoiceTranscript(
            text="hello kuma",
            is_final=True,
        )
    )

    assert (
        admission.admit(
            transcript
        )
        is True
    )

    assert len(
        FakeWorker.created
    ) == 1

    spoken_worker = (
        FakeWorker.created[0]
    )

    assert (
        spoken_worker.message
        == typed_worker.message
        == "hello kuma"
    )

    assert (
        spoken_worker.runtime
        is spoken.runtime
    )

    assert (
        spoken_worker.started
        is True
    )

    # Voice admission must not erase unrelated unsent keyboard text.
    assert (
        spoken.input.value
        == "draft the user is still typing"
    )

    assert (
        spoken.input.clear_calls
        == 0
    )

    assert spoken.emotions == [
        "hello kuma",
    ]

    assert (
        transcript.authority
        == "NONE"
    )


def test_stt_1f_busy_window_rejects_voice_before_turn_side_effects():
    subject = FakeWindow(
        typed_text="draft"
    )

    subject.worker = (
        BusyWorker()
    )

    admission = (
        KumaSTTTurnAdmission(
            submit_user_turn=(
                subject.submit_user_turn_text
            ),
        )
    )

    transcript = (
        VoiceTranscript(
            text="do not admit yet",
            is_final=True,
        )
    )

    assert (
        admission.admit(
            transcript
        )
        is False
    )

    assert FakeWorker.created == []

    assert (
        subject.speech.stop_calls
        == 0
    )

    assert (
        subject.emotions
        == []
    )

    assert (
        subject.input.value
        == "draft"
    )

    assert (
        subject.input.clear_calls
        == 0
    )

    assert (
        subject.current_response
        == "old response"
    )


def test_stt_1f_blank_scheduler_input_is_rejected_without_side_effects():
    subject = FakeWindow(
        typed_text="draft"
    )

    assert (
        subject.submit_user_turn_text(
            "   "
        )
        is False
    )

    assert FakeWorker.created == []
    assert subject.emotions == []
    assert subject.speech.stop_calls == 0
    assert subject.input.clear_calls == 0


def test_stt_1f_scheduler_requires_exact_text_and_bool_clear_flag():
    subject = FakeWindow()

    with pytest.raises(
        TypeError,
        match="message",
    ):
        subject.submit_user_turn_text(
            None
        )

    with pytest.raises(
        TypeError,
        match="clear_input",
    ):
        subject.submit_user_turn_text(
            "hello",
            clear_input=1,
        )

    assert FakeWorker.created == []


def test_stt_1f_admission_module_still_has_no_gui_or_runtime_import():
    source = Path(
        "app/voice/stt_turn_admission.py"
    ).read_text(
        encoding="utf-8"
    )

    for forbidden in (
        "from app.ui",
        "import app.ui",
        "from app.agent",
        "import app.agent",
        "KumaWindow",
        "KumaWorker",
        "KumaGUIRuntime",
        "KumaAgent",
    ):
        assert forbidden not in source


def test_stt_1f_window_has_no_recognizer_or_transcript_import():
    source = (
        WINDOW_SOURCE.read_text(
            encoding="utf-8"
        )
    )

    for forbidden in (
        "KumaSTTRecognizerOwner",
        "VoiceTranscript",
        "stt_recognizer_owner",
        "stt_turn_admission",
    ):
        assert forbidden not in source
