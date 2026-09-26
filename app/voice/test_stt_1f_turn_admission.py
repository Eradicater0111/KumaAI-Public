from __future__ import annotations

from dataclasses import (
    FrozenInstanceError,
)
import inspect
from pathlib import Path

import pytest

from app.voice.stt_turn_admission import (
    KumaSTTTurnAdmission,
    STT_TURN_ADMISSION_AUTHORITY_NONE,
)
from app.voice.voice_runtime import (
    VOICE_AUTHORITY_NONE,
    VoiceTranscript,
)


SOURCE = Path(
    "app/voice/stt_turn_admission.py"
)


def test_stt_1f_source_compiles_and_documents_zero_authority_boundary():
    source = (
        SOURCE.read_text(
            encoding="utf-8"
        )
    )

    compile(
        source,
        str(
            SOURCE
        ),
        "exec",
    )

    for marker in (
        "SPEECH RECOGNITION SUCCESS != USER TURN ADMISSION",
        "VoiceTranscript != USER TURN",
        "USER TURN ADMISSION != TOOL PERMISSION",
        "USER TURN ADMISSION != EXECUTION AUTHORITY",
        "ADMISSION CALLBACK != RUNTIME OWNER",
        "AUTHORITY = NONE",
    ):
        assert marker in source


def test_stt_1f_has_no_agent_gui_runtime_tool_or_recognizer_coupling():
    source = (
        SOURCE.read_text(
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
        "KumaAgent",
        "KumaGUIRuntime",
        "KumaWorker",
        "KumaIntegrationV2LiveTurnOwner",
        "KumaSTTRecognizerOwner",
        "send_message(",
        "QThread",
        "QProcess",
    ):
        assert forbidden not in source


def test_stt_1f_authority_is_none():
    subject = (
        KumaSTTTurnAdmission(
            submit_user_turn=(
                lambda _text: True
            ),
        )
    )

    assert (
        STT_TURN_ADMISSION_AUTHORITY_NONE
        == VOICE_AUTHORITY_NONE
        == "NONE"
    )

    assert (
        subject.authority
        == "NONE"
    )


def test_stt_1f_construction_performs_no_admission():
    calls = []

    subject = (
        KumaSTTTurnAdmission(
            submit_user_turn=(
                calls.append
            ),
        )
    )

    assert calls == []

    assert (
        subject.admission_in_progress
        is False
    )


def test_stt_1f_requires_callable_submission_boundary():
    with pytest.raises(
        TypeError,
        match="submit_user_turn",
    ):
        KumaSTTTurnAdmission(
            submit_user_turn=None
        )


def test_stt_1f_requires_real_voice_transcript():
    calls = []

    subject = (
        KumaSTTTurnAdmission(
            submit_user_turn=(
                lambda text:
                calls.append(
                    text
                )
                or True
            ),
        )
    )

    with pytest.raises(
        TypeError,
        match="VoiceTranscript",
    ):
        subject.admit(
            "hello"
        )

    assert calls == []


def test_stt_1f_nonfinal_transcript_is_not_admitted():
    calls = []

    subject = (
        KumaSTTTurnAdmission(
            submit_user_turn=(
                lambda text:
                calls.append(
                    text
                )
                or True
            ),
        )
    )

    transcript = (
        VoiceTranscript(
            text="still listening",
            is_final=False,
        )
    )

    assert (
        subject.admit(
            transcript
        )
        is False
    )

    assert calls == []


def test_stt_1f_rejects_any_transcript_whose_authority_is_not_none():
    calls = []

    subject = (
        KumaSTTTurnAdmission(
            submit_user_turn=(
                lambda text:
                calls.append(
                    text
                )
                or True
            ),
        )
    )

    transcript = (
        VoiceTranscript(
            text="hello kuma",
            is_final=True,
        )
    )

    object.__setattr__(
        transcript,
        "authority",
        "ELEVATED",
    )

    with pytest.raises(
        ValueError,
        match="authority",
    ):
        subject.admit(
            transcript
        )

    assert calls == []


def test_stt_1f_final_transcript_calls_submission_boundary_exactly_once():
    calls = []

    def submit(
        text,
    ):
        calls.append(
            text
        )

        return True

    subject = (
        KumaSTTTurnAdmission(
            submit_user_turn=submit,
        )
    )

    transcript = (
        VoiceTranscript(
            text="hello kuma",
            is_final=True,
        )
    )

    assert (
        subject.admit(
            transcript
        )
        is True
    )

    assert calls == [
        "hello kuma",
    ]

    assert (
        subject.admission_in_progress
        is False
    )


def test_stt_1f_false_submission_means_no_admitted_turn():
    calls = []

    def submit(
        text,
    ):
        calls.append(
            text
        )

        return False

    subject = (
        KumaSTTTurnAdmission(
            submit_user_turn=submit,
        )
    )

    transcript = (
        VoiceTranscript(
            text="hello kuma",
            is_final=True,
        )
    )

    assert (
        subject.admit(
            transcript
        )
        is False
    )

    assert calls == [
        "hello kuma",
    ]

    assert (
        subject.admission_in_progress
        is False
    )


def test_stt_1f_submission_result_must_be_strict_bool():
    subject = (
        KumaSTTTurnAdmission(
            submit_user_turn=(
                lambda _text: 1
            ),
        )
    )

    transcript = (
        VoiceTranscript(
            text="hello kuma",
            is_final=True,
        )
    )

    with pytest.raises(
        TypeError,
        match="return bool",
    ):
        subject.admit(
            transcript
        )

    assert (
        subject.admission_in_progress
        is False
    )


def test_stt_1f_callback_failure_releases_reentrancy_guard():
    calls = []

    def broken(
        text,
    ):
        calls.append(
            text
        )

        raise RuntimeError(
            "submission failed"
        )

    subject = (
        KumaSTTTurnAdmission(
            submit_user_turn=broken,
        )
    )

    transcript = (
        VoiceTranscript(
            text="hello kuma",
            is_final=True,
        )
    )

    with pytest.raises(
        RuntimeError,
        match="submission failed",
    ):
        subject.admit(
            transcript
        )

    assert calls == [
        "hello kuma",
    ]

    assert (
        subject.admission_in_progress
        is False
    )


def test_stt_1f_recursive_admission_is_rejected_without_second_submission():
    calls = []
    nested_results = []

    subject = None

    transcript = (
        VoiceTranscript(
            text="hello kuma",
            is_final=True,
        )
    )

    def submit(
        text,
    ):
        calls.append(
            text
        )

        nested_results.append(
            subject.admit(
                transcript
            )
        )

        return True

    subject = (
        KumaSTTTurnAdmission(
            submit_user_turn=submit,
        )
    )

    assert (
        subject.admit(
            transcript
        )
        is True
    )

    assert calls == [
        "hello kuma",
    ]

    assert nested_results == [
        False,
    ]

    assert (
        subject.admission_in_progress
        is False
    )


def test_stt_1f_does_not_content_deduplicate_distinct_spoken_turns():
    calls = []

    subject = (
        KumaSTTTurnAdmission(
            submit_user_turn=(
                lambda text:
                calls.append(
                    text
                )
                or True
            ),
        )
    )

    first = (
        VoiceTranscript(
            text="repeat this",
            is_final=True,
        )
    )

    second = (
        VoiceTranscript(
            text="repeat this",
            is_final=True,
        )
    )

    assert first is not second

    assert (
        subject.admit(
            first
        )
        is True
    )

    assert (
        subject.admit(
            second
        )
        is True
    )

    assert calls == [
        "repeat this",
        "repeat this",
    ]


def test_stt_1f_does_not_mutate_transcript():
    transcript = (
        VoiceTranscript(
            text="hello kuma",
            is_final=True,
        )
    )

    subject = (
        KumaSTTTurnAdmission(
            submit_user_turn=(
                lambda _text: True
            ),
        )
    )

    assert (
        subject.admit(
            transcript
        )
        is True
    )

    assert (
        transcript.text
        == "hello kuma"
    )

    assert (
        transcript.is_final
        is True
    )

    assert (
        transcript.authority
        == "NONE"
    )

    with pytest.raises(
        FrozenInstanceError
    ):
        transcript.text = (
            "changed"
        )


def test_stt_1f_admit_surface_has_no_authority_or_permission_parameter():
    signature = (
        inspect.signature(
            KumaSTTTurnAdmission.admit
        )
    )

    assert tuple(
        signature.parameters
    ) == (
        "self",
        "transcript",
    )


def test_stt_1f_constructor_has_only_caller_owned_submission_boundary():
    signature = (
        inspect.signature(
            KumaSTTTurnAdmission.__init__
        )
    )

    assert tuple(
        signature.parameters
    ) == (
        "self",
        "submit_user_turn",
    )

    assert (
        signature.parameters[
            "submit_user_turn"
        ].kind
        is inspect.Parameter.KEYWORD_ONLY
    )
