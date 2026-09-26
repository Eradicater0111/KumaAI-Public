import json
import sqlite3

import pytest

from app.memory.contracts import (
    MemoryKind,
    MemoryRecord,
    MemorySource,
    MemoryStatus,
)
from app.memory.retrieval import retrieve_memories
from app.memory.schema import (
    KUMA_DATABASE_SCHEMA_VERSION,
    migrate_memory_schema,
)
from app.memory.store import MemoryStore


def _create_database(path):
    connection = sqlite3.connect(path)

    connection.execute("""
        CREATE TABLE messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    connection.execute("""
        CREATE TABLE memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            embedding TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    connection.execute("""
        CREATE TABLE missions (
            mission_id TEXT PRIMARY KEY,
            goal TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            state_json TEXT NOT NULL
        )
    """)

    connection.commit()
    migrate_memory_schema(connection)
    connection.close()


def _record(
    memory_id,
    value,
    *,
    status=MemoryStatus.ACTIVE,
    supersedes=None,
    created_at="2026-09-12T00:00:00+00:00",
    updated_at="2026-09-12T00:00:00+00:00",
    valid_from=None,
    valid_until=None,
):
    return MemoryRecord(
        memory_id=memory_id,
        kind=MemoryKind.PREFERENCE,
        category="preferences",
        key="transport",
        value=value,
        source=MemorySource.USER_EXPLICIT,
        confidence=1.0,
        importance=0.8,
        created_at=created_at,
        updated_at=updated_at,
        valid_from=valid_from,
        valid_until=valid_until,
        status=status,
        supersedes=supersedes,
    )


def test_typed_revision_preserves_history_and_supersedes_old(tmp_path):
    db = tmp_path / "revision.db"
    _create_database(db)
    store = MemoryStore(db)

    old = _record(
        "mem-old",
        "Prefers bikes.",
    )

    new = _record(
        "mem-new",
        "Prefers cars.",
        supersedes=old.memory_id,
        created_at="2026-09-12T01:00:00+00:00",
        updated_at="2026-09-12T01:00:00+00:00",
    )

    store.insert(old)
    assert store.revise(
        old.memory_id,
        new,
    ) == new

    old_after = store.load(
        old.memory_id
    )
    new_after = store.load(
        new.memory_id
    )

    assert old_after.status == MemoryStatus.SUPERSEDED
    assert old_after.value == "Prefers bikes."
    assert new_after.status == MemoryStatus.ACTIVE
    assert new_after.supersedes == old.memory_id


def test_revision_failure_rolls_back_old_status(tmp_path):
    db = tmp_path / "revision.db"
    _create_database(db)
    store = MemoryStore(db)

    old = _record(
        "mem-old",
        "Prefers bikes.",
    )
    blocker = _record(
        "mem-blocker",
        "Other value.",
    )

    store.insert(old)
    store.insert(blocker)

    duplicate = _record(
        "mem-blocker",
        "Prefers cars.",
        supersedes=old.memory_id,
        created_at="2026-09-12T01:00:00+00:00",
        updated_at="2026-09-12T01:00:00+00:00",
    )

    with pytest.raises(
        ValueError,
        match="already exists",
    ):
        store.revise(
            old.memory_id,
            duplicate,
        )

    current = store.load(
        old.memory_id
    )

    assert current.status == MemoryStatus.ACTIVE
    assert current.value == "Prefers bikes."


def test_revision_rejects_cross_key_replacement(tmp_path):
    db = tmp_path / "revision.db"
    _create_database(db)
    store = MemoryStore(db)

    old = _record(
        "mem-old",
        "Prefers bikes.",
    )
    store.insert(old)

    replacement = MemoryRecord(
        memory_id="mem-new",
        kind=old.kind,
        category=old.category,
        key="different_key",
        value="Different concept.",
        source=old.source,
        created_at="2026-09-12T01:00:00+00:00",
        updated_at="2026-09-12T01:00:00+00:00",
        supersedes=old.memory_id,
    )

    with pytest.raises(
        ValueError,
        match="same category and key",
    ):
        store.revise(
            old.memory_id,
            replacement,
        )

    assert (
        store.load(old.memory_id).status
        == MemoryStatus.ACTIVE
    )


def test_only_active_memory_can_be_revised(tmp_path):
    db = tmp_path / "revision.db"
    _create_database(db)
    store = MemoryStore(db)

    old = _record(
        "mem-old",
        "Old value.",
        status=MemoryStatus.RETRACTED,
    )
    store.insert(old)

    replacement = _record(
        "mem-new",
        "New value.",
        supersedes=old.memory_id,
        created_at="2026-09-12T01:00:00+00:00",
        updated_at="2026-09-12T01:00:00+00:00",
    )

    with pytest.raises(
        ValueError,
        match="must be ACTIVE",
    ):
        store.revise(
            old.memory_id,
            replacement,
        )


def test_retract_preserves_value_and_changes_lifecycle(tmp_path):
    db = tmp_path / "revision.db"
    _create_database(db)
    store = MemoryStore(db)

    record = _record(
        "mem-retract",
        "Incorrect preference.",
    )
    store.insert(record)

    changed = store.retract(
        record.memory_id,
        updated_at="2026-09-12T02:00:00+00:00",
    )

    assert changed.status == MemoryStatus.RETRACTED
    assert changed.value == "Incorrect preference."


def test_retract_rejects_timestamp_before_creation(tmp_path):
    db = tmp_path / "revision.db"
    _create_database(db)
    store = MemoryStore(db)

    record = _record(
        "mem-retract",
        "Incorrect preference.",
        created_at="2026-09-12T02:00:00+00:00",
        updated_at="2026-09-12T02:00:00+00:00",
    )
    store.insert(record)

    with pytest.raises(
        ValueError,
        match="earlier than created_at",
    ):
        store.retract(
            record.memory_id,
            updated_at="2026-09-12T01:00:00+00:00",
        )

    assert (
        store.load(record.memory_id).status
        == MemoryStatus.ACTIVE
    )


def test_expire_preserves_value_and_sets_valid_until(tmp_path):
    db = tmp_path / "revision.db"
    _create_database(db)
    store = MemoryStore(db)

    record = _record(
        "mem-expire",
        "Temporary long-term fact.",
        valid_from="2026-09-01T00:00:00+00:00",
    )
    store.insert(record)

    changed = store.expire(
        record.memory_id,
        valid_until="2026-09-12T03:00:00+00:00",
    )

    assert changed.status == MemoryStatus.EXPIRED
    assert (
        changed.valid_until
        == "2026-09-12T03:00:00+00:00"
    )
    assert changed.value == "Temporary long-term fact."


def test_expire_allows_historical_window_before_creation(tmp_path):
    db = tmp_path / "revision.db"
    _create_database(db)
    store = MemoryStore(db)

    record = _record(
        "mem-historical",
        "Historical fact.",
        created_at="2026-09-12T00:00:00+00:00",
        updated_at="2026-09-12T00:00:00+00:00",
        valid_from="2026-09-01T00:00:00+00:00",
    )

    store.insert(record)

    changed = store.expire(
        record.memory_id,
        valid_until="2026-09-09T00:00:00+00:00",
    )

    assert (
        changed.status
        == MemoryStatus.EXPIRED
    )

    assert (
        changed.valid_until
        == "2026-09-09T00:00:00+00:00"
    )

    assert (
        changed.updated_at
        >= changed.created_at
    )


def test_expire_rejects_time_before_valid_from(tmp_path):
    db = tmp_path / "revision.db"
    _create_database(db)
    store = MemoryStore(db)

    record = _record(
        "mem-expire",
        "Temporary long-term fact.",
        valid_from="2026-09-10T00:00:00+00:00",
    )
    store.insert(record)

    with pytest.raises(
        ValueError,
        match="earlier than valid_from",
    ):
        store.expire(
            record.memory_id,
            valid_until="2026-09-09T00:00:00+00:00",
        )

    assert (
        store.load(record.memory_id).status
        == MemoryStatus.ACTIVE
    )


def test_forget_key_physically_removes_all_versions(tmp_path):
    db = tmp_path / "revision.db"
    _create_database(db)
    store = MemoryStore(db)

    old = _record(
        "mem-old",
        "Prefers bikes.",
    )
    new = _record(
        "mem-new",
        "Prefers cars.",
        supersedes=old.memory_id,
        created_at="2026-09-12T01:00:00+00:00",
        updated_at="2026-09-12T01:00:00+00:00",
    )

    store.insert(old)
    store.revise(
        old.memory_id,
        new,
    )

    assert (
        store.forget_key(
            "preferences",
            "transport",
        )
        == 2
    )

    assert store.load("mem-old") is None
    assert store.load("mem-new") is None


def test_forgotten_embedding_cannot_resurface_in_retrieval(tmp_path):
    db = tmp_path / "revision.db"
    _create_database(db)
    store = MemoryStore(db)

    record = _record(
        "mem-delete",
        "Prefers bikes.",
    )
    store.insert(record)

    connection = sqlite3.connect(db)
    connection.execute(
        """
        UPDATE memories
        SET embedding = ?
        WHERE memory_id = ?
        """,
        (
            json.dumps([1.0, 0.0]),
            record.memory_id,
        ),
    )
    connection.commit()
    connection.close()

    assert retrieve_memories(
        "transport",
        db_path=db,
        embedder=lambda _text: [1.0, 0.0],
        threshold=0.0,
        limit=10,
    )

    assert (
        store.forget_key(
            "preferences",
            "transport",
        )
        == 1
    )

    assert retrieve_memories(
        "transport",
        db_path=db,
        embedder=lambda _text: [1.0, 0.0],
        threshold=0.0,
        limit=10,
    ) == []


def test_memory_1f_does_not_require_schema_v2(tmp_path):
    db = tmp_path / "revision.db"
    _create_database(db)

    connection = sqlite3.connect(db)
    version = connection.execute(
        "PRAGMA user_version"
    ).fetchone()[0]
    connection.close()

    assert (
        version
        == KUMA_DATABASE_SCHEMA_VERSION
        == 1
    )
