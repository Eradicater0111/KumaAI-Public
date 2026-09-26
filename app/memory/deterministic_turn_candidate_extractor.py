from __future__ import annotations

import re

from app.memory.contracts import (
    MEMORY_AUTHORITY_NONE,
    MemoryKind,
    MemorySource,
)
from app.memory.formation import (
    MemoryCandidate,
    MemoryDurability,
    MemorySensitivity,
)
from app.memory.turn_candidate_composition import (
    ExtractedTurnMemoryCandidate,
)


MEMORY_V2C_AUTHORITY_NONE = (
    MEMORY_AUTHORITY_NONE
)


# =========================================================
# KUMA MEMORY-V2C — DETERMINISTIC IMPLICIT CANDIDATE EXTRACTION
# =========================================================
#
# CURRENT USER MESSAGE
#   -> CONSERVATIVE LITERAL PATTERN
#   -> ZERO OR ONE USER_STATEMENT CANDIDATE
#   -> MEMORY-V2B
#   -> MEMORY-V2A
#   -> STOP
#
# PRECISION > RECALL
# USER MESSAGE = ONLY FACTUAL EVIDENCE
# LITERAL MATCH != INFERENCE
# EXTRACTION != PERSISTENCE
# EXTRACTION != PERMISSION
# CANDIDATE KEY != DURABLE REVISION IDENTITY
# EXPLICIT MEMORY REQUEST != IMPLICIT CANDIDATE
# TEMPORARY STATE != STABLE MEMORY
# COMPOUND STATEMENT != SINGLE CANDIDATE
# SECRET-LIKE CONTENT != IMPLICIT CANDIDATE
# MODEL CALL = NONE
# AUTHORITY: NONE
#
# Initial supported forms are intentionally narrow:
#
#   I prefer X.
#   My favorite <label> is X.
#   My name is X.
#   <project> is my <descriptor> project.
#
# Any message outside these forms returns None.
# =========================================================


_EXPLICIT_MEMORY_MARKERS = (
    "remember that",
    "remember this",
    "remember ",
    "save this",
    "save that",
    "keep in mind",
    "don't forget",
    "do not forget",
)


_TEMPORARY_OR_UNCERTAIN_MARKERS = (
    " today",
    " tonight",
    " right now",
    " currently",
    " this week",
    " this month",
    " tomorrow",
    " yesterday",
    " later",
    " for now",
    " temporarily",
    " maybe",
    " might ",
    " may ",
    " probably",
    " plan to ",
    " planning to ",
    " going to ",
    " will ",
)


_SECRET_LIKE_MARKERS = (
    "password",
    "passcode",
    " pin ",
    "cvv",
    "credit card",
    "debit card",
    "bank account",
    "aadhaar",
    "passport number",
    "social security",
    "one-time password",
    " otp ",
    "api key",
    "secret key",
    "private key",
)


_COMPOUND_MARKERS = (
    " and ",
    " but ",
    " or ",
    ";",
    "\n",
)


_PREFERENCE_PATTERN = re.compile(
    r"^I prefer (?P<value>[^.!?]{1,120})\.?$",
    re.IGNORECASE,
)


_FAVORITE_PATTERN = re.compile(
    (
        r"^My favorite "
        r"(?P<label>[A-Za-z][A-Za-z0-9 _-]{0,39}) "
        r"is "
        r"(?P<value>[^.!?]{1,120})"
        r"\.?$"
    ),
    re.IGNORECASE,
)


_NAME_PATTERN = re.compile(
    (
        r"^My name is "
        r"(?P<value>[A-Za-z][A-Za-z .'-]{0,79}?)"
        r"\.?$"
    ),
    re.IGNORECASE,
)


_PROJECT_PATTERN = re.compile(
    (
        r"^(?P<project>[A-Za-z][A-Za-z0-9 _-]{0,39}) "
        r"is my "
        r"(?P<descriptor>[^.!?]{1,100} project)"
        r"\.?$"
    ),
    re.IGNORECASE,
)


def _slug(
    value: str,
) -> str:
    normalized = re.sub(
        r"[^a-z0-9]+",
        "_",
        value.casefold(),
    ).strip("_")

    return normalized[:48]


def _message_is_ineligible(
    message: str,
) -> bool:
    lowered = message.casefold()

    if "?" in message:
        return True

    if any(
        marker in lowered
        for marker in _EXPLICIT_MEMORY_MARKERS
    ):
        return True

    if any(
        marker in lowered
        for marker in _TEMPORARY_OR_UNCERTAIN_MARKERS
    ):
        return True

    if any(
        marker in lowered
        for marker in _SECRET_LIKE_MARKERS
    ):
        return True

    if any(
        marker in lowered
        for marker in _COMPOUND_MARKERS
    ):
        return True

    return False


def _candidate(
    *,
    kind: MemoryKind,
    category: str,
    key: str,
    value: str,
    importance: float,
) -> MemoryCandidate:
    return MemoryCandidate(
        kind=kind,
        category=category,
        key=key,
        value=value,
        source=MemorySource.USER_STATEMENT,
        durability=MemoryDurability.STABLE,
        sensitivity=MemorySensitivity.NORMAL,
        explicit_user_authorization=False,
        confidence=1.0,
        importance=importance,
    )


def extract_deterministic_turn_memory_candidate(
    user_message: str,
) -> ExtractedTurnMemoryCandidate | None:
    """
    Extract at most one narrow, literal, implicit memory candidate.

    This function never writes memory and never infers beyond supported
    sentence forms.
    """

    if not isinstance(
        user_message,
        str,
    ):
        raise TypeError(
            "user_message must be a string."
        )

    message = user_message.strip()

    if not message:
        return None

    if _message_is_ineligible(
        message
    ):
        return None

    match = _FAVORITE_PATTERN.fullmatch(
        message
    )

    if match is not None:
        label = match.group(
            "label"
        ).strip()

        value = match.group(
            "value"
        ).strip()

        key_suffix = _slug(
            label
        )

        if not key_suffix:
            return None

        return ExtractedTurnMemoryCandidate(
            evidence_text=message,
            candidate=_candidate(
                kind=MemoryKind.PREFERENCE,
                category="preferences",
                key=(
                    "favorite_"
                    + key_suffix
                ),
                value=value,
                importance=0.70,
            ),
        )

    match = _NAME_PATTERN.fullmatch(
        message
    )

    if match is not None:
        value = match.group(
            "value"
        ).strip()

        return ExtractedTurnMemoryCandidate(
            evidence_text=message,
            candidate=_candidate(
                kind=MemoryKind.PERSONAL_FACT,
                category="personal",
                key="name",
                value=value,
                importance=0.80,
            ),
        )

    match = _PROJECT_PATTERN.fullmatch(
        message
    )

    if match is not None:
        project = match.group(
            "project"
        ).strip()

        key_prefix = _slug(
            project
        )

        if not key_prefix:
            return None

        statement = (
            message[:-1]
            if message.endswith(".")
            else message
        )

        return ExtractedTurnMemoryCandidate(
            evidence_text=statement,
            candidate=_candidate(
                kind=MemoryKind.PROJECT_KNOWLEDGE,
                category="projects",
                key=(
                    key_prefix
                    + "_project"
                ),
                value=statement,
                importance=0.80,
            ),
        )

    match = _PREFERENCE_PATTERN.fullmatch(
        message
    )

    if match is not None:
        value = match.group(
            "value"
        ).strip()

        key_suffix = _slug(
            value
        )

        if not key_suffix:
            return None

        return ExtractedTurnMemoryCandidate(
            evidence_text=message,
            candidate=_candidate(
                kind=MemoryKind.PREFERENCE,
                category="preferences",
                key=(
                    "preference_"
                    + key_suffix
                ),
                value=value,
                importance=0.60,
            ),
        )

    return None
