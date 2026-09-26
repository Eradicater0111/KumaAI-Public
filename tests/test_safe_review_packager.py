from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_packager():
    root = Path(__file__).resolve().parents[1]
    path = root / "scripts" / "kuma_safe_review_packager.py"
    spec = importlib.util.spec_from_file_location("kuma_safe_review_packager", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_malformed_database_filename_is_excluded(tmp_path):
    packager = _load_packager()
    repo = tmp_path / "KumaAI"
    repo.mkdir()
    path = repo / "memory_backup.db]"
    path.write_bytes(b"not even sqlite")
    assert packager.exclude_reason(repo, path) == "runtime-database-name"


def test_sqlite_magic_is_excluded_without_database_suffix(tmp_path):
    packager = _load_packager()
    repo = tmp_path / "KumaAI"
    repo.mkdir()
    path = repo / "innocent-looking-data"
    path.write_bytes(b"SQLite format 3\x00" + b"x" * 32)
    assert packager.exclude_reason(repo, path) == "sqlite-magic"
