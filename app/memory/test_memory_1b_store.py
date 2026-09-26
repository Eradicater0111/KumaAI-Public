import importlib
import sqlite3
import sys
import types

import pytest

from app.memory.contracts import (
    MEMORY_AUTHORITY_NONE,
    MemoryKind,
    MemoryRecord,
    MemorySource,
    MemoryStatus,
)
from app.memory.schema import (
    KUMA_DATABASE_SCHEMA_VERSION,
    migrate_memory_schema,
)
from app.memory.store import MemoryStore


def _create_legacy_database(path):
    connection = sqlite3.connect(path)

    connection.execute(
        """
        CREATE TABLE messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

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

    connection.execute(
        """
        CREATE TABLE missions (
            mission_id TEXT PRIMARY KEY,
            goal TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            state_json TEXT NOT NULL
        )
        """
    )

    connection.execute(
        """
        INSERT INTO messages(role, content)
        VALUES ('user', 'hello')
        """
    )

    connection.execute(
        """
        INSERT INTO memories(category, key, value, embedding)
        VALUES ('preferences', 'editor', 'VS Code', NULL)
        """
    )

    connection.execute(
        """
        INSERT INTO missions(
            mission_id,
            goal,
            status,
            created_at,
            updated_at,
            state_json
        )
        VALUES (
            'M-test',
            'test mission',
            'running',
            '2026-09-11T00:00:00+00:00',
            '2026-09-11T00:00:00+00:00',
            '{"mission_id":"M-test"}'
        )
        """
    )

    connection.commit()
    connection.close()


def _record(memory_id="mem-test"):
    return MemoryRecord(
        memory_id=memory_id,
        kind=MemoryKind.PREFERENCE,
        category="preferences",
        key="transport",
        value="Prefers bike rides.",
        source=MemorySource.USER_STATEMENT,
        confidence=0.95,
        importance=0.7,
        created_at="2026-09-11T12:00:00+00:00",
        updated_at="2026-09-11T12:00:00+00:00",
    )


def test_legacy_migration_is_additive_and_conservative(tmp_path):
    db = tmp_path / "legacy.db"
    _create_legacy_database(db)
    connection = sqlite3.connect(db)

    before_messages = connection.execute(
        "SELECT * FROM messages"
    ).fetchall()
    before_missions = connection.execute(
        "SELECT * FROM missions"
    ).fetchall()

    version = migrate_memory_schema(connection)

    assert version == KUMA_DATABASE_SCHEMA_VERSION
    assert (
        connection.execute(
            "PRAGMA user_version"
        ).fetchone()[0]
        == KUMA_DATABASE_SCHEMA_VERSION
    )
    assert connection.execute(
        "SELECT * FROM messages"
    ).fetchall() == before_messages
    assert connection.execute(
        "SELECT * FROM missions"
    ).fetchall() == before_missions

    migrated = connection.execute(
        """
        SELECT
            memory_id,
            kind,
            source,
            confidence,
            importance,
            status,
            subject,
            authority
        FROM memories
        WHERE id = 1
        """
    ).fetchone()

    assert migrated == (
        "legacy-1",
        MemoryKind.UNCLASSIFIED.value,
        MemorySource.IMPORTED.value,
        0.5,
        0.5,
        MemoryStatus.ACTIVE.value,
        "user",
        MEMORY_AUTHORITY_NONE,
    )
    connection.close()


def test_migration_is_idempotent(tmp_path):
    db = tmp_path / "legacy.db"
    _create_legacy_database(db)
    connection = sqlite3.connect(db)

    migrate_memory_schema(connection)

    first = connection.execute(
        """
        SELECT memory_id, kind, source, status, authority
        FROM memories
        """
    ).fetchall()

    migrate_memory_schema(connection)

    second = connection.execute(
        """
        SELECT memory_id, kind, source, status, authority
        FROM memories
        """
    ).fetchall()

    assert second == first

    indexes = {
        row[1]
        for row in connection.execute(
            "PRAGMA index_list(memories)"
        ).fetchall()
    }

    assert "idx_memories_memory_id_unique" in indexes
    assert "idx_memories_category_key" in indexes
    assert "idx_memories_status" in indexes
    assert "idx_memories_kind" in indexes
    connection.close()


def test_nonzero_persisted_memory_authority_fails_closed(tmp_path):
    db = tmp_path / "legacy.db"
    _create_legacy_database(db)
    connection = sqlite3.connect(db)
    migrate_memory_schema(connection)

    connection.execute(
        """
        UPDATE memories
        SET authority = 'EXECUTE'
        WHERE id = 1
        """
    )
    connection.commit()

    with pytest.raises(
        RuntimeError,
        match="non-NONE authority",
    ):
        migrate_memory_schema(connection)

    connection.close()


def test_newer_database_version_is_rejected(tmp_path):
    db = tmp_path / "legacy.db"
    _create_legacy_database(db)
    connection = sqlite3.connect(db)
    connection.execute(
        "PRAGMA user_version = 999"
    )

    with pytest.raises(
        RuntimeError,
        match="newer than this KUMA build",
    ):
        migrate_memory_schema(connection)

    connection.close()


def test_typed_store_round_trip(tmp_path):
    db = tmp_path / "store.db"
    _create_legacy_database(db)
    store = MemoryStore(db)
    record = _record()

    assert store.insert(record) == record
    assert store.load(record.memory_id) == record


def test_typed_store_rejects_duplicate_identity(tmp_path):
    db = tmp_path / "store.db"
    _create_legacy_database(db)
    store = MemoryStore(db)
    record = _record()
    store.insert(record)

    with pytest.raises(
        ValueError,
        match="already exists",
    ):
        store.insert(record)


def test_typed_store_keeps_distinct_versions_of_same_key(tmp_path):
    db = tmp_path / "store.db"
    _create_legacy_database(db)
    store = MemoryStore(db)

    first = _record("mem-v1")
    second = MemoryRecord(
        memory_id="mem-v2",
        kind=first.kind,
        category=first.category,
        key=first.key,
        value="Prefers long bike rides.",
        source=first.source,
        confidence=first.confidence,
        importance=first.importance,
        created_at="2026-09-11T13:00:00+00:00",
        updated_at="2026-09-11T13:00:00+00:00",
        supersedes=first.memory_id,
    )

    store.insert(first)
    store.insert(second)

    assert store.load("mem-v1") == first
    assert store.load("mem-v2") == second


def test_typed_store_unknown_identity_returns_none(tmp_path):
    db = tmp_path / "store.db"
    _create_legacy_database(db)
    store = MemoryStore(db)

    assert store.load("does-not-exist") is None
    assert store.load("") is None


def test_list_records_can_filter_status(tmp_path):
    db = tmp_path / "store.db"
    _create_legacy_database(db)
    store = MemoryStore(db)

    active = _record("mem-active")
    expired = MemoryRecord(
        memory_id="mem-expired",
        kind=MemoryKind.PREFERENCE,
        category="preferences",
        key="old_transport",
        value="Old preference.",
        source=MemorySource.USER_STATEMENT,
        created_at="2026-09-10T12:00:00+00:00",
        updated_at="2026-09-10T12:00:00+00:00",
        status=MemoryStatus.EXPIRED,
    )

    store.insert(active)
    store.insert(expired)

    active_ids = {
        record.memory_id
        for record in store.list_records(
            status=MemoryStatus.ACTIVE
        )
    }

    assert "mem-active" in active_ids
    assert "mem-expired" not in active_ids


def test_legacy_initialize_and_save_api_populate_v1_metadata(
    monkeypatch,
    tmp_path,
):
    try:
        from app.memory import memory
    except ModuleNotFoundError as error:
        if error.name != "sentence_transformers":
            raise

        fake_module = types.ModuleType(
            "sentence_transformers"
        )

        class _FakeSentenceTransformer:
            def __init__(self, *_args, **_kwargs):
                pass

        fake_module.SentenceTransformer = (
            _FakeSentenceTransformer
        )

        monkeypatch.setitem(
            sys.modules,
            "sentence_transformers",
            fake_module,
        )

        memory = importlib.import_module(
            "app.memory.memory"
        )

    db = tmp_path / "compat.db"

    monkeypatch.setattr(memory, "DB_PATH", db)
    monkeypatch.setattr(
        memory,
        "create_embedding",
        lambda _text: [1.0, 0.0],
    )

    memory.initialize_memory()
    memory.save_memory(
        "preferences",
        "editor",
        "VS Code",
    )

    connection = sqlite3.connect(db)
    row = connection.execute(
        """
        SELECT
            memory_id,
            kind,
            source,
            confidence,
            importance,
            status,
            subject,
            authority
        FROM memories
        WHERE category = 'preferences'
          AND key = 'editor'
        """
    ).fetchone()

    assert row[0].startswith("mem-")
    assert row[1:] == (
        MemoryKind.UNCLASSIFIED.value,
        MemorySource.USER_STATEMENT.value,
        1.0,
        0.5,
        MemoryStatus.ACTIVE.value,
        "user",
        MEMORY_AUTHORITY_NONE,
    )
    assert (
        connection.execute(
            "PRAGMA user_version"
        ).fetchone()[0]
        == KUMA_DATABASE_SCHEMA_VERSION
    )
    connection.close()
