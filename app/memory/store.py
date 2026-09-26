"""Versioned typed persistence API for KUMA long-term memory.

MEMORY-1F adds transactional revision, retraction, expiry, and strong
forget semantics while preserving zero-authority memory contracts.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from app.memory.contracts import (
    MemoryKind,
    MemoryRecord,
    MemorySource,
    MemoryStatus,
)
from app.memory.schema import migrate_memory_schema


_RECORD_COLUMNS = """
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
    observed_at,
    valid_from,
    valid_until,
    status,
    supersedes,
    subject,
    project_scope,
    authority
"""


def _default_db_path() -> Path:
    from app.memory.memory import DB_PATH
    return Path(DB_PATH)


def _record_from_row(row) -> MemoryRecord:
    return MemoryRecord(
        memory_id=row[0],
        kind=MemoryKind(row[1]),
        category=row[2],
        key=row[3],
        value=row[4],
        source=MemorySource(row[5]),
        confidence=row[6],
        importance=row[7],
        created_at=row[8],
        updated_at=row[9],
        observed_at=row[10],
        valid_from=row[11],
        valid_until=row[12],
        status=MemoryStatus(row[13]),
        supersedes=row[14],
        subject=row[15],
        project_scope=row[16],
        authority=row[17],
    )


class MemoryStore:
    """Versioned typed store for canonical long-term memories."""

    def __init__(self, db_path=None):
        self.db_path = Path(
            db_path if db_path is not None else _default_db_path()
        )

    def get_connection(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def insert(self, record: MemoryRecord) -> MemoryRecord:
        if not isinstance(record, MemoryRecord):
            raise TypeError(
                "record must be a MemoryRecord."
            )

        with self.get_connection() as connection:
            migrate_memory_schema(connection)

            try:
                connection.execute(
                    f"""
                    INSERT INTO memories (
                        {_RECORD_COLUMNS},
                        embedding
                    )
                    VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        NULL
                    )
                    """,
                    (
                        record.memory_id,
                        record.kind.value,
                        record.category,
                        record.key,
                        record.value,
                        record.source.value,
                        record.confidence,
                        record.importance,
                        record.created_at,
                        record.updated_at,
                        record.observed_at,
                        record.valid_from,
                        record.valid_until,
                        record.status.value,
                        record.supersedes,
                        record.subject,
                        record.project_scope,
                        record.authority,
                    ),
                )

            except sqlite3.IntegrityError as error:
                raise ValueError(
                    "Memory identity already exists: "
                    f"{record.memory_id}"
                ) from error

        return record

    def load(self, memory_id: str) -> MemoryRecord | None:
        memory_id = str(memory_id or "").strip()

        if not memory_id:
            return None

        with self.get_connection() as connection:
            migrate_memory_schema(connection)
            row = connection.execute(
                f"""
                SELECT {_RECORD_COLUMNS}
                FROM memories
                WHERE memory_id = ?
                """,
                (memory_id,),
            ).fetchone()

        if row is None:
            return None

        return _record_from_row(row)

    def list_records(
        self,
        *,
        status: MemoryStatus | None = None,
        limit: int = 100,
    ) -> list[MemoryRecord]:
        if type(limit) is not int:
            raise TypeError(
                "limit must be an integer."
            )

        if not 1 <= limit <= 1000:
            raise ValueError(
                "limit must be between 1 and 1000."
            )

        if (
            status is not None
            and not isinstance(status, MemoryStatus)
        ):
            raise TypeError(
                "status must be MemoryStatus or None."
            )

        with self.get_connection() as connection:
            migrate_memory_schema(connection)

            if status is None:
                rows = connection.execute(
                    f"""
                    SELECT {_RECORD_COLUMNS}
                    FROM memories
                    ORDER BY updated_at DESC, id DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
            else:
                rows = connection.execute(
                    f"""
                    SELECT {_RECORD_COLUMNS}
                    FROM memories
                    WHERE status = ?
                    ORDER BY updated_at DESC, id DESC
                    LIMIT ?
                    """,
                    (status.value, limit),
                ).fetchall()

        return [
            _record_from_row(row)
            for row in rows
        ]

    @staticmethod
    def _parse_timestamp(
        name: str,
        value: str,
    ) -> tuple[str, datetime]:
        if type(value) is not str:
            raise TypeError(
                f"{name} must be a string."
            )

        normalized = value.strip()

        if not normalized:
            raise ValueError(
                f"{name} cannot be empty."
            )

        try:
            parsed = datetime.fromisoformat(
                normalized.replace(
                    "Z",
                    "+00:00",
                )
            )
        except ValueError as error:
            raise ValueError(
                f"{name} must be an ISO-8601 timestamp."
            ) from error

        return normalized, parsed

    @staticmethod
    def _compare_not_before(
        later_name: str,
        later: datetime,
        earlier_name: str,
        earlier: datetime,
    ) -> None:
        try:
            if later < earlier:
                raise ValueError(
                    f"{later_name} cannot be earlier than {earlier_name}."
                )
        except TypeError as error:
            raise ValueError(
                f"{later_name} and {earlier_name} must use "
                "compatible timezone forms."
            ) from error

    def revise(
        self,
        current_memory_id: str,
        replacement: MemoryRecord,
    ) -> MemoryRecord:
        current_memory_id = str(
            current_memory_id or ""
        ).strip()

        if not current_memory_id:
            raise ValueError(
                "current_memory_id cannot be empty."
            )

        if not isinstance(
            replacement,
            MemoryRecord,
        ):
            raise TypeError(
                "replacement must be a MemoryRecord."
            )

        if replacement.status != MemoryStatus.ACTIVE:
            raise ValueError(
                "replacement must be ACTIVE."
            )

        if replacement.supersedes != current_memory_id:
            raise ValueError(
                "replacement.supersedes must reference current_memory_id."
            )

        with self.get_connection() as connection:
            migrate_memory_schema(connection)
            connection.execute(
                "BEGIN IMMEDIATE"
            )

            try:
                row = connection.execute(
                    f"""
                    SELECT {_RECORD_COLUMNS}
                    FROM memories
                    WHERE memory_id = ?
                    """,
                    (current_memory_id,),
                ).fetchone()

                if row is None:
                    raise ValueError(
                        "Current memory does not exist."
                    )

                current = _record_from_row(
                    row
                )

                if current.status != MemoryStatus.ACTIVE:
                    raise ValueError(
                        "Current memory must be ACTIVE."
                    )

                if (
                    replacement.category != current.category
                    or replacement.key != current.key
                ):
                    raise ValueError(
                        "Revision must keep the same category and key."
                    )

                if (
                    replacement.subject != current.subject
                    or replacement.project_scope != current.project_scope
                ):
                    raise ValueError(
                        "Revision must keep the same subject and project scope."
                    )

                _, replacement_created_dt = self._parse_timestamp(
                    "replacement.created_at",
                    replacement.created_at,
                )

                _, current_updated_dt = self._parse_timestamp(
                    "current.updated_at",
                    current.updated_at,
                )

                self._compare_not_before(
                    "replacement.created_at",
                    replacement_created_dt,
                    "current.updated_at",
                    current_updated_dt,
                )

                connection.execute(
                    """
                    UPDATE memories
                    SET status = ?,
                        updated_at = ?
                    WHERE memory_id = ?
                      AND status = ?
                    """,
                    (
                        MemoryStatus.SUPERSEDED.value,
                        replacement.created_at,
                        current_memory_id,
                        MemoryStatus.ACTIVE.value,
                    ),
                )

                try:
                    connection.execute(
                        f"""
                        INSERT INTO memories (
                            {_RECORD_COLUMNS},
                            embedding
                        )
                        VALUES (
                            ?, ?, ?, ?, ?, ?, ?, ?, ?,
                            ?, ?, ?, ?, ?, ?, ?, ?, ?,
                            NULL
                        )
                        """,
                        (
                            replacement.memory_id,
                            replacement.kind.value,
                            replacement.category,
                            replacement.key,
                            replacement.value,
                            replacement.source.value,
                            replacement.confidence,
                            replacement.importance,
                            replacement.created_at,
                            replacement.updated_at,
                            replacement.observed_at,
                            replacement.valid_from,
                            replacement.valid_until,
                            replacement.status.value,
                            replacement.supersedes,
                            replacement.subject,
                            replacement.project_scope,
                            replacement.authority,
                        ),
                    )
                except sqlite3.IntegrityError as error:
                    raise ValueError(
                        "Memory identity already exists: "
                        f"{replacement.memory_id}"
                    ) from error

                connection.commit()

            except BaseException:
                connection.rollback()
                raise

        return replacement

    def retract(
        self,
        memory_id: str,
        *,
        updated_at: str,
    ) -> MemoryRecord:
        normalized, updated_dt = self._parse_timestamp(
            "updated_at",
            updated_at,
        )

        memory_id = str(
            memory_id or ""
        ).strip()

        if not memory_id:
            raise ValueError(
                "memory_id cannot be empty."
            )

        with self.get_connection() as connection:
            migrate_memory_schema(connection)
            connection.execute(
                "BEGIN IMMEDIATE"
            )

            try:
                row = connection.execute(
                    f"""
                    SELECT {_RECORD_COLUMNS}
                    FROM memories
                    WHERE memory_id = ?
                    """,
                    (memory_id,),
                ).fetchone()

                if row is None:
                    raise ValueError(
                        "Memory does not exist."
                    )

                current = _record_from_row(
                    row
                )

                if current.status != MemoryStatus.ACTIVE:
                    raise ValueError(
                        "Memory must be ACTIVE."
                    )

                _, created_dt = self._parse_timestamp(
                    "created_at",
                    current.created_at,
                )

                self._compare_not_before(
                    "updated_at",
                    updated_dt,
                    "created_at",
                    created_dt,
                )

                cursor = connection.execute(
                    """
                    UPDATE memories
                    SET status = ?,
                        updated_at = ?
                    WHERE memory_id = ?
                      AND status = ?
                    """,
                    (
                        MemoryStatus.RETRACTED.value,
                        normalized,
                        memory_id,
                        MemoryStatus.ACTIVE.value,
                    ),
                )

                if cursor.rowcount != 1:
                    raise RuntimeError(
                        "Memory lifecycle update lost its active target."
                    )

                connection.commit()

            except BaseException:
                connection.rollback()
                raise

        result = self.load(
            memory_id
        )

        if result is None:
            raise RuntimeError(
                "Retracted memory disappeared after commit."
            )

        return result

    def expire(
        self,
        memory_id: str,
        *,
        valid_until: str,
    ) -> MemoryRecord:
        normalized, valid_until_dt = self._parse_timestamp(
            "valid_until",
            valid_until,
        )

        memory_id = str(
            memory_id or ""
        ).strip()

        if not memory_id:
            raise ValueError(
                "memory_id cannot be empty."
            )

        with self.get_connection() as connection:
            migrate_memory_schema(connection)
            connection.execute(
                "BEGIN IMMEDIATE"
            )

            try:
                row = connection.execute(
                    f"""
                    SELECT {_RECORD_COLUMNS}
                    FROM memories
                    WHERE memory_id = ?
                    """,
                    (memory_id,),
                ).fetchone()

                if row is None:
                    raise ValueError(
                        "Memory does not exist."
                    )

                current = _record_from_row(
                    row
                )

                if current.status != MemoryStatus.ACTIVE:
                    raise ValueError(
                        "Memory must be ACTIVE."
                    )

                if current.valid_from is not None:
                    _, valid_from_dt = self._parse_timestamp(
                        "valid_from",
                        current.valid_from,
                    )

                    self._compare_not_before(
                        "valid_until",
                        valid_until_dt,
                        "valid_from",
                        valid_from_dt,
                    )

                _, current_updated_dt = self._parse_timestamp(
                    "updated_at",
                    current.updated_at,
                )

                if current_updated_dt.tzinfo is None:
                    mutation_dt = (
                        datetime.now(
                            timezone.utc
                        )
                        .replace(
                            tzinfo=None
                        )
                    )
                else:
                    mutation_dt = (
                        datetime.now(
                            timezone.utc
                        )
                        .astimezone(
                            current_updated_dt.tzinfo
                        )
                    )

                if mutation_dt < current_updated_dt:
                    mutation_dt = current_updated_dt

                mutation_updated_at = (
                    mutation_dt.isoformat()
                )

                cursor = connection.execute(
                    """
                    UPDATE memories
                    SET status = ?,
                        valid_until = ?,
                        updated_at = ?
                    WHERE memory_id = ?
                      AND status = ?
                    """,
                    (
                        MemoryStatus.EXPIRED.value,
                        normalized,
                        mutation_updated_at,
                        memory_id,
                        MemoryStatus.ACTIVE.value,
                    ),
                )

                if cursor.rowcount != 1:
                    raise RuntimeError(
                        "Memory lifecycle update lost its active target."
                    )

                connection.commit()

            except BaseException:
                connection.rollback()
                raise

        result = self.load(
            memory_id
        )

        if result is None:
            raise RuntimeError(
                "Expired memory disappeared after commit."
            )

        return result

    def forget_key(
        self,
        category: str,
        key: str,
    ) -> int:
        category = str(
            category or ""
        ).strip()

        key = str(
            key or ""
        ).strip()

        if not category:
            raise ValueError(
                "category cannot be empty."
            )

        if not key:
            raise ValueError(
                "key cannot be empty."
            )

        with self.get_connection() as connection:
            migrate_memory_schema(connection)

            cursor = connection.execute(
                """
                DELETE FROM memories
                WHERE category = ?
                  AND key = ?
                """,
                (category, key),
            )

            connection.commit()

            return int(
                cursor.rowcount
            )
