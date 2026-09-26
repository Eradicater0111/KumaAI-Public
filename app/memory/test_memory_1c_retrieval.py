import json
import sqlite3
from datetime import datetime, timedelta, timezone

from app.memory.contracts import (
    MEMORY_AUTHORITY_NONE,
    MemoryKind,
    MemorySource,
    MemoryStatus,
)
from app.memory.retrieval import (
    format_memory_context,
    retrieve_memories,
)
from app.memory.schema import migrate_memory_schema


NOW = datetime(
    2026, 9, 12, 0, 0,
    tzinfo=timezone.utc,
)


def _database(tmp_path):
    db = tmp_path / "memory.db"
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

    migrate_memory_schema(connection)
    connection.close()
    return db


def _insert(
    db,
    *,
    memory_id,
    key,
    value,
    kind=MemoryKind.PREFERENCE,
    source=MemorySource.USER_STATEMENT,
    status=MemoryStatus.ACTIVE,
    valid_from=None,
    valid_until=None,
    project_scope=None,
    subject="user",
    authority=MEMORY_AUTHORITY_NONE,
    confidence=0.8,
    embedding=(1.0, 0.0),
):
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
            valid_from,
            valid_until,
            status,
            subject,
            project_scope,
            authority,
            embedding
        )
        VALUES (
            ?, ?, 'test', ?, ?, ?, ?,
            0.5,
            '2026-09-11T00:00:00+00:00',
            '2026-09-11T00:00:00+00:00',
            ?, ?, ?, ?, ?, ?, ?
        )
        """,
        (
            memory_id,
            kind.value,
            key,
            value,
            source.value,
            confidence,
            valid_from,
            valid_until,
            status.value,
            subject,
            project_scope,
            authority,
            json.dumps(list(embedding)),
        ),
    )

    connection.commit()
    connection.close()


def _retrieve(db, **kwargs):
    return retrieve_memories(
        "preference",
        db_path=db,
        embedder=lambda _text: [1.0, 0.0],
        now=NOW,
        threshold=0.0,
        limit=50,
        **kwargs,
    )


def test_only_active_lifecycle_state_is_retrievable(tmp_path):
    db = _database(tmp_path)

    for memory_id, status in (
        ("active", MemoryStatus.ACTIVE),
        ("superseded", MemoryStatus.SUPERSEDED),
        ("retracted", MemoryStatus.RETRACTED),
        ("expired", MemoryStatus.EXPIRED),
    ):
        _insert(
            db,
            memory_id=memory_id,
            key=memory_id,
            value=memory_id,
            status=status,
        )

    assert [
        match.record.memory_id
        for match in _retrieve(db)
    ] == ["active"]


def test_temporal_validity_is_enforced(tmp_path):
    db = _database(tmp_path)

    _insert(
        db,
        memory_id="current",
        key="current",
        value="current",
        valid_from=(NOW - timedelta(days=1)).isoformat(),
        valid_until=(NOW + timedelta(days=1)).isoformat(),
    )
    _insert(
        db,
        memory_id="future",
        key="future",
        value="future",
        valid_from=(NOW + timedelta(seconds=1)).isoformat(),
    )
    _insert(
        db,
        memory_id="past",
        key="past",
        value="past",
        valid_until=(NOW - timedelta(seconds=1)).isoformat(),
    )

    assert [
        match.record.memory_id
        for match in _retrieve(db)
    ] == ["current"]


def test_project_scope_is_required_and_case_insensitive(tmp_path):
    db = _database(tmp_path)

    _insert(
        db,
        memory_id="global",
        key="global",
        value="global",
    )
    _insert(
        db,
        memory_id="kuma",
        key="kuma",
        value="kuma",
        kind=MemoryKind.PROJECT_KNOWLEDGE,
        source=MemorySource.PROJECT_STATE,
        project_scope="KumaAI",
    )
    _insert(
        db,
        memory_id="other",
        key="other",
        value="other",
        kind=MemoryKind.PROJECT_KNOWLEDGE,
        source=MemorySource.PROJECT_STATE,
        project_scope="OtherProject",
    )

    assert {
        match.record.memory_id
        for match in _retrieve(db)
    } == {"global"}

    assert {
        match.record.memory_id
        for match in _retrieve(
            db,
            project_scope="kumaai",
        )
    } == {"global", "kuma"}


def test_subject_boundary_is_enforced(tmp_path):
    db = _database(tmp_path)

    _insert(
        db,
        memory_id="user",
        key="user",
        value="user",
        subject="user",
    )
    _insert(
        db,
        memory_id="kuma",
        key="kuma",
        value="kuma",
        subject="kuma",
    )

    assert [
        match.record.memory_id
        for match in _retrieve(db)
    ] == ["user"]

    assert [
        match.record.memory_id
        for match in _retrieve(
            db,
            subject="kuma",
        )
    ] == ["kuma"]


def test_inference_remains_explicit_in_context(tmp_path):
    db = _database(tmp_path)

    _insert(
        db,
        memory_id="inference",
        key="coding_time",
        value="Possibly prefers late-night coding.",
        kind=MemoryKind.INFERENCE,
        source=MemorySource.MODEL_INFERENCE,
        confidence=0.55,
    )

    matches = _retrieve(db)
    context = format_memory_context(matches)

    assert len(matches) == 1
    assert "[INFERENCE confidence=0.55]" in context
    assert "Possibly prefers late-night coding." in context


def test_unclassified_imported_legacy_memory_remains_retrievable(
    tmp_path,
):
    db = _database(tmp_path)

    _insert(
        db,
        memory_id="legacy-1",
        key="legacy",
        value="legacy value",
        kind=MemoryKind.UNCLASSIFIED,
        source=MemorySource.IMPORTED,
        confidence=0.5,
    )

    assert [
        match.record.memory_id
        for match in _retrieve(db)
    ] == ["legacy-1"]


def test_non_none_authority_fails_closed(tmp_path):
    db = _database(tmp_path)

    _insert(
        db,
        memory_id="unsafe",
        key="unsafe",
        value="unsafe",
        authority="EXECUTE",
    )

    assert _retrieve(db) == []


def test_similarity_order_and_threshold_remain_semantic_only(tmp_path):
    db = _database(tmp_path)

    _insert(
        db,
        memory_id="strong",
        key="strong",
        value="strong",
        embedding=(1.0, 0.0),
    )
    _insert(
        db,
        memory_id="medium",
        key="medium",
        value="medium",
        embedding=(0.6, 0.8),
    )
    _insert(
        db,
        memory_id="weak",
        key="weak",
        value="weak",
        embedding=(0.2, 0.98),
    )

    matches = retrieve_memories(
        "preference",
        db_path=db,
        embedder=lambda _text: [1.0, 0.0],
        now=NOW,
        threshold=0.5,
        limit=50,
    )

    assert [
        match.record.memory_id
        for match in matches
    ] == ["strong", "medium"]


def test_malformed_or_wrong_dimension_embedding_fails_closed(
    tmp_path,
):
    db = _database(tmp_path)

    _insert(
        db,
        memory_id="bad-json",
        key="bad-json",
        value="bad-json",
    )
    _insert(
        db,
        memory_id="bad-dimension",
        key="bad-dimension",
        value="bad-dimension",
        embedding=(1.0, 0.0, 0.0),
    )

    connection = sqlite3.connect(db)
    connection.execute(
        """
        UPDATE memories
        SET embedding = 'not-json'
        WHERE memory_id = 'bad-json'
        """
    )
    connection.commit()
    connection.close()

    assert _retrieve(db) == []


def test_blank_query_does_not_call_embedder(tmp_path):
    db = _database(tmp_path)
    called = False

    def embedder(_text):
        nonlocal called
        called = True
        return [1.0, 0.0]

    assert retrieve_memories(
        "   ",
        db_path=db,
        embedder=embedder,
    ) == []

    assert called is False


def test_unavailable_schema_fails_closed_without_migration(tmp_path):
    db = tmp_path / "empty.db"
    sqlite3.connect(db).close()

    assert retrieve_memories(
        "preference",
        db_path=db,
        embedder=lambda _text: [1.0, 0.0],
    ) == []
