from __future__ import annotations

from enum import Enum


class KumaBodyState(str, Enum):
    IDLE = "idle"
    LISTENING = "listening"
    SPEAKING = "speaking"
    THINKING = "thinking"
    OBSERVING = "observing"
    WORKING = "working"
    FOCUSED = "focused"
    HAPPY = "happy"
    ALERT = "alert"
    SLEEP = "sleep"


KUMA_BODY_STATES = tuple(
    state.value
    for state in KumaBodyState
)


def normalize_body_state(
    value: object,
) -> KumaBodyState:
    if isinstance(
        value,
        KumaBodyState,
    ):
        return value

    if type(value) is not str:
        return KumaBodyState.IDLE

    normalized = (
        value.strip()
        .lower()
    )

    try:
        return KumaBodyState(
            normalized
        )
    except ValueError:
        return KumaBodyState.IDLE
