from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from PySide6.QtCore import (
    QCoreApplication,
)

import app.ui.window as window_module
import app.voice.stt_live_turn_binding as binding_module

from app.ui.window import (
    KumaWindow,
)
from app.voice.stt_live_turn_binding import (
    DEFAULT_STT_MODEL_PATH,
    KumaSTTLiveTurnBinding,
    STT_LIVE_TURN_BINDING_AUTHORITY_NONE,
    attach_kuma_stt_turn_admission,
)
from app.voice.stt_recognizer_owner import (
    KumaSTTRecognizerOwner,
)
from app.voice.voice_runtime import (
    VOICE_AUTHORITY_NONE,
    VoiceTranscript,
)


MAIN = Path(
    "app/main.py"
)

BINDING_SOURCE = Path(
    "app/voice/stt_live_turn_binding.py"
)


class FakeSignal:
    def __init__(
        self,
    ):
        self.slots = []

    def connect(
        self,
        slot,
    ):
        self.slots.append(
            slot
        )

    def disconnect(
        self,
        slot,
    ):
        self.slots.remove(
            slot
        )

    def emit(
        self,
        value,
    ):
        return [
            slot(
                value
            )
            for slot
            in tuple(
                self.slots
            )
        ]


class FakeRecognizer:
    def __init__(
        self,
        *,
        model_path=None,
    ):
        self.model_path = (
            model_path
        )

        self.transcript_ready = (
            FakeSignal()
        )

        self.start_calls = 0
        self.shutdown_calls = 0

    def start(
        self,
    ):
        self.start_calls += 1

        raise AssertionError(
            "binding construction must not start recognizer"
        )

    def shutdown(
        self,
    ):
        self.shutdown_calls += 1


class FakeWorkerSignal:
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
            FakeWorkerSignal()
        )

        self.response_finished = (
            FakeWorkerSignal()
        )

        self.error = (
            FakeWorkerSignal()
        )

        self.finished = (
            FakeWorkerSignal()
        )

        self.running = False
        self.started = False

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

        self.response = (
            FakeLabel()
        )

        self.status = (
            FakeLabel()
        )

        self.send_button = (
            FakeButton()
        )

        self.character = (
            FakeCharacter()
        )

        self.speech = (
            FakeSpeech()
        )

        self.body_controller = (
            FakeBodyController()
        )

        self.runtime = object()
        self.worker = None
        self.current_response = ""

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
    scope="module",
    autouse=True,
)
def qt_core_application():
    app = (
        QCoreApplication.instance()
    )

    if app is None:
        app = QCoreApplication(
            []
        )

    return app


@pytest.fixture(
    autouse=True,
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


def test_stt_1f_live_binding_documents_zero_authority_composition():
    source = (
        BINDING_SOURCE.read_text(
            encoding="utf-8"
        )
    )

    compile(
        source,
        str(
            BINDING_SOURCE
        ),
        "exec",
    )

    for marker in (
        "RECOGNIZER CONSTRUCTION != RECOGNIZER START",
        "SIGNAL CONNECTION != USER TURN",
        "ADMISSION REQUEST != MICROPHONE CONSENT",
        "ADMISSION REQUEST != RECOGNIZER START",
        "ADMISSION REQUEST != USER TURN",
        "RECOGNIZER RESULT != USER TURN",
        "VoiceTranscript != USER TURN",
        "USER TURN ADMISSION != TOOL PERMISSION",
        "BINDING OWNER != EXECUTION AUTHORITY",
        "AUTHORITY = NONE",
    ):
        assert marker in source


def test_stt_1f_live_binding_has_no_agent_ui_tool_or_provider_import():
    source = (
        BINDING_SOURCE.read_text(
            encoding="utf-8"
        )
    )

    for forbidden in (
        "from app.agent",
        "import app.agent",
        "from app.ui",
        "import app.ui",
        "from app.tools",
        "import app.tools",
        "mlx_whisper",
        "numpy",
        "huggingface_hub",
    ):
        assert forbidden not in source


def test_stt_1f_binding_authority_remains_none():
    recognizer = (
        FakeRecognizer()
    )

    window = (
        FakeWindow()
    )

    subject = (
        KumaSTTLiveTurnBinding(
            window=window,
            recognizer=recognizer,
        )
    )

    try:
        assert (
            STT_LIVE_TURN_BINDING_AUTHORITY_NONE
            == VOICE_AUTHORITY_NONE
            == "NONE"
        )

        assert (
            subject.authority
            == "NONE"
        )

        assert (
            subject.admission.authority
            == "NONE"
        )

    finally:
        subject.close()


def test_stt_1f_binding_construction_connects_but_never_starts_recognizer():
    recognizer = (
        FakeRecognizer()
    )

    subject = (
        KumaSTTLiveTurnBinding(
            window=FakeWindow(),
            recognizer=recognizer,
        )
    )

    try:
        assert (
            recognizer.start_calls
            == 0
        )

        assert len(
            recognizer.transcript_ready.slots
        ) == 1

        assert (
            subject.closed
            is False
        )

        assert (
            subject.user_turn_admission_pending
            is False
        )

    finally:
        subject.close()


def test_stt_1f_admission_request_is_one_shot_and_has_no_side_effects():
    recognizer = (
        FakeRecognizer()
    )

    subject = (
        KumaSTTLiveTurnBinding(
            window=FakeWindow(),
            recognizer=recognizer,
        )
    )

    try:
        assert (
            subject.request_user_turn_admission()
            is True
        )

        assert (
            subject.user_turn_admission_pending
            is True
        )

        assert (
            subject.request_user_turn_admission()
            is False
        )

        assert (
            recognizer.start_calls
            == 0
        )

        assert (
            FakeWorker.created
            == []
        )

    finally:
        subject.close()


def test_stt_1f_cancel_user_turn_admission_is_explicit_and_strict():
    subject = (
        KumaSTTLiveTurnBinding(
            window=FakeWindow(),
            recognizer=FakeRecognizer(),
        )
    )

    try:
        assert (
            subject.cancel_user_turn_admission()
            is False
        )

        assert (
            subject.request_user_turn_admission()
            is True
        )

        assert (
            subject.cancel_user_turn_admission()
            is True
        )

        assert (
            subject.user_turn_admission_pending
            is False
        )

        assert (
            subject.cancel_user_turn_admission()
            is False
        )

    finally:
        subject.close()


def test_stt_1f_default_attachment_constructs_owner_without_starting(
    monkeypatch,
):
    created = []

    class DefaultRecognizer(
        FakeRecognizer
    ):
        def __init__(
            self,
            *,
            model_path,
        ):
            super().__init__(
                model_path=model_path
            )

            created.append(
                self
            )

    monkeypatch.setattr(
        binding_module,
        "KumaSTTRecognizerOwner",
        DefaultRecognizer,
    )

    window = (
        FakeWindow()
    )

    subject = (
        attach_kuma_stt_turn_admission(
            window
        )
    )

    try:
        assert len(
            created
        ) == 1

        recognizer = (
            created[0]
        )

        assert (
            recognizer.start_calls
            == 0
        )

        assert (
            recognizer.model_path
            == DEFAULT_STT_MODEL_PATH
        )

        assert (
            subject.recognizer
            is recognizer
        )

        assert (
            window._kuma_stt_turn_binding
            is subject
        )

    finally:
        subject.close()


def test_stt_1f_default_model_path_matches_frozen_stt_1e_location():
    assert (
        DEFAULT_STT_MODEL_PATH
        == (
            Path.home()
            / ".kuma"
            / "models"
            / "stt"
            / "mlx-whisper"
            / "whisper-tiny-mlx"
        )
    )


def test_stt_1f_unarmed_real_recognizer_signal_never_schedules_worker(
    tmp_path,
):
    recognizer = (
        KumaSTTRecognizerOwner(
            model_path=(
                tmp_path
                / "model-not-loaded"
            )
        )
    )

    window = (
        FakeWindow(
            typed_text="draft"
        )
    )

    subject = (
        KumaSTTLiveTurnBinding(
            window=window,
            recognizer=recognizer,
        )
    )

    try:
        recognizer.transcript_ready.emit(
            VoiceTranscript(
                text="must not become a turn",
                is_final=True,
            )
        )

        assert (
            FakeWorker.created
            == []
        )

        assert (
            subject.user_turn_admission_pending
            is False
        )

        assert (
            window.input.value
            == "draft"
        )

    finally:
        subject.close()


def test_stt_1f_armed_real_recognizer_signal_schedules_exactly_one_worker(
    tmp_path,
):
    recognizer = (
        KumaSTTRecognizerOwner(
            model_path=(
                tmp_path
                / "model-not-loaded"
            )
        )
    )

    window = (
        FakeWindow(
            typed_text="draft"
        )
    )

    subject = (
        KumaSTTLiveTurnBinding(
            window=window,
            recognizer=recognizer,
        )
    )

    transcript = (
        VoiceTranscript(
            text="hello kuma",
            is_final=True,
        )
    )

    try:
        assert (
            subject.request_user_turn_admission()
            is True
        )

        recognizer.transcript_ready.emit(
            transcript
        )

        assert (
            subject.user_turn_admission_pending
            is False
        )

        assert len(
            FakeWorker.created
        ) == 1

        worker = (
            FakeWorker.created[0]
        )

        assert (
            worker.message
            == "hello kuma"
        )

        assert (
            worker.runtime
            is window.runtime
        )

        assert (
            worker.started
            is True
        )

        assert (
            transcript.authority
            == "NONE"
        )

        assert (
            window.input.value
            == "draft"
        )

        assert (
            window.input.clear_calls
            == 0
        )

        recognizer.transcript_ready.emit(
            VoiceTranscript(
                text="second signal",
                is_final=True,
            )
        )

        assert len(
            FakeWorker.created
        ) == 1

    finally:
        subject.close()


def test_stt_1f_real_signal_nonfinal_transcript_consumes_arm_without_turn(
    tmp_path,
):
    recognizer = (
        KumaSTTRecognizerOwner(
            model_path=(
                tmp_path
                / "model-not-loaded"
            )
        )
    )

    window = (
        FakeWindow()
    )

    subject = (
        KumaSTTLiveTurnBinding(
            window=window,
            recognizer=recognizer,
        )
    )

    try:
        assert (
            subject.request_user_turn_admission()
            is True
        )

        recognizer.transcript_ready.emit(
            VoiceTranscript(
                text="still listening",
                is_final=False,
            )
        )

        assert (
            subject.user_turn_admission_pending
            is False
        )

        assert (
            FakeWorker.created
            == []
        )

        assert (
            window.emotions
            == []
        )

        recognizer.transcript_ready.emit(
            VoiceTranscript(
                text="later final must remain blocked",
                is_final=True,
            )
        )

        assert (
            FakeWorker.created
            == []
        )

    finally:
        subject.close()


def test_stt_1f_real_signal_busy_window_consumes_arm_without_turn(
    tmp_path,
):
    recognizer = (
        KumaSTTRecognizerOwner(
            model_path=(
                tmp_path
                / "model-not-loaded"
            )
        )
    )

    window = (
        FakeWindow(
            typed_text="draft"
        )
    )

    window.worker = (
        BusyWorker()
    )

    subject = (
        KumaSTTLiveTurnBinding(
            window=window,
            recognizer=recognizer,
        )
    )

    try:
        assert (
            subject.request_user_turn_admission()
            is True
        )

        recognizer.transcript_ready.emit(
            VoiceTranscript(
                text="do not overlap",
                is_final=True,
            )
        )

        assert (
            subject.user_turn_admission_pending
            is False
        )

        assert (
            FakeWorker.created
            == []
        )

        assert (
            window.emotions
            == []
        )

        assert (
            window.speech.stop_calls
            == 0
        )

        assert (
            window.input.value
            == "draft"
        )

        window.worker = None

        recognizer.transcript_ready.emit(
            VoiceTranscript(
                text="must not leak into later turn",
                is_final=True,
            )
        )

        assert (
            FakeWorker.created
            == []
        )

    finally:
        subject.close()


def test_stt_1f_attachment_is_idempotent_and_does_not_double_connect():
    recognizer = (
        FakeRecognizer()
    )

    window = (
        FakeWindow()
    )

    first = (
        attach_kuma_stt_turn_admission(
            window,
            recognizer=recognizer,
        )
    )

    second = (
        attach_kuma_stt_turn_admission(
            window,
            recognizer=recognizer,
        )
    )

    try:
        assert (
            first
            is second
        )

        assert len(
            recognizer.transcript_ready.slots
        ) == 1

        assert (
            first.request_user_turn_admission()
            is True
        )

        recognizer.transcript_ready.emit(
            VoiceTranscript(
                text="once only",
                is_final=True,
            )
        )

        assert len(
            FakeWorker.created
        ) == 1

        assert (
            FakeWorker.created[0].message
            == "once only"
        )

    finally:
        first.close()


def test_stt_1f_attachment_rejects_different_second_recognizer():
    first_recognizer = (
        FakeRecognizer()
    )

    second_recognizer = (
        FakeRecognizer()
    )

    window = (
        FakeWindow()
    )

    subject = (
        attach_kuma_stt_turn_admission(
            window,
            recognizer=first_recognizer,
        )
    )

    try:
        with pytest.raises(
            RuntimeError,
            match="different STT recognizer",
        ):
            attach_kuma_stt_turn_admission(
                window,
                recognizer=second_recognizer,
            )

    finally:
        subject.close()


def test_stt_1f_repeated_identical_text_requires_two_explicit_arms():
    recognizer = (
        FakeRecognizer()
    )

    window = (
        FakeWindow()
    )

    subject = (
        KumaSTTLiveTurnBinding(
            window=window,
            recognizer=recognizer,
        )
    )

    try:
        transcript_one = (
            VoiceTranscript(
                text="repeat",
                is_final=True,
            )
        )

        transcript_two = (
            VoiceTranscript(
                text="repeat",
                is_final=True,
            )
        )

        assert (
            subject.request_user_turn_admission()
            is True
        )

        recognizer.transcript_ready.emit(
            transcript_one
        )

        assert len(
            FakeWorker.created
        ) == 1

        first_worker = (
            FakeWorker.created[0]
        )

        first_worker.running = False
        window.worker = None

        # Same transcript text without another explicit arm cannot
        # create another user turn.
        recognizer.transcript_ready.emit(
            transcript_two
        )

        assert len(
            FakeWorker.created
        ) == 1

        assert (
            subject.request_user_turn_admission()
            is True
        )

        recognizer.transcript_ready.emit(
            transcript_two
        )

        assert [
            worker.message
            for worker
            in FakeWorker.created
        ] == [
            "repeat",
            "repeat",
        ]

    finally:
        subject.close()


def test_stt_1f_close_disconnects_clears_arm_and_shuts_down_recognizer():
    recognizer = (
        FakeRecognizer()
    )

    window = (
        FakeWindow()
    )

    subject = (
        KumaSTTLiveTurnBinding(
            window=window,
            recognizer=recognizer,
        )
    )

    assert len(
        recognizer.transcript_ready.slots
    ) == 1

    assert (
        subject.request_user_turn_admission()
        is True
    )

    assert (
        subject.user_turn_admission_pending
        is True
    )

    subject.close()

    assert (
        subject.closed
        is True
    )

    assert (
        subject.user_turn_admission_pending
        is False
    )

    assert (
        subject.request_user_turn_admission()
        is False
    )

    assert (
        subject.cancel_user_turn_admission()
        is False
    )

    assert (
        recognizer.shutdown_calls
        == 1
    )

    assert (
        recognizer.transcript_ready.slots
        == []
    )

    recognizer.transcript_ready.emit(
        VoiceTranscript(
            text="after close",
            is_final=True,
        )
    )

    assert (
        FakeWorker.created
        == []
    )

    subject.close()

    assert (
        recognizer.shutdown_calls
        == 1
    )


def test_stt_1f_binding_requires_window_submission_seam():
    with pytest.raises(
        TypeError,
        match="submit_user_turn_text",
    ):
        KumaSTTLiveTurnBinding(
            window=object(),
            recognizer=(
                FakeRecognizer()
            ),
        )


def test_stt_1f_binding_requires_recognizer_signal_and_shutdown():
    class MissingSignal:
        def shutdown(
            self,
        ):
            pass

    with pytest.raises(
        TypeError,
        match="transcript_ready",
    ):
        KumaSTTLiveTurnBinding(
            window=FakeWindow(),
            recognizer=MissingSignal(),
        )

    class MissingShutdown:
        transcript_ready = (
            FakeSignal()
        )

    with pytest.raises(
        TypeError,
        match="shutdown",
    ):
        KumaSTTLiveTurnBinding(
            window=FakeWindow(),
            recognizer=MissingShutdown(),
        )


def test_stt_1f_binding_and_attach_have_no_authority_parameter():
    binding_signature = (
        inspect.signature(
            KumaSTTLiveTurnBinding.__init__
        )
    )

    attach_signature = (
        inspect.signature(
            attach_kuma_stt_turn_admission
        )
    )

    assert (
        "authority"
        not in binding_signature.parameters
    )

    assert (
        "authority"
        not in attach_signature.parameters
    )


def test_stt_1f_main_composes_binding_once_without_starting_recognizer():
    source = (
        MAIN.read_text(
            encoding="utf-8"
        )
    )

    assert source.count(
        "attach_kuma_stt_turn_admission("
    ) == 1

    assert (
        "stt_turn_binding.close"
        in source
    )

    assert (
        "recognizer.start("
        not in source
    )

    assert (
        ".recognizer.start("
        not in source
    )

    assert (
        "start_microphone("
        not in source
    )

    assert (
        "start_capture("
        not in source
    )


def test_stt_1f_main_preserves_existing_voice_runtime_attachment():
    source = (
        MAIN.read_text(
            encoding="utf-8"
        )
    )

    assert source.count(
        "attach_kuma_voice_runtime("
    ) == 1

    assert (
        "voice_runtime.close"
        in source
    )


def test_stt_1f_real_owner_construction_does_not_start_process(
    tmp_path,
):
    owner = (
        KumaSTTRecognizerOwner(
            model_path=(
                tmp_path
                / "never-loaded"
            )
        )
    )

    try:
        assert (
            owner.service_ready
            is False
        )

        assert (
            owner.request_pending
            is False
        )

        assert (
            getattr(
                owner,
                "_service",
            )
            is None
        )

    finally:
        owner.shutdown()
