from __future__ import annotations

from app.emotion.emotion_state import (
    EmotionSignal,
    KumaEmotion,
)

from app.emotion.expression_directive import (
    KumaExpressionDirective,
    KumaExpressionMode,
    KumaGesture,
)


class KumaExpressionMapper:
    """
    Translate user conversational affect into
    KUMA's own presentation response.

    KUMA does not blindly mirror negative affect.
    Frustration becomes calm focus.
    Sadness becomes gentle attention.
    Confusion becomes curiosity.
    """

    def map(
        self,
        signal: EmotionSignal,
    ) -> KumaExpressionDirective:

        emotion = signal.primary

        intensity = signal.intensity

        # -------------------------------------------------
        # EXCITED
        # -------------------------------------------------

        if emotion == KumaEmotion.EXCITED:

            return KumaExpressionDirective(
                mode=(
                    KumaExpressionMode.ENERGETIC
                ),
                gesture=(
                    KumaGesture.DOUBLE_ARM_LIFT
                ),
                head_tilt_deg=2.0,
                bounce=(
                    0.45
                    + intensity * 0.40
                ),
                pod_energy=(
                    0.70
                    + intensity * 0.25
                ),
                motion_scale=(
                    1.15
                    + intensity * 0.25
                ),
                hold_ms=2200,
            )

        # -------------------------------------------------
        # PLAYFUL
        # -------------------------------------------------

        if emotion == KumaEmotion.PLAYFUL:

            return KumaExpressionDirective(
                mode=(
                    KumaExpressionMode.PLAYFUL
                ),
                gesture=(
                    KumaGesture.WAVE
                ),
                head_tilt_deg=7.0,
                bounce=(
                    0.30
                    + intensity * 0.25
                ),
                pod_energy=0.78,
                motion_scale=1.15,
                hold_ms=2000,
            )

        # -------------------------------------------------
        # HAPPY
        # -------------------------------------------------

        if emotion == KumaEmotion.HAPPY:

            return KumaExpressionDirective(
                mode=(
                    KumaExpressionMode.HAPPY
                ),
                gesture=(
                    KumaGesture.NOD
                ),
                head_tilt_deg=2.0,
                bounce=(
                    0.20
                    + intensity * 0.20
                ),
                pod_energy=0.72,
                motion_scale=1.08,
                hold_ms=1900,
            )

        # -------------------------------------------------
        # CURIOUS
        # -------------------------------------------------

        if emotion == KumaEmotion.CURIOUS:

            return KumaExpressionDirective(
                mode=(
                    KumaExpressionMode.CURIOUS
                ),
                gesture=(
                    KumaGesture.CURIOUS_TILT
                ),
                head_tilt_deg=10.0,
                bounce=0.08,
                pod_energy=0.58,
                motion_scale=0.95,
                hold_ms=2200,
            )

        # -------------------------------------------------
        # CONFUSED
        # -------------------------------------------------
        #
        # User confusion should make KUMA attentive and
        # curious rather than confused herself.
        # -------------------------------------------------

        if emotion == KumaEmotion.CONFUSED:

            return KumaExpressionDirective(
                mode=(
                    KumaExpressionMode.CURIOUS
                ),
                gesture=(
                    KumaGesture.ATTENTIVE
                ),
                head_tilt_deg=9.0,
                bounce=0.04,
                pod_energy=0.52,
                motion_scale=0.90,
                hold_ms=2500,
            )

        # -------------------------------------------------
        # SAD / TIRED
        # -------------------------------------------------

        if emotion in {
            KumaEmotion.SAD,
            KumaEmotion.TIRED,
        }:

            return KumaExpressionDirective(
                mode=(
                    KumaExpressionMode.GENTLE
                ),
                gesture=(
                    KumaGesture.GENTLE_OPEN
                ),
                head_tilt_deg=4.0,
                bounce=0.02,
                pod_energy=0.36,
                motion_scale=0.72,
                hold_ms=2800,
            )

        # -------------------------------------------------
        # FRUSTRATED
        # -------------------------------------------------
        #
        # Do not mirror frustration.
        # KUMA becomes calmer and more focused.
        # -------------------------------------------------

        if emotion == KumaEmotion.FRUSTRATED:

            return KumaExpressionDirective(
                mode=(
                    KumaExpressionMode.FOCUSED
                ),
                gesture=(
                    KumaGesture.ATTENTIVE
                ),
                head_tilt_deg=1.0,
                bounce=0.0,
                pod_energy=0.52,
                motion_scale=0.82,
                hold_ms=2400,
            )

        # -------------------------------------------------
        # ALERT
        # -------------------------------------------------

        if (
            emotion == KumaEmotion.ALERT
            or signal.urgency >= 0.70
        ):

            return KumaExpressionDirective(
                mode=(
                    KumaExpressionMode.ALERT
                ),
                gesture=(
                    KumaGesture.ATTENTIVE
                ),
                head_tilt_deg=0.0,
                bounce=0.0,
                pod_energy=0.95,
                motion_scale=1.12,
                hold_ms=2400,
            )

        # -------------------------------------------------
        # GENTLE
        # -------------------------------------------------

        if emotion == KumaEmotion.GENTLE:

            return KumaExpressionDirective(
                mode=(
                    KumaExpressionMode.WARM
                ),
                gesture=(
                    KumaGesture.OPEN_ARM
                ),
                head_tilt_deg=4.0,
                bounce=0.04,
                pod_energy=0.48,
                motion_scale=0.85,
                hold_ms=2200,
            )

        # -------------------------------------------------
        # NEUTRAL
        # -------------------------------------------------

        return KumaExpressionDirective(
            mode=(
                KumaExpressionMode.NEUTRAL
            ),
            gesture=(
                KumaGesture.NONE
            ),
            head_tilt_deg=0.0,
            bounce=0.05,
            pod_energy=0.30,
            motion_scale=1.0,
            hold_ms=1600,
        )
