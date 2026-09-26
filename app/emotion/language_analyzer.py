from __future__ import annotations

import re

from app.emotion.emotion_state import (
    EmotionSignal,
    KumaEmotion,
    KumaTone,
)


class LanguageEmotionAnalyzer:
    """
    Lightweight conversational affect detector.

    V1 is deterministic and local:
        - lexical cues
        - punctuation
        - repetition
        - emoji cues
        - conversational phrasing

    It creates no tool authority and performs
    no external actions.
    """

    _EXCITED = (
        "yooo",
        "yooo",
        "lets go",
        "let's go",
        "hell yeah",
        "awesome",
        "amazing",
        "finally",
        "broooo",
        "brooo",
        "letsgoo",
        "letsgо",
        "hype",
    )

    _HAPPY = (
        "happy",
        "nice",
        "great",
        "good",
        "love it",
        "perfect",
        "beautiful",
        "thank you",
        "thanks",
        "yay",
    )

    _PLAYFUL = (
        "lol",
        "lmao",
        "haha",
        "hehe",
        "😂",
        "🤣",
        "😜",
        "😏",
        "💀",
    )

    _CURIOUS = (
        "why",
        "how",
        "what if",
        "wonder",
        "curious",
        "can we",
        "could we",
        "is it possible",
    )

    _TIRED = (
        "tired",
        "sleepy",
        "exhausted",
        "drained",
        "worn out",
        "no energy",
        "😴",
    )

    _SAD = (
        "sad",
        "upset",
        "down",
        "hurt",
        "lonely",
        "terrible",
        "awful",
        "😭",
        "😢",
    )

    _FRUSTRATED = (
        "annoying",
        "annoyed",
        "frustrated",
        "pissed",
        "wtf",
        "come on",
        "again bro",
        "not working",
        "doesn't work",
        "doesnt work",
    )

    _CONFUSED = (
        "confused",
        "i don't get",
        "i dont get",
        "don't understand",
        "dont understand",
        "huh",
        "what do you mean",
        "🤔",
        "😵",
    )

    _URGENT = (
        "urgent",
        "quick",
        "quickly",
        "now",
        "immediately",
        "asap",
        "emergency",
        "hurry",
    )

    _POSITIVE_EMOJI = (
        "😊",
        "😁",
        "😄",
        "😍",
        "🥹",
        "❤️",
        "♥",
        "🔥",
        "✨",
        "🎉",
    )

    def analyze(
        self,
        text,
    ) -> EmotionSignal:

        original = str(
            text
            or ""
        )

        normalized = (
            original
            .strip()
            .lower()
        )

        if not normalized:
            return EmotionSignal()

        scores = {
            emotion: 0.0
            for emotion
            in KumaEmotion
        }

        # ---------------------------------------------
        # LEXICAL CUES
        # ---------------------------------------------

        self._score_terms(
            normalized,
            self._EXCITED,
            scores,
            KumaEmotion.EXCITED,
            0.34,
        )

        self._score_terms(
            normalized,
            self._HAPPY,
            scores,
            KumaEmotion.HAPPY,
            0.25,
        )

        self._score_terms(
            normalized,
            self._PLAYFUL,
            scores,
            KumaEmotion.PLAYFUL,
            0.38,
        )

        self._score_terms(
            normalized,
            self._CURIOUS,
            scores,
            KumaEmotion.CURIOUS,
            0.20,
        )

        self._score_terms(
            normalized,
            self._TIRED,
            scores,
            KumaEmotion.TIRED,
            0.45,
        )

        self._score_terms(
            normalized,
            self._SAD,
            scores,
            KumaEmotion.SAD,
            0.42,
        )

        self._score_terms(
            normalized,
            self._FRUSTRATED,
            scores,
            KumaEmotion.FRUSTRATED,
            0.44,
        )

        self._score_terms(
            normalized,
            self._CONFUSED,
            scores,
            KumaEmotion.CONFUSED,
            0.40,
        )

        # ---------------------------------------------
        # EMOJI ENERGY
        # ---------------------------------------------

        positive_emoji_count = sum(
            original.count(
                emoji
            )
            for emoji
            in self._POSITIVE_EMOJI
        )

        if positive_emoji_count:
            scores[
                KumaEmotion.HAPPY
            ] += min(
                0.45,
                positive_emoji_count
                * 0.15,
            )

        if "🔥" in original:
            scores[
                KumaEmotion.EXCITED
            ] += 0.28

        # ---------------------------------------------
        # TEXT ENERGY
        # ---------------------------------------------

        exclamations = (
            original.count("!")
        )

        if exclamations:
            scores[
                KumaEmotion.EXCITED
            ] += min(
                0.30,
                exclamations * 0.08,
            )

        repeated_letters = bool(
            re.search(
                r"([a-zA-Z])\1{2,}",
                original,
            )
        )

        if repeated_letters:
            scores[
                KumaEmotion.EXCITED
            ] += 0.18

        uppercase_letters = [
            char
            for char in original
            if char.isalpha()
        ]

        if uppercase_letters:

            uppercase_ratio = (
                sum(
                    char.isupper()
                    for char
                    in uppercase_letters
                )
                / len(
                    uppercase_letters
                )
            )

            if (
                len(
                    uppercase_letters
                ) >= 4
                and uppercase_ratio
                > 0.70
            ):
                scores[
                    KumaEmotion.EXCITED
                ] += 0.22

        # ---------------------------------------------
        # URGENCY
        # ---------------------------------------------

        urgency_matches = sum(
            term in normalized
            for term
            in self._URGENT
        )

        urgency = min(
            1.0,
            urgency_matches * 0.35,
        )

        if urgency >= 0.50:
            scores[
                KumaEmotion.ALERT
            ] += urgency * 0.60

        # ---------------------------------------------
        # PRIMARY EMOTION
        # ---------------------------------------------

        primary = max(
            scores,
            key=scores.get,
        )

        primary_score = scores[
            primary
        ]

        if primary_score < 0.18:
            primary = (
                KumaEmotion.NEUTRAL
            )

        intensity = min(
            1.0,
            primary_score,
        )

        tone = self._tone_for(
            primary
        )

        valence = self._valence_for(
            primary
        )

        confidence = (
            0.35
            if primary
            == KumaEmotion.NEUTRAL
            else min(
                0.96,
                0.55
                + primary_score
                * 0.45,
            )
        )

        return EmotionSignal(
            primary=primary,
            tone=tone,
            intensity=intensity,
            valence=valence,
            urgency=urgency,
            confidence=confidence,
        )

    @staticmethod
    def _score_terms(
        text,
        terms,
        scores,
        emotion,
        weight,
    ):
        matches = sum(
            term in text
            for term in terms
        )

        scores[
            emotion
        ] += matches * weight

    @staticmethod
    def _tone_for(
        emotion,
    ) -> KumaTone:

        mapping = {
            KumaEmotion.HAPPY:
                KumaTone.FRIENDLY,

            KumaEmotion.EXCITED:
                KumaTone.ENERGETIC,

            KumaEmotion.PLAYFUL:
                KumaTone.PLAYFUL,

            KumaEmotion.CURIOUS:
                KumaTone.CURIOUS,

            KumaEmotion.GENTLE:
                KumaTone.SUBDUED,

            KumaEmotion.SAD:
                KumaTone.SUBDUED,

            KumaEmotion.TIRED:
                KumaTone.SUBDUED,

            KumaEmotion.CONFUSED:
                KumaTone.CURIOUS,

            KumaEmotion.ALERT:
                KumaTone.URGENT,

            KumaEmotion.FRUSTRATED:
                KumaTone.SERIOUS,
        }

        return mapping.get(
            emotion,
            KumaTone.NEUTRAL,
        )

    @staticmethod
    def _valence_for(
        emotion,
    ) -> float:

        mapping = {
            KumaEmotion.HAPPY:
                0.85,

            KumaEmotion.EXCITED:
                0.80,

            KumaEmotion.PLAYFUL:
                0.75,

            KumaEmotion.CURIOUS:
                0.20,

            KumaEmotion.GENTLE:
                0.25,

            KumaEmotion.SAD:
                -0.70,

            KumaEmotion.TIRED:
                -0.30,

            KumaEmotion.CONFUSED:
                -0.15,

            KumaEmotion.ALERT:
                -0.10,

            KumaEmotion.FRUSTRATED:
                -0.65,
        }

        return mapping.get(
            emotion,
            0.0,
        )
