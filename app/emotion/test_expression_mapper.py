from app.emotion import (
    EmotionSignal,
    KumaEmotion,
    KumaExpressionMapper,
    KumaExpressionMode,
    KumaGesture,
)


def test_excited_becomes_energetic():
    directive = KumaExpressionMapper().map(
        EmotionSignal(
            primary=KumaEmotion.EXCITED,
            intensity=0.9,
            confidence=0.9,
        )
    )

    assert directive.mode == (
        KumaExpressionMode.ENERGETIC
    )

    assert directive.gesture == (
        KumaGesture.DOUBLE_ARM_LIFT
    )

    assert directive.bounce > 0.5
    assert directive.pod_energy > 0.8


def test_playful_uses_wave():
    directive = KumaExpressionMapper().map(
        EmotionSignal(
            primary=KumaEmotion.PLAYFUL,
            intensity=0.7,
        )
    )

    assert directive.mode == (
        KumaExpressionMode.PLAYFUL
    )

    assert directive.gesture == (
        KumaGesture.WAVE
    )


def test_sad_user_gets_gentle_kuma():
    directive = KumaExpressionMapper().map(
        EmotionSignal(
            primary=KumaEmotion.SAD,
            intensity=0.8,
        )
    )

    assert directive.mode == (
        KumaExpressionMode.GENTLE
    )

    assert directive.gesture == (
        KumaGesture.GENTLE_OPEN
    )

    assert directive.motion_scale < 1.0


def test_frustration_is_not_mirrored():
    directive = KumaExpressionMapper().map(
        EmotionSignal(
            primary=(
                KumaEmotion.FRUSTRATED
            ),
            intensity=0.9,
        )
    )

    assert directive.mode == (
        KumaExpressionMode.FOCUSED
    )

    assert directive.mode != (
        KumaExpressionMode.ALERT
    )


def test_confusion_becomes_curiosity():
    directive = KumaExpressionMapper().map(
        EmotionSignal(
            primary=KumaEmotion.CONFUSED,
            intensity=0.7,
        )
    )

    assert directive.mode == (
        KumaExpressionMode.CURIOUS
    )

    assert directive.head_tilt_deg > 0


def test_high_urgency_becomes_alert():
    directive = KumaExpressionMapper().map(
        EmotionSignal(
            primary=KumaEmotion.NEUTRAL,
            urgency=0.9,
        )
    )

    assert directive.mode == (
        KumaExpressionMode.ALERT
    )


def test_neutral_stays_neutral():
    directive = KumaExpressionMapper().map(
        EmotionSignal()
    )

    assert directive.mode == (
        KumaExpressionMode.NEUTRAL
    )

    assert directive.gesture == (
        KumaGesture.NONE
    )
