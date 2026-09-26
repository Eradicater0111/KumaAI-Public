"""
KUMA STT-1F — outer production binding from recognizer observations to the
explicit textual user-turn admission boundary.

This module is composition only.

It connects one KumaSTTRecognizerOwner.transcript_ready signal to a
zero-authority, one-shot conversational admission gate. Signal delivery alone
never creates a user turn. A caller must explicitly request admission for one
future transcript before the binding may present it to KumaSTTTurnAdmission.
The admission callback is supplied by the GUI's ordinary textual scheduling
seam.

Construction does not:
- start the recognizer,
- load a model,
- open the microphone,
- admit a transcript,
- create a user turn,
- call KumaAgent,
- call tools,
- grant permission.

RECOGNIZER CONSTRUCTION != RECOGNIZER START
SIGNAL CONNECTION != USER TURN
ADMISSION REQUEST != MICROPHONE CONSENT
ADMISSION REQUEST != RECOGNIZER START
ADMISSION REQUEST != USER TURN
RECOGNIZER RESULT != USER TURN
VoiceTranscript != USER TURN
USER TURN ADMISSION != TOOL PERMISSION
BINDING OWNER != EXECUTION AUTHORITY
AUTHORITY = NONE
"""

from __future__ import annotations

from pathlib import Path

from app.voice.stt_recognizer_owner import (
    KumaSTTRecognizerOwner,
)
from app.voice.stt_turn_admission import (
    KumaSTTTurnAdmission,
    STT_TURN_ADMISSION_AUTHORITY_NONE,
)


STT_LIVE_TURN_BINDING_AUTHORITY_NONE = (
    STT_TURN_ADMISSION_AUTHORITY_NONE
)


DEFAULT_STT_MODEL_PATH = (
    Path.home()
    / ".kuma"
    / "models"
    / "stt"
    / "mlx-whisper"
    / "whisper-tiny-mlx"
)


class KumaSTTLiveTurnBinding:
    """
    Own exactly one recognizer-signal → transcript-admission connection.

    The binding owns the lifetime of the recognizer supplied to it, whether
    injected for testing/composition or constructed locally.
    """

    def __init__(
        self,
        *,
        window,
        recognizer=None,
    ):
        submit_user_turn = getattr(
            window,
            "submit_user_turn_text",
            None,
        )

        if not callable(
            submit_user_turn
        ):
            raise TypeError(
                "window must expose callable submit_user_turn_text."
            )

        if recognizer is None:
            recognizer = (
                KumaSTTRecognizerOwner(
                    model_path=(
                        DEFAULT_STT_MODEL_PATH
                    ),
                )
            )

        transcript_signal = getattr(
            recognizer,
            "transcript_ready",
            None,
        )

        connect = getattr(
            transcript_signal,
            "connect",
            None,
        )

        disconnect = getattr(
            transcript_signal,
            "disconnect",
            None,
        )

        shutdown = getattr(
            recognizer,
            "shutdown",
            None,
        )

        if not callable(
            connect
        ):
            raise TypeError(
                "recognizer must expose connectable transcript_ready."
            )

        if not callable(
            disconnect
        ):
            raise TypeError(
                "recognizer transcript_ready must support disconnect."
            )

        if not callable(
            shutdown
        ):
            raise TypeError(
                "recognizer must expose callable shutdown."
            )

        self._window = window
        self._recognizer = recognizer

        self._admission = (
            KumaSTTTurnAdmission(
                submit_user_turn=(
                    submit_user_turn
                ),
            )
        )

        self._closed = False
        self._user_turn_admission_armed = False

        # Retain the exact bound method object used for connection so
        # disconnect() is deterministic for both Qt and test signals.
        self._transcript_slot = (
            self._on_transcript_ready
        )

        transcript_signal.connect(
            self._transcript_slot
        )

    @property
    def authority(
        self,
    ) -> str:
        return (
            STT_LIVE_TURN_BINDING_AUTHORITY_NONE
        )

    @property
    def recognizer(
        self,
    ):
        return self._recognizer

    @property
    def admission(
        self,
    ) -> KumaSTTTurnAdmission:
        return self._admission

    @property
    def closed(
        self,
    ) -> bool:
        return self._closed

    @property
    def user_turn_admission_pending(
        self,
    ) -> bool:
        return (
            self._user_turn_admission_armed
        )

    def request_user_turn_admission(
        self,
    ) -> bool:
        """
        Explicitly arm admission for exactly one future transcript signal.

        This does not start recognition, open the microphone, create a turn,
        or grant tool/execution authority.
        """

        if (
            self._closed
            or self._user_turn_admission_armed
        ):
            return False

        self._user_turn_admission_armed = (
            True
        )

        return True

    def cancel_user_turn_admission(
        self,
    ) -> bool:
        """Cancel one pending explicit user-turn admission request."""

        if (
            self._closed
            or not self._user_turn_admission_armed
        ):
            return False

        self._user_turn_admission_armed = (
            False
        )

        return True

    def _on_transcript_ready(
        self,
        transcript,
    ) -> bool:
        if (
            self._closed
            or not self._user_turn_admission_armed
        ):
            return False

        # Consume the explicit request before admission. A non-final
        # transcript, a busy textual scheduler, or an admission error must
        # never leave authority-like state armed for a later transcript.
        self._user_turn_admission_armed = (
            False
        )

        return self._admission.admit(
            transcript
        )

    def close(
        self,
    ) -> None:
        if self._closed:
            return

        self._closed = True
        self._user_turn_admission_armed = False

        signal = (
            self._recognizer
            .transcript_ready
        )

        try:
            signal.disconnect(
                self._transcript_slot
            )

        except (
            RuntimeError,
            TypeError,
        ):
            # Shutdown must remain best-effort even if Qt has already
            # destroyed or disconnected the signal endpoint.
            pass

        self._recognizer.shutdown()


def attach_kuma_stt_turn_admission(
    window,
    *,
    recognizer=None,
) -> KumaSTTLiveTurnBinding:
    """
    Attach exactly one STT live-turn binding to an existing GUI window.

    Attaching does not start recognition or microphone capture.
    """

    existing = getattr(
        window,
        "_kuma_stt_turn_binding",
        None,
    )

    if existing is not None:
        if not isinstance(
            existing,
            KumaSTTLiveTurnBinding,
        ):
            raise RuntimeError(
                "window already has an incompatible STT turn binding."
            )

        if (
            recognizer is not None
            and existing.recognizer
            is not recognizer
        ):
            raise RuntimeError(
                "window already owns a different STT recognizer."
            )

        return existing

    binding = (
        KumaSTTLiveTurnBinding(
            window=window,
            recognizer=recognizer,
        )
    )

    window._kuma_stt_turn_binding = (
        binding
    )

    return binding
