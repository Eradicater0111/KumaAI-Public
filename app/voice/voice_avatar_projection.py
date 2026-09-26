"""
KUMA-VOICE-1E — pure truthful voice-to-avatar semantic projection.

This module converts an already-unified VoiceSnapshot into an optional
AvatarSnapshot presentation claim.

Boundaries:

- VOICE SNAPSHOT != AVATAR AUTHORITY
- VOICE PRESENTATION != COGNITION
- MICROPHONE CAPTURE != COMMAND
- PLAYBACK != MODEL CONTROL
- LISTENING PRESENTATION REQUIRES REAL CAPTURE TRUTH
- SPEAKING PRESENTATION REQUIRES REAL PLAYBACK TRUTH
- PRESENTATION PRECEDENCE != I/O TRUTH LOSS
- VOICE-AVATAR PROJECTION AUTHORITY = NONE

The avatar has one semantic mode while VoiceSnapshot can truthfully represent
capture and playback at the same time. When both are active, SPEAKING receives
presentation precedence because active playback must keep speech_active=True.
The underlying VoiceSnapshot remains the authoritative representation of both
simultaneous I/O truths.

Inactive, synthesizing, unavailable, and error-only voice states return None.
Voice-1E therefore does not fabricate IDLE, THINKING, SUCCESS, ERROR, or other
presentation state and cannot overwrite unrelated avatar lifecycle semantics.
"""

from __future__ import annotations

from app.ui.avatar_runtime import (
    AvatarExpression,
    AvatarGaze,
    AvatarMode,
    AvatarSnapshot,
)
from app.voice.voice_runtime import (
    VoiceInputMode,
    VoiceOutputMode,
    VoiceSnapshot,
)


def project_voice_snapshot_to_avatar(
    snapshot: VoiceSnapshot,
) -> AvatarSnapshot | None:
    """
    Project active physical voice I/O truth into presentation semantics.

    Return None when voice currently owns no active LISTENING/SPEAKING
    presentation claim.

    Precedence for the avatar's single mode:

        PLAYING     -> SPEAKING
        CAPTURING   -> LISTENING
        otherwise   -> None

    This precedence changes presentation only. It never rewrites VoiceSnapshot
    and never hides or mutates its simultaneous input/output truth.
    """

    if not isinstance(
        snapshot,
        VoiceSnapshot,
    ):
        raise TypeError(
            "snapshot must be VoiceSnapshot."
        )

    playback_active = (
        snapshot.output_mode
        == VoiceOutputMode.PLAYING
        and snapshot.playback_active
        is True
    )

    microphone_active = (
        snapshot.input_mode
        == VoiceInputMode.CAPTURING
        and snapshot.microphone_active
        is True
    )

    if playback_active:
        return AvatarSnapshot(
            mode=AvatarMode.SPEAKING,
            expression=(
                AvatarExpression.GENTLE
            ),
            expression_intensity=0.35,
            gaze=AvatarGaze.USER,
            motion_energy=0.55,
            speech_active=True,
            reason="voice playback active",
        )

    if microphone_active:
        return AvatarSnapshot(
            mode=AvatarMode.LISTENING,
            expression=(
                AvatarExpression.FOCUSED
            ),
            expression_intensity=0.35,
            gaze=AvatarGaze.USER,
            motion_energy=0.25,
            speech_active=False,
            reason="microphone capture active",
        )

    return None
