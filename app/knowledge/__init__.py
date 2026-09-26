"""KUMA unified read-only knowledge layer.

Internal providers are not model-facing tools. Knowledge intents/plans
are permanently AUTHORITY: NONE.
"""

from app.knowledge.contracts import (
    KNOWLEDGE_AUTHORITY_NONE,
    KnowledgeDomain,
    KnowledgeIntent,
    KnowledgePlan,
    LocationScope,
    TemporalScope,
)
from app.knowledge.resolver import KnowledgeResolver

__all__ = [
    "KNOWLEDGE_AUTHORITY_NONE",
    "KnowledgeDomain",
    "KnowledgeIntent",
    "KnowledgePlan",
    "KnowledgeResolver",
    "LocationScope",
    "TemporalScope",
]
