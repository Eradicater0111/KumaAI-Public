from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = (
    Path(__file__)
    .resolve()
    .parents[2]
)

PROVISIONER = (
    ROOT
    / "scripts"
    / "kuma_stt_model_provision.py"
)

CONTRACT = (
    ROOT
    / "stt-model.env"
)


@pytest.fixture
def provisioner():
    name = (
        "kuma_stt_1e_provisioner_test"
    )

    spec = (
        importlib.util.spec_from_file_location(
            name,
            PROVISIONER,
        )
    )

    assert spec is not None
    assert spec.loader is not None

    module = (
        importlib.util.module_from_spec(
            spec
        )
    )

    sys.modules[name] = module

    try:
        spec.loader.exec_module(
            module
        )

        yield module

    finally:
        sys.modules.pop(
            name,
            None,
        )


def _digest(
    payload: bytes,
) -> str:
    return hashlib.sha256(
        payload
    ).hexdigest()


def _synthetic_contract(
    provisioner,
    payloads,
):
    return provisioner.ModelContract(
        python_series=(3, 12),
        provider_package="mlx-whisper",
        provider_version="0.4.3",
        mlx_package="mlx",
        mlx_version="0.32.2",
        hub_package="huggingface-hub",
        hub_version="2.0.0",
        repo_id="example/model",
        revision="1" * 40,
        relative_path=Path(
            "stt/example/model"
        ),
        files=tuple(
            (
                name,
                _digest(
                    payload
                ),
            )
            for (
                name,
                payload,
            )
            in payloads.items()
        ),
    )


def test_stt_1e_provisioner_exists_compiles_and_has_no_runtime_authority():
    source = (
        PROVISIONER.read_text(
            encoding="utf-8"
        )
    )

    compile(
        source,
        str(
            PROVISIONER
        ),
        "exec",
    )

    for marker in (
        "MODEL DOWNLOAD != APP STARTUP",
        "MODEL PROVISIONING != MODEL LOAD",
        "MODEL PROVISIONING != MICROPHONE CONSENT",
        "MODEL READY != RECOGNIZER START",
        "MODEL READY != USER TURN",
        "MODEL READY != TOOL PERMISSION",
        "AUTHORITY:NONE",
    ):
        assert marker in source

    for forbidden in (
        "from app.",
        "import app.",
        "QApplication",
        "QAudioSource",
        "KumaAgent",
        "KumaRuntimeV2LiveOwner",
        "start_microphone",
        "start_capture",
    ):
        assert forbidden not in source


def test_stt_1e_frozen_contract_is_exact(
    provisioner,
):
    contract = (
        provisioner.load_contract(
            CONTRACT
        )
    )

    assert (
        contract.python_series
        == (3, 12)
    )

    assert (
        contract.provider_package
        == "mlx-whisper"
    )

    assert (
        contract.provider_version
        == "0.4.3"
    )

    assert (
        contract.mlx_package
        == "mlx"
    )

    assert (
        contract.mlx_version
        == "0.32.2"
    )

    assert (
        contract.hub_package
        == "huggingface-hub"
    )

    assert (
        contract.hub_version
        == "2.0.0"
    )

    assert (
        contract.repo_id
        == "mlx-community/whisper-tiny-mlx"
    )

    assert (
        contract.revision
        == (
            "6caf9c55601caafbe6508a8b0d216bdf"
            "4783c4e8"
        )
    )

    assert (
        contract.relative_path
        == Path(
            "stt/mlx-whisper/whisper-tiny-mlx"
        )
    )

    assert dict(
        contract.files
    ) == {
        ".gitattributes": (
            "11ad7efa24975ee4b0c3c3a38ed18737"
            "f0658a5f75a0a96787b576a78a023361"
        ),
        "README.md": (
            "64166743e9db4d6907c1655930648089e"
            "0f7c895d950b20409d13b7ccfe9f948"
        ),
        "config.json": (
            "aaff20ce8f69beddee3fe0cc1e08f4e9"
            "2f58586cb9f12ba00a6f73cbfec1cb1c"
        ),
        "weights.npz": (
            "0e03a5993d6eea43b07ee2dcc772b0e4"
            "cef5bb227257dacc24bf289387d49186"
        ),
    }


def test_stt_1e_plan_is_non_mutating(
    tmp_path,
):
    destination = (
        tmp_path
        / "model"
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(
                PROVISIONER
            ),
            "--plan",
            "--destination",
            str(
                destination
            ),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert (
        completed.returncode
        == 0
    ), (
        completed.stdout
        + completed.stderr
    )

    assert (
        not destination.exists()
    )

    assert (
        "network/download occurs "
        "only with explicit --install"
        in completed.stdout
    )

    assert (
        "AUTHORITY → NONE"
        in completed.stdout
    )


def test_stt_1e_destination_verification_is_exact(
    provisioner,
    tmp_path,
):
    payloads = {
        "config.json": b"{}",
        "weights.npz": b"weights",
    }

    destination = (
        tmp_path
        / "model"
    )

    destination.mkdir()

    files = []

    for (
        name,
        payload,
    ) in payloads.items():
        (
            destination
            / name
        ).write_bytes(
            payload
        )

        files.append(
            (
                name,
                _digest(
                    payload
                ),
            )
        )

    assert (
        provisioner.verify_destination(
            destination,
            tuple(
                files
            ),
        )
        == []
    )

    (
        destination
        / "unexpected.txt"
    ).write_text(
        "unexpected"
    )

    errors = (
        provisioner.verify_destination(
            destination,
            tuple(
                files
            ),
        )
    )

    assert any(
        "unexpected file"
        in error
        for error
        in errors
    )


def test_stt_1e_fake_download_is_hash_verified_and_atomically_published(
    provisioner,
    tmp_path,
):
    payloads = {
        ".gitattributes": b"attributes",
        "README.md": b"readme",
        "config.json": b'{"model":"tiny"}',
        "weights.npz": b"synthetic-weights",
    }

    contract = (
        _synthetic_contract(
            provisioner,
            payloads,
        )
    )

    upstream = (
        tmp_path
        / "upstream"
    )

    upstream.mkdir()

    for (
        name,
        payload,
    ) in payloads.items():
        (
            upstream
            / name
        ).write_bytes(
            payload
        )

    destination = (
        tmp_path
        / "models"
        / "model"
    )

    calls = []

    def fake_downloader(
        *,
        repo_id,
        revision,
        filename,
        cache_dir,
    ):
        calls.append(
            (
                repo_id,
                revision,
                filename,
                Path(
                    cache_dir
                ),
            )
        )

        return (
            upstream
            / filename
        )

    result = (
        provisioner.provision_model(
            contract,
            destination,
            downloader=fake_downloader,
        )
    )

    assert result == "installed"

    assert (
        provisioner.verify_destination(
            destination,
            contract.files,
        )
        == []
    )

    assert all(
        not (
            destination
            / name
        ).is_symlink()
        for name
        in payloads
    )

    assert [
        call[2]
        for call
        in calls
    ] == list(
        payloads
    )

    assert all(
        call[0]
        == contract.repo_id
        for call
        in calls
    )

    assert all(
        call[1]
        == contract.revision
        for call
        in calls
    )


def test_stt_1e_hash_failure_never_publishes_destination(
    provisioner,
    tmp_path,
):
    payloads = {
        "config.json": b"expected-config",
        "weights.npz": b"expected-weights",
    }

    contract = (
        _synthetic_contract(
            provisioner,
            payloads,
        )
    )

    corrupt = (
        tmp_path
        / "corrupt"
    )

    corrupt.mkdir()

    for name in payloads:
        (
            corrupt
            / name
        ).write_bytes(
            b"WRONG"
        )

    destination = (
        tmp_path
        / "models"
        / "model"
    )

    def fake_downloader(
        *,
        repo_id,
        revision,
        filename,
        cache_dir,
    ):
        return (
            corrupt
            / filename
        )

    with pytest.raises(
        RuntimeError
    ):
        provisioner.provision_model(
            contract,
            destination,
            downloader=fake_downloader,
        )

    assert (
        not destination.exists()
    )


def test_stt_1e_existing_destination_is_never_replaced(
    provisioner,
    tmp_path,
):
    contract = (
        _synthetic_contract(
            provisioner,
            {
                "config.json": b"good",
            },
        )
    )

    destination = (
        tmp_path
        / "model"
    )

    destination.mkdir()

    existing = (
        destination
        / "keep.txt"
    )

    existing.write_bytes(
        b"preserve-me"
    )

    called = False

    def fake_downloader(
        **kwargs,
    ):
        nonlocal called

        called = True

        raise AssertionError(
            "downloader must not run"
        )

    with pytest.raises(
        FileExistsError
    ):
        provisioner.provision_model(
            contract,
            destination,
            downloader=fake_downloader,
        )

    assert called is False

    assert (
        existing.read_bytes()
        == b"preserve-me"
    )
