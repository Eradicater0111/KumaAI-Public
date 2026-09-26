"""
KUMA-VOICE-1F — live zero-authority Voice V1 presentation runtime.

This is the outer live attachment layer for the already-frozen Voice stack:

Voice-1B speech output truth
        +
Voice-1C microphone capture truth
        ↓
Voice-1D unified VoiceSnapshot
        ↓
Voice-1E pure AvatarSnapshot projection
        ↓
existing KumaBodyController presentation sink

Boundaries:

- LIVE VOICE RUNTIME != COGNITION
- LIVE VOICE RUNTIME != COMMAND AUTHORITY
- MICROPHONE CAPTURE != COMMAND
- PLAYBACK != MODEL CONTROL
- AVATAR PRESENTATION != PERMISSION
- LISTENING PRESENTATION REQUIRES CAPTURE TRUTH
- SPEAKING PRESENTATION REMAINS OWNED BY THE FROZEN WINDOW PLAYBACK PATH
- RUNTIME ATTACHMENT != MICROPHONE START
- RUNTIME ATTACHMENT != TRANSCRIPTION
- VOICE V1 AUTHORITY = NONE

Voice-1F deliberately does not auto-start microphone capture. Voice V1 provides
the truthful live attachment and lifecycle API, while a later recognition /
turn-taking phase may choose when capture should begin and end. This avoids
silently turning KUMA into an always-on microphone.

The frozen Avatar V1 window already owns truthful SPEAKING presentation from
the real playback signal. Voice-1F therefore adds only the previously missing
truthful LISTENING presentation path and does not duplicate that SPEAKING sink.
"""

from __future__ import annotations

from PySide6.QtCore import (
    QObject,
)

from app.ui.avatar_runtime import (
    AvatarMode,
)
from app.voice.microphone_capture import (
    KumaMicrophoneCapture,
)
from app.voice.voice_avatar_projection import (
    project_voice_snapshot_to_avatar,
)
from app.voice.voice_state_bridge import (
    KumaVoiceStateBridge,
)


class KumaVoiceLiveRuntime(
    QObject
):
    """
    Attach frozen Voice truth sources to the existing avatar presentation sink.

    The object owns no model, agent, memory, tool, permission, or execution
    surface. It also owns no transcription logic.

    Microphone capture remains explicit through start_listening(). Construction
    and attach_kuma_voice_runtime() never start or probe the microphone.
    """

    def __init__(
        self,
        speech_controller,
        body_controller,
        parent=None,
        *,
        microphone_capture=None,
    ):
        super().__init__(
            parent
        )

        if not hasattr(
            speech_controller,
            "voice_snapshot",
        ):
            raise TypeError(
                "speech_controller must expose voice_snapshot."
            )

        if not callable(
            getattr(
                body_controller,
                "present_avatar_snapshot",
                None,
            )
        ):
            raise TypeError(
                "body_controller must expose present_avatar_snapshot()."
            )

        self._speech_controller = (
            speech_controller
        )

        self._body_controller = (
            body_controller
        )

        self._microphone_capture = (
            microphone_capture
            if microphone_capture is not None
            else KumaMicrophoneCapture(
                parent=self
            )
        )

        self._bridge = (
            KumaVoiceStateBridge(
                speech_controller,
                self._microphone_capture,
                parent=self,
            )
        )

        self._last_voice_projection = (
            None
        )

        self._bridge.voice_state_changed.connect(
            self._on_voice_state_changed
        )

        # The frozen window connected these signals first during its
        # constructor. Because Voice-1F attaches from app/main.py afterward,
        # these reconciliation handlers run after the existing terminal
        # presentation and can truthfully restore LISTENING when capture is
        # still active.
        speech_controller.speech_finished.connect(
            self._reassert_listening_after_speech_terminal
        )

        speech_controller.speech_error.connect(
            self._reassert_listening_after_speech_terminal
        )

    @property
    def voice_snapshot(
        self,
    ):
        return (
            self._bridge.voice_snapshot
        )

    @property
    def microphone_capture(
        self,
    ):
        return (
            self._microphone_capture
        )

    @property
    def bridge(
        self,
    ):
        return (
            self._bridge
        )

    def probe_microphone(
        self,
    ) -> bool:
        """
        Discover microphone availability without starting capture.
        """

        return bool(
            self._microphone_capture
            .probe_availability()
        )

    def start_listening(
        self,
    ) -> bool:
        """
        Explicitly request truthful local microphone capture.

        LISTENING presentation is not published here. It can appear only after
        Voice-1C observes real non-empty microphone bytes and Voice-1E projects
        the resulting unified VoiceSnapshot.
        """

        return bool(
            self._microphone_capture
            .start_capture()
        )

    def stop_listening(
        self,
    ) -> bool:
        """
        Stop microphone capture.

        Voice-1F does not fabricate an IDLE AvatarSnapshot on release because
        doing so could overwrite a newer non-voice presentation owned by the
        window. The caller that owns conversational turn-taking owns the next
        semantic presentation after capture stops.
        """

        return bool(
            self._microphone_capture
            .stop_capture()
        )

    def close(
        self,
    ) -> None:
        """
        Explicit application-shutdown boundary.
        """

        self._microphone_capture.close()

    def _present_listening_if_owned(
        self,
        snapshot,
    ) -> bool:
        projection = (
            project_voice_snapshot_to_avatar(
                snapshot
            )
        )

        self._last_voice_projection = (
            projection
        )

        if (
            projection is None
            or projection.mode
            != AvatarMode.LISTENING
        ):
            return False

        self._body_controller.present_avatar_snapshot(
            projection
        )

        return True

    def _on_voice_state_changed(
        self,
        snapshot,
    ) -> None:
        """
        Add the missing live LISTENING path only.

        SPEAKING remains bound to the frozen window's real speech_started signal,
        avoiding a duplicate presentation sink for the same playback event.
        """

        self._present_listening_if_owned(
            snapshot
        )

    def _reassert_listening_after_speech_terminal(
        self,
        *_args,
    ) -> None:
        """
        Reconcile active capture after the frozen terminal speech presentation.

        If microphone capture is still physically active when playback finishes
        or errors, the unified current snapshot projects LISTENING and this
        handler restores that truthful privacy/presentation signal.
        """

        self._present_listening_if_owned(
            self._bridge.voice_snapshot
        )


def attach_kuma_voice_runtime(
    window,
) -> KumaVoiceLiveRuntime:
    """
    Attach one Voice V1 live runtime to an already-constructed KumaWindow.

    This is intentionally an outer bootstrap seam. It does not modify or
    subclass KumaWindow and it does not start microphone capture.
    """

    existing = getattr(
        window,
        "_kuma_voice_runtime",
        None,
    )

    if existing is not None:
        if not isinstance(
            existing,
            KumaVoiceLiveRuntime,
        ):
            raise RuntimeError(
                "window already has an incompatible voice runtime."
            )

        return existing

    speech_controller = getattr(
        window,
        "speech",
        None,
    )

    body_controller = getattr(
        window,
        "body_controller",
        None,
    )

    if speech_controller is None:
        raise TypeError(
            "window must expose speech."
        )

    if body_controller is None:
        raise TypeError(
            "window must expose body_controller."
        )

    runtime = (
        KumaVoiceLiveRuntime(
            speech_controller,
            body_controller,
            parent=window,
        )
    )

    window._kuma_voice_runtime = (
        runtime
    )

    return runtime
