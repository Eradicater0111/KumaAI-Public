from app.emotion import (
    KumaEmotion,
    KumaTone,
    LanguageEmotionAnalyzer,
)


def test_excited_playful_message():
    result = LanguageEmotionAnalyzer().analyze(
        "Yoooo broooo 🔥🔥"
    )

    assert result.primary == (
        KumaEmotion.EXCITED
    )

    assert result.tone == (
        KumaTone.ENERGETIC
    )

    assert result.intensity > 0.5


def test_playful_emoji_message():
    result = LanguageEmotionAnalyzer().analyze(
        "bro 😂😂"
    )

    assert result.primary == (
        KumaEmotion.PLAYFUL
    )


def test_tired_message():
    result = LanguageEmotionAnalyzer().analyze(
        "bro I'm exhausted and have no energy"
    )

    assert result.primary == (
        KumaEmotion.TIRED
    )

    assert result.valence < 0


def test_confused_message():
    result = LanguageEmotionAnalyzer().analyze(
        "huh I don't understand this"
    )

    assert result.primary == (
        KumaEmotion.CONFUSED
    )


def test_neutral_message():
    result = LanguageEmotionAnalyzer().analyze(
        "Okay."
    )

    assert result.primary == (
        KumaEmotion.NEUTRAL
    )


def test_empty_message_is_neutral():
    result = LanguageEmotionAnalyzer().analyze(
        ""
    )

    assert result.primary == (
        KumaEmotion.NEUTRAL
    )
