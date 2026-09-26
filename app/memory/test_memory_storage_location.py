import json
import os
from pathlib import Path
import subprocess
import sys


def _clean_import_storage_snapshot(
    tmp_path,
):
    """
    Observe KUMA's true default memory-storage contract in a
    fresh interpreter.

    The main pytest process may intentionally monkeypatch
    app.memory.memory.DB_PATH for test isolation, so it must
    not be used to prove the production default.
    """

    repository_root = (
        Path(__file__)
        .resolve()
        .parent
        .parent
        .parent
    )

    fake_home = (
        tmp_path
        / "home"
    )

    fake_home.mkdir()

    probe = r'''
import json
from pathlib import Path
import stat

import app.memory.memory as memory


payload = {
    "home": str(Path.home()),
    "data_dir": str(memory.DATA_DIR),
    "db_path": str(memory.DB_PATH),
    "data_dir_exists": memory.DATA_DIR.is_dir(),
    "data_dir_mode": oct(
        stat.S_IMODE(
            memory.DATA_DIR.stat().st_mode
        )
    ),
}

print(
    "KUMA_STORAGE_SNAPSHOT="
    + json.dumps(
        payload,
        sort_keys=True,
    )
)
'''

    environment = dict(
        os.environ
    )

    environment["HOME"] = str(
        fake_home
    )

    result = subprocess.run(
        [
            sys.executable,
            "-B",
            "-c",
            probe,
        ],
        cwd=repository_root,
        env=environment,
        text=True,
        capture_output=True,
        check=True,
    )

    marker = (
        "KUMA_STORAGE_SNAPSHOT="
    )

    matching = [
        line
        for line in result.stdout.splitlines()
        if line.startswith(marker)
    ]

    assert len(matching) == 1

    return (
        json.loads(
            matching[0][
                len(marker):
            ]
        ),
        repository_root,
        fake_home,
    )


def test_default_memory_storage_is_user_application_support(
    tmp_path,
):
    snapshot, _, fake_home = (
        _clean_import_storage_snapshot(
            tmp_path
        )
    )

    expected_data_dir = (
        fake_home
        / "Library"
        / "Application Support"
        / "Kuma"
        / "data"
    )

    expected_db_path = (
        expected_data_dir
        / "kuma_memory.db"
    )

    assert (
        Path(snapshot["home"])
        == fake_home
    )

    assert (
        Path(snapshot["data_dir"])
        == expected_data_dir
    )

    assert (
        Path(snapshot["db_path"])
        == expected_db_path
    )

    assert (
        snapshot[
            "data_dir_exists"
        ]
        is True
    )

    assert (
        snapshot[
            "data_dir_mode"
        ]
        == "0o700"
    )


def test_default_memory_storage_is_outside_repository(
    tmp_path,
):
    (
        snapshot,
        repository_root,
        _,
    ) = _clean_import_storage_snapshot(
        tmp_path
    )

    db_path = Path(
        snapshot["db_path"]
    ).resolve()

    assert not db_path.is_relative_to(
        repository_root
    )
