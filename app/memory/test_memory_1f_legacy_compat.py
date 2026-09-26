import importlib
import sqlite3
import sys
import types

import pytest

from app.memory.contracts import (
    MemoryStatus,
)


def _memory_module(monkeypatch):
    try:
        from app.memory import memory
        return memory
    except ModuleNotFoundError as error:
        if error.name != "sentence_transformers":
            raise

        fake_module = types.ModuleType(
            "sentence_transformers"
        )

        class _FakeSentenceTransformer:
            def __init__(
                self,
                *_args,
                **_kwargs,
            ):
                pass

        fake_module.SentenceTransformer = (
            _FakeSentenceTransformer
        )

        monkeypatch.setitem(
            sys.modules,
            "sentence_transformers",
            fake_module,
        )

        return importlib.import_module(
            "app.memory.memory"
        )


def _prepare(
    monkeypatch,
    tmp_path,
):
    memory = _memory_module(
        monkeypatch
    )
    db = tmp_path / "compat.db"

    monkeypatch.setattr(
        memory,
        "DB_PATH",
        db,
    )
    monkeypatch.setattr(
        memory,
        "create_embedding",
        lambda _text: [1.0, 0.0],
    )

    memory.initialize_memory()

    return memory, db


def test_legacy_save_versions_instead_of_overwriting(
    monkeypatch,
    tmp_path,
):
    memory, db = _prepare(
        monkeypatch,
        tmp_path,
    )

    memory.save_memory(
        "preferences",
        "editor",
        "VS Code",
    )
    memory.save_memory(
        "preferences",
        "editor",
        "Zed",
    )

    connection = sqlite3.connect(
        db
    )
    rows = connection.execute(
        """
        SELECT
            memory_id,
            value,
            status,
            supersedes
        FROM memories
        WHERE category = 'preferences'
          AND key = 'editor'
        ORDER BY id ASC
        """
    ).fetchall()
    connection.close()

    assert len(rows) == 2
    assert rows[0][1] == "VS Code"
    assert (
        rows[0][2]
        == MemoryStatus.SUPERSEDED.value
    )
    assert rows[1][1] == "Zed"
    assert (
        rows[1][2]
        == MemoryStatus.ACTIVE.value
    )
    assert rows[1][3] == rows[0][0]


def test_exact_get_returns_active_revision_only(
    monkeypatch,
    tmp_path,
):
    memory, _db = _prepare(
        monkeypatch,
        tmp_path,
    )

    memory.save_memory(
        "preferences",
        "editor",
        "VS Code",
    )
    memory.save_memory(
        "preferences",
        "editor",
        "Zed",
    )

    assert (
        memory.get_memory(
            "preferences",
            "editor",
        )
        == "Zed"
    )

    assert memory.get_all_memories() == [
        (
            "preferences",
            "editor",
            "Zed",
        )
    ]


def test_legacy_revision_failure_rolls_back_old_status(
    monkeypatch,
    tmp_path,
):
    memory, db = _prepare(
        monkeypatch,
        tmp_path,
    )

    memory.save_memory(
        "preferences",
        "editor",
        "VS Code",
    )

    connection = sqlite3.connect(
        db
    )
    old_id = connection.execute(
        """
        SELECT memory_id
        FROM memories
        WHERE category = 'preferences'
          AND key = 'editor'
        """
    ).fetchone()[0]
    connection.close()

    monkeypatch.setattr(
        memory,
        "new_memory_id",
        lambda: old_id,
    )

    with pytest.raises(
        sqlite3.IntegrityError,
    ):
        memory.save_memory(
            "preferences",
            "editor",
            "Zed",
        )

    connection = sqlite3.connect(
        db
    )
    rows = connection.execute(
        """
        SELECT value, status
        FROM memories
        WHERE category = 'preferences'
          AND key = 'editor'
        """
    ).fetchall()
    connection.close()

    assert rows == [
        (
            "VS Code",
            MemoryStatus.ACTIVE.value,
        )
    ]


def test_legacy_delete_removes_all_historical_versions(
    monkeypatch,
    tmp_path,
):
    memory, db = _prepare(
        monkeypatch,
        tmp_path,
    )

    memory.save_memory(
        "preferences",
        "editor",
        "VS Code",
    )
    memory.save_memory(
        "preferences",
        "editor",
        "Zed",
    )

    assert memory.delete_memory(
        "preferences",
        "editor",
    )

    connection = sqlite3.connect(
        db
    )
    count = connection.execute(
        """
        SELECT COUNT(*)
        FROM memories
        WHERE category = 'preferences'
          AND key = 'editor'
        """
    ).fetchone()[0]
    connection.close()

    assert count == 0
