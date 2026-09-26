"""KUMA database schema migration for MEMORY-1B.

Database schema v1 extends the existing ``memories`` table additively.
Conversation history and durable mission tables are intentionally untouched.

This module owns schema shape only. It grants no tool or execution authority.
"""

from __future__ import annotations

import sqlite3
import uuid

from app.memory.contracts import (
    MEMORY_AUTHORITY_NONE,
    MemoryKind,
    MemorySource,
    MemoryStatus,
)


KUMA_DATABASE_SCHEMA_VERSION = 1


_MEMORY_V1_COLUMNS = (
    ("memory_id", "TEXT"),
    ("kind", "TEXT NOT NULL DEFAULT 'unclassified'"),
    ("source", "TEXT NOT NULL DEFAULT 'imported'"),
    ("confidence", "REAL NOT NULL DEFAULT 0.5"),
    ("importance", "REAL NOT NULL DEFAULT 0.5"),
    ("observed_at", "TEXT"),
    ("valid_from", "TEXT"),
    ("valid_until", "TEXT"),
    ("status", "TEXT NOT NULL DEFAULT 'active'"),
    ("supersedes", "TEXT"),
    ("subject", "TEXT NOT NULL DEFAULT 'user'"),
    ("project_scope", "TEXT"),
    ("authority", "TEXT NOT NULL DEFAULT 'NONE'"),
)


def new_memory_id() -> str:
    """Return a new opaque identity for a durable memory record."""
    return f"mem-{uuid.uuid4().hex}"


def _table_exists(
    connection: sqlite3.Connection,
    table: str,
) -> bool:
    row = connection.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table'
          AND name = ?
        """,
        (table,),
    ).fetchone()
    return row is not None


def _column_names(
    connection: sqlite3.Connection,
    table: str,
) -> set[str]:
    return {
        str(row[1])
        for row in connection.execute(
            f'PRAGMA table_info("{table}")'
        ).fetchall()
    }


def _ensure_memory_columns(
    connection: sqlite3.Connection,
) -> None:
    columns = _column_names(connection, "memories")

    for name, declaration in _MEMORY_V1_COLUMNS:
        if name in columns:
            continue

        connection.execute(
            f'ALTER TABLE memories '
            f'ADD COLUMN "{name}" {declaration}'
        )
        columns.add(name)


def _backfill_legacy_rows(
    connection: sqlite3.Connection,
) -> None:
    """Conservatively classify pre-MEMORY-1B rows."""

    connection.execute(
        """
        UPDATE memories
        SET memory_id = 'legacy-' || CAST(id AS TEXT)
        WHERE memory_id IS NULL
           OR TRIM(memory_id) = ''
        """
    )

    connection.execute(
        """
        UPDATE memories
        SET kind = ?
        WHERE kind IS NULL
           OR TRIM(kind) = ''
        """,
        (MemoryKind.UNCLASSIFIED.value,),
    )

    connection.execute(
        """
        UPDATE memories
        SET source = ?
        WHERE source IS NULL
           OR TRIM(source) = ''
        """,
        (MemorySource.IMPORTED.value,),
    )

    connection.execute(
        """
        UPDATE memories
        SET confidence = 0.5
        WHERE confidence IS NULL
        """
    )

    connection.execute(
        """
        UPDATE memories
        SET importance = 0.5
        WHERE importance IS NULL
        """
    )

    connection.execute(
        """
        UPDATE memories
        SET status = ?
        WHERE status IS NULL
           OR TRIM(status) = ''
        """,
        (MemoryStatus.ACTIVE.value,),
    )

    connection.execute(
        """
        UPDATE memories
        SET subject = 'user'
        WHERE subject IS NULL
           OR TRIM(subject) = ''
        """
    )

    connection.execute(
        """
        UPDATE memories
        SET authority = ?
        WHERE authority IS NULL
           OR TRIM(authority) = ''
        """,
        (MEMORY_AUTHORITY_NONE,),
    )


def _ensure_memory_indexes(
    connection: sqlite3.Connection,
) -> None:
    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS
        idx_memories_memory_id_unique
        ON memories(memory_id)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_memories_category_key
        ON memories(category, key)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_memories_status
        ON memories(status)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_memories_kind
        ON memories(kind)
        """
    )


def _validate_memory_v1(
    connection: sqlite3.Connection,
) -> None:
    required = {
        "id",
        "category",
        "key",
        "value",
        "embedding",
        "created_at",
        "updated_at",
        *(name for name, _ in _MEMORY_V1_COLUMNS),
    }

    columns = _column_names(connection, "memories")
    missing = sorted(required - columns)

    if missing:
        raise RuntimeError(
            "MEMORY-1B schema is incomplete: "
            + ", ".join(missing)
        )

    bad_identity = connection.execute(
        """
        SELECT COUNT(*)
        FROM memories
        WHERE memory_id IS NULL
           OR TRIM(memory_id) = ''
        """
    ).fetchone()[0]
    if bad_identity:
        raise RuntimeError(
            "MEMORY-1B requires every memory to have a memory_id."
        )

    bad_authority = connection.execute(
        """
        SELECT COUNT(*)
        FROM memories
        WHERE authority IS NULL
           OR authority != ?
        """,
        (MEMORY_AUTHORITY_NONE,),
    ).fetchone()[0]
    if bad_authority:
        raise RuntimeError(
            "Memory persistence contains non-NONE authority."
        )

    bad_confidence = connection.execute(
        """
        SELECT COUNT(*)
        FROM memories
        WHERE confidence IS NULL
           OR confidence < 0.0
           OR confidence > 1.0
        """
    ).fetchone()[0]
    if bad_confidence:
        raise RuntimeError(
            "Memory persistence contains invalid confidence."
        )

    bad_importance = connection.execute(
        """
        SELECT COUNT(*)
        FROM memories
        WHERE importance IS NULL
           OR importance < 0.0
           OR importance > 1.0
        """
    ).fetchone()[0]
    if bad_importance:
        raise RuntimeError(
            "Memory persistence contains invalid importance."
        )


def migrate_memory_schema(
    connection: sqlite3.Connection,
) -> int:
    """Migrate the shared KUMA SQLite database to schema v1.

    The migration is additive, transactional, and idempotent. Only the
    ``memories`` table and its indexes are changed. Existing ``messages``
    and ``missions`` rows are not rewritten.
    """

    if not isinstance(connection, sqlite3.Connection):
        raise TypeError(
            "connection must be sqlite3.Connection."
        )

    current = int(
        connection.execute(
            "PRAGMA user_version"
        ).fetchone()[0]
    )

    if current > KUMA_DATABASE_SCHEMA_VERSION:
        raise RuntimeError(
            "Database schema is newer than this KUMA build: "
            f"{current} > {KUMA_DATABASE_SCHEMA_VERSION}."
        )

    if not _table_exists(connection, "memories"):
        raise RuntimeError(
            "memories table must exist before MEMORY-1B migration."
        )

    connection.execute("SAVEPOINT kuma_memory_1b")

    try:
        _ensure_memory_columns(connection)
        _backfill_legacy_rows(connection)
        _ensure_memory_indexes(connection)
        _validate_memory_v1(connection)

        connection.execute(
            f"PRAGMA user_version = "
            f"{KUMA_DATABASE_SCHEMA_VERSION}"
        )

        connection.execute(
            "RELEASE SAVEPOINT kuma_memory_1b"
        )

    except BaseException:
        connection.execute(
            "ROLLBACK TO SAVEPOINT kuma_memory_1b"
        )
        connection.execute(
            "RELEASE SAVEPOINT kuma_memory_1b"
        )
        raise

    return KUMA_DATABASE_SCHEMA_VERSION
