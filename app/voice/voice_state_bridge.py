"""
KUMA-VOICE-1D — zero-authority unified voice-state bridge.

The bridge consumes the already-truthful output observation from Voice-1B and
the already-truthful microphone observation from Voice-1C, then projects one
immutable VoiceSnapshot.

Boundaries:

- INPUT OBSERVATION != OUTPUT STATE
- OUTPUT OBSERVATION != INPUT STATE
- INPUT UPDATE MUST PRESERVE OUTPUT TRUTH
- OUTPUT UPDATE MUST PRESERVE INPUT TRUTH
- BRIDGE SNAPSHOT != COMMAND
- BRIDGE SNAPSHOT != PERMISSION
- BRIDGE SNAPSHOT != COGNITION
- BRIDGE SNAPSHOT != AVATAR STATE
- BRIDGE AUTHORITY = NONE

Voice-1D performs no microphone capture, playback, transcription, persistence,
network access, model work, agent work, permission decisions, or UI/avatar
projection. It owns only the composition of independently observed I/O truth.
"""

from __future__ import annotations

from PySide6.QtCore import (
    QObject,
    Signal,
)

from app.voice.microphone_capture import (
    MicrophoneCaptureObservation,
)
from app.voice.voice_runtime import (
    VoiceSnapshot,
)


class KumaVoiceStateBridge(
    QObject
):
    """
    Compose Voice-1B output truth and Voice-1C input truth.

    Source ownership is intentionally disjoint:

    - input_mode / microphone_active come only from MicrophoneCaptureObservation
    - output_mode / playback_active come only from the Voice-1B VoiceSnapshot
    - transcript is retained from the bridge's current snapshot and is not
      authored, replaced, interpreted, or routed by Voice-1D
    - reason describes the source event that most recently changed the bridge

    The bridge never writes back into either source.
    """

    voice_state_changed = Signal(
        object
    )

    def __init__(
        self,
        speech_controller,
        microphone_capture,
        parent=None,
    ):
        super().__init__(
            parent
        )

        output_snapshot = (
            speech_controller.voice_snapshot
        )

        input_observation = (
            microphone_capture.observation
        )

        self._require_output_snapshot(
            output_snapshot
        )

        self._require_input_observation(
            input_observation
        )

        self._speech_controller = (
            speech_controller
        )

        self._microphone_capture = (
            microphone_capture
        )

        self._input_observation = (
            input_observation
        )

        self._output_snapshot = (
            output_snapshot
        )

        self._voice_snapshot = (
            VoiceSnapshot(
                input_mode=(
                    input_observation.input_mode
                ),
                output_mode=(
                    output_snapshot.output_mode
                ),
                microphone_active=(
                    input_observation.microphone_active
                ),
                playback_active=(
                    output_snapshot.playback_active
                ),
                transcript=(
                    output_snapshot.transcript
                ),
                reason="",
            )
        )

        speech_controller.voice_state_changed.connect(
            self._on_output_state_changed
        )

        microphone_capture.capture_state_changed.connect(
            self._on_input_state_changed
        )

    @property
    def voice_snapshot(
        self,
    ) -> VoiceSnapshot:
        return self._voice_snapshot

    @staticmethod
    def _require_output_snapshot(
        snapshot,
    ) -> None:
        if not isinstance(
            snapshot,
            VoiceSnapshot,
        ):
            raise TypeError(
                "output source must publish VoiceSnapshot."
            )

    @staticmethod
    def _require_input_observation(
        observation,
    ) -> None:
        if not isinstance(
            observation,
            MicrophoneCaptureObservation,
        ):
            raise TypeError(
                "input source must publish "
                "MicrophoneCaptureObservation."
            )

    def _compose(
        self,
        *,
        input_observation,
        output_snapshot,
        reason,
    ) -> VoiceSnapshot:
        self._require_input_observation(
            input_observation
        )

        self._require_output_snapshot(
            output_snapshot
        )

        return VoiceSnapshot(
            input_mode=(
                input_observation.input_mode
            ),
            output_mode=(
                output_snapshot.output_mode
            ),
            microphone_active=(
                input_observation.microphone_active
            ),
            playback_active=(
                output_snapshot.playback_active
            ),
            transcript=(
                self._voice_snapshot.transcript
            ),
            reason=reason,
        )

    def _publish_if_changed(
        self,
        snapshot,
    ) -> VoiceSnapshot:
        self._require_output_snapshot(
            snapshot
        )

        if (
            snapshot
            == self._voice_snapshot
        ):
            return self._voice_snapshot

        self._voice_snapshot = (
            snapshot
        )

        self.voice_state_changed.emit(
            snapshot
        )

        return snapshot

    def _on_input_state_changed(
        self,
        observation,
    ) -> None:
        self._require_input_observation(
            observation
        )

        self._input_observation = (
            observation
        )

        snapshot = self._compose(
            input_observation=observation,
            output_snapshot=(
                self._output_snapshot
            ),
            reason=observation.reason,
        )

        self._publish_if_changed(
            snapshot
        )

    def _on_output_state_changed(
        self,
        snapshot,
    ) -> None:
        self._require_output_snapshot(
            snapshot
        )

        self._output_snapshot = (
            snapshot
        )

        unified = self._compose(
            input_observation=(
                self._input_observation
            ),
            output_snapshot=snapshot,
            reason=snapshot.reason,
        )

        self._publish_if_changed(
            unified
        )
