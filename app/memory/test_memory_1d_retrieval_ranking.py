import json
import sqlite3
from datetime import datetime, timedelta, timezone

from app.memory.contracts import (
    MemoryKind,
    MemorySource,
)
from app.memory.retrieval import (
    format_memory_context,
    retrieve_memories,
)
from app.memory.schema import migrate_memory_schema


NOW = datetime(
    2026,
    9,
    12,
    0,
    0,
    tzinfo=timezone.utc,
)


def _database(tmp_path):
    db = tmp_path / "attention.db"
    connection = sqlite3.connect(db)

    connection.execute(
        """
        CREATE TABLE memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            embedding TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    migrate_memory_schema(
        connection
    )
    connection.close()
    return db


def _insert(
    db,
    *,
    memory_id,
    kind,
    source,
    confidence,
    importance,
    age_days,
    similarity,
):
    updated = (
        NOW
        - timedelta(
            days=age_days
        )
    ).isoformat()

    connection = sqlite3.connect(db)
    connection.execute(
        """
        INSERT INTO memories (
            memory_id,
            kind,
            category,
            key,
            value,
            source,
            confidence,
            importance,
            created_at,
            updated_at,
            status,
            subject,
            authority,
            embedding
        )
        VALUES (
            ?, ?, 'probe', ?, ?, ?,
            ?, ?, ?, ?,
            'active', 'user', 'NONE', ?
        )
        """,
        (
            memory_id,
            kind.value,
            memory_id,
            memory_id,
            source.value,
            confidence,
            importance,
            updated,
            updated,
            json.dumps(
                [similarity, 0.0]
            ),
        ),
    )
    connection.commit()
    connection.close()


def test_retrieval_orders_by_attention_but_preserves_similarity(tmp_path):
    db = _database(tmp_path)

    _insert(
        db,
        memory_id="weak-inference",
        kind=MemoryKind.INFERENCE,
        source=MemorySource.MODEL_INFERENCE,
        confidence=0.35,
        importance=0.20,
        age_days=120,
        similarity=0.98,
    )

    _insert(
        db,
        memory_id="explicit-preference",
        kind=MemoryKind.PREFERENCE,
        source=MemorySource.USER_EXPLICIT,
        confidence=1.0,
        importance=0.90,
        age_days=2,
        similarity=0.93,
    )

    matches = retrieve_memories(
        "coffee",
        db_path=db,
        embedder=lambda _text: [
            1.0,
            0.0,
        ],
        threshold=0.0,
        limit=10,
        now=NOW,
    )

    assert [
        match.record.memory_id
        for match in matches
    ] == [
        "explicit-preference",
        "weak-inference",
    ]

    by_id = {
        match.record.memory_id: match
        for match in matches
    }

    assert (
        by_id["weak-inference"].similarity
        == 0.98
    )
    assert (
        by_id["explicit-preference"].similarity
        == 0.93
    )
    assert (
        by_id["explicit-preference"].attention_score
        > by_id["weak-inference"].attention_score
    )


def test_semantic_threshold_remains_hard_gate(tmp_path):
    db = _database(tmp_path)

    _insert(
        db,
        memory_id="below-threshold",
        kind=MemoryKind.PERSONAL_FACT,
        source=MemorySource.USER_EXPLICIT,
        confidence=1.0,
        importance=1.0,
        age_days=0,
        similarity=0.24,
    )

    matches = retrieve_memories(
        "query",
        db_path=db,
        embedder=lambda _text: [
            1.0,
            0.0,
        ],
        threshold=0.25,
        limit=10,
        now=NOW,
    )

    assert matches == []


def test_full_probe_order_repairs_all_three_failures(tmp_path):
    db = _database(tmp_path)

    rows = (
        (
            "weak-inference",
            MemoryKind.INFERENCE,
            MemorySource.MODEL_INFERENCE,
            0.35,
            0.20,
            120,
            0.98,
        ),
        (
            "explicit-preference",
            MemoryKind.PREFERENCE,
            MemorySource.USER_EXPLICIT,
            1.0,
            0.90,
            2,
            0.93,
        ),
        (
            "old-project-fact",
            MemoryKind.PROJECT_KNOWLEDGE,
            MemorySource.PROJECT_STATE,
            0.90,
            0.45,
            180,
            0.91,
        ),
        (
            "recent-project-fact",
            MemoryKind.PROJECT_KNOWLEDGE,
            MemorySource.PROJECT_STATE,
            0.98,
            0.95,
            4 / 24,
            0.89,
        ),
        (
            "legacy-import",
            MemoryKind.UNCLASSIFIED,
            MemorySource.IMPORTED,
            0.50,
            0.50,
            300,
            0.88,
        ),
        (
            "explicit-current",
            MemoryKind.PERSONAL_FACT,
            MemorySource.USER_EXPLICIT,
            1.0,
            0.80,
            2 / 24,
            0.86,
        ),
    )

    for row in rows:
        _insert(
            db,
            memory_id=row[0],
            kind=row[1],
            source=row[2],
            confidence=row[3],
            importance=row[4],
            age_days=row[5],
            similarity=row[6],
        )

    matches = retrieve_memories(
        "current work",
        db_path=db,
        embedder=lambda _text: [
            1.0,
            0.0,
        ],
        threshold=0.0,
        limit=20,
        now=NOW,
    )

    ids = [
        match.record.memory_id
        for match in matches
    ]

    assert ids.index(
        "explicit-preference"
    ) < ids.index(
        "weak-inference"
    )
    assert ids.index(
        "recent-project-fact"
    ) < ids.index(
        "old-project-fact"
    )
    assert ids.index(
        "explicit-current"
    ) < ids.index(
        "legacy-import"
    )


def test_context_does_not_expose_internal_attention_score(tmp_path):
    db = _database(tmp_path)

    _insert(
        db,
        memory_id="explicit",
        kind=MemoryKind.PREFERENCE,
        source=MemorySource.USER_EXPLICIT,
        confidence=1.0,
        importance=0.9,
        age_days=1,
        similarity=0.9,
    )

    matches = retrieve_memories(
        "query",
        db_path=db,
        embedder=lambda _text: [
            1.0,
            0.0,
        ],
        threshold=0.0,
        limit=10,
        now=NOW,
    )

    context = format_memory_context(
        matches
    )

    assert "attention" not in context.lower()
    assert "similarity" not in context.lower()
