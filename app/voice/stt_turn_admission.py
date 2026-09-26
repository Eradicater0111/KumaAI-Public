"""
KUMA STT-1F — explicit zero-authority transcript admission boundary.

The recognizer produces VoiceTranscript observations. Recognition success
alone never creates a KUMA user turn.

A caller that owns conversational scheduling may explicitly present a final
VoiceTranscript to KumaSTTTurnAdmission. The admission boundary validates the
observation and invokes the caller-owned text submission callback at most once
for that admit() invocation.

The callback remains responsible for deciding whether an ordinary textual
user turn can actually be accepted, for example because the GUI is currently
idle. It must return a strict bool.

No transcript content fingerprint is used for deduplication. Saying the same
text twice is allowed to create two distinct user turns. Recognition request
identity, stale-result rejection, and one-recognition-in-flight semantics remain
owned by STT-1D before VoiceTranscript crosses this boundary.

SPEECH RECOGNITION SUCCESS != USER TURN ADMISSION
VoiceTranscript != USER TURN
USER TURN ADMISSION != TOOL PERMISSION
USER TURN ADMISSION != EXECUTION AUTHORITY
ADMISSION CALLBACK != RUNTIME OWNER
AUTHORITY = NONE
"""

from __future__ import annotations

from app.voice.voice_runtime import (
    VOICE_AUTHORITY_NONE,
    VoiceTranscript,
)


STT_TURN_ADMISSION_AUTHORITY_NONE = (
    VOICE_AUTHORITY_NONE
)


class KumaSTTTurnAdmission:
    """
    Explicit one-call-at-a-time admission gate for final voice transcripts.

    Construction performs no admission and invokes no callback.
    """

    def __init__(
        self,
        *,
        submit_user_turn,
    ):
        if not callable(
            submit_user_turn
        ):
            raise TypeError(
                "submit_user_turn must be callable."
            )

        self._submit_user_turn = (
            submit_user_turn
        )

        self._admission_in_progress = (
            False
        )

    @property
    def authority(
        self,
    ) -> str:
        return (
            STT_TURN_ADMISSION_AUTHORITY_NONE
        )

    @property
    def admission_in_progress(
        self,
    ) -> bool:
        return (
            self._admission_in_progress
        )

    def admit(
        self,
        transcript,
    ) -> bool:
        """
        Attempt explicit admission of one final VoiceTranscript.

        True means the caller-owned text-turn scheduler explicitly accepted
        this admission attempt.

        False means no user turn was accepted.

        This object does not own runtime execution, tools, confirmation,
        permissions, recognition request identity, or transcript persistence.
        """

        if not isinstance(
            transcript,
            VoiceTranscript,
        ):
            raise TypeError(
                "transcript must be VoiceTranscript."
            )

        if (
            transcript.authority
            != VOICE_AUTHORITY_NONE
        ):
            raise ValueError(
                "VoiceTranscript authority must remain NONE."
            )

        if not transcript.is_final:
            return False

        # Fail closed against recursive/reentrant admission while the
        # caller-owned submission callback is already executing.
        if self._admission_in_progress:
            return False

        self._admission_in_progress = (
            True
        )

        try:
            accepted = (
                self._submit_user_turn(
                    transcript.text
                )
            )

        finally:
            self._admission_in_progress = (
                False
            )

        if type(
            accepted
        ) is not bool:
            raise TypeError(
                "submit_user_turn must return bool."
            )

        return accepted
