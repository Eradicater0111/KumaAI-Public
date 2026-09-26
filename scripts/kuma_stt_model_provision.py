#!/usr/bin/env python3

"""
KUMA STT-1E explicit model provisioner.

MODEL DOWNLOAD != APP STARTUP
MODEL PROVISIONING != MODEL LOAD
MODEL PROVISIONING != MICROPHONE CONSENT
MODEL READY != RECOGNIZER START
MODEL READY != USER TURN
MODEL READY != TOOL PERMISSION
AUTHORITY:NONE
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
from importlib.metadata import (
    PackageNotFoundError,
    version as distribution_version,
)
import os
from pathlib import Path
import shutil
import sys
import tempfile
from typing import Callable


ROOT = (
    Path(__file__)
    .resolve()
    .parents[1]
)

CONTRACT_PATH = (
    ROOT
    / "stt-model.env"
)

DEFAULT_MODELS_ROOT = (
    Path.home()
    / ".kuma"
    / "models"
)


_REQUIRED_KEYS = {
    "KUMA_STT_PYTHON_SERIES",
    "KUMA_STT_PROVIDER_PACKAGE",
    "KUMA_STT_PROVIDER_VERSION",
    "KUMA_STT_MLX_PACKAGE",
    "KUMA_STT_MLX_VERSION",
    "KUMA_STT_HUB_PACKAGE",
    "KUMA_STT_HUB_VERSION",
    "KUMA_STT_MODEL_REPO",
    "KUMA_STT_MODEL_REVISION",
    "KUMA_STT_MODEL_RELATIVE_PATH",
    "KUMA_STT_MODEL_GITATTRIBUTES_SHA256",
    "KUMA_STT_MODEL_README_SHA256",
    "KUMA_STT_MODEL_CONFIG_SHA256",
    "KUMA_STT_MODEL_WEIGHTS_SHA256",
}


@dataclass(
    frozen=True,
    slots=True,
)
class ModelContract:
    python_series: tuple[int, int]

    provider_package: str
    provider_version: str

    mlx_package: str
    mlx_version: str

    hub_package: str
    hub_version: str

    repo_id: str
    revision: str

    relative_path: Path

    files: tuple[
        tuple[str, str],
        ...,
    ]


def _sha256_file(
    path: Path,
) -> str:
    digest = hashlib.sha256()

    with path.open(
        "rb"
    ) as handle:
        for chunk in iter(
            lambda: handle.read(
                1024 * 1024
            ),
            b"",
        ):
            digest.update(
                chunk
            )

    return digest.hexdigest()


def _sha256_hex(
    value: str,
) -> bool:
    return (
        len(value) == 64
        and all(
            character
            in "0123456789abcdef"
            for character
            in value
        )
    )


def _read_contract_values(
    path: Path,
) -> dict[str, str]:
    if not path.is_file():
        raise ValueError(
            f"missing STT model contract: {path}"
        )

    values: dict[str, str] = {}

    for raw_line in path.read_text(
        encoding="utf-8"
    ).splitlines():

        line = raw_line.strip()

        if (
            not line
            or line.startswith("#")
        ):
            continue

        if "=" not in line:
            raise ValueError(
                "invalid STT model contract line"
            )

        key, value = (
            part.strip()
            for part
            in line.split(
                "=",
                1,
            )
        )

        if (
            not key
            or not value
        ):
            raise ValueError(
                "empty STT model contract key/value"
            )

        if key in values:
            raise ValueError(
                f"duplicate STT model contract key: {key}"
            )

        values[key] = value

    missing = (
        _REQUIRED_KEYS
        - set(values)
    )

    extra = (
        set(values)
        - _REQUIRED_KEYS
    )

    if missing:
        raise ValueError(
            "missing STT model contract key(s): "
            + ", ".join(
                sorted(
                    missing
                )
            )
        )

    if extra:
        raise ValueError(
            "unknown STT model contract key(s): "
            + ", ".join(
                sorted(
                    extra
                )
            )
        )

    return values


def load_contract(
    path: Path = CONTRACT_PATH,
) -> ModelContract:
    values = (
        _read_contract_values(
            path
        )
    )

    series_parts = (
        values[
            "KUMA_STT_PYTHON_SERIES"
        ].split(".")
    )

    if (
        len(series_parts)
        != 2
        or not all(
            part.isdigit()
            for part
            in series_parts
        )
    ):
        raise ValueError(
            "invalid STT Python series"
        )

    python_series = (
        int(
            series_parts[0]
        ),
        int(
            series_parts[1]
        ),
    )

    revision = values[
        "KUMA_STT_MODEL_REVISION"
    ]

    if (
        len(revision) != 40
        or any(
            character
            not in "0123456789abcdef"
            for character
            in revision
        )
    ):
        raise ValueError(
            "model revision must be an immutable "
            "40-character lowercase git commit"
        )

    relative_path = Path(
        values[
            "KUMA_STT_MODEL_RELATIVE_PATH"
        ]
    )

    if (
        relative_path.is_absolute()
        or ".."
        in relative_path.parts
    ):
        raise ValueError(
            "model relative path must stay "
            "inside the KUMA model root"
        )

    files = (
        (
            ".gitattributes",
            values[
                "KUMA_STT_MODEL_GITATTRIBUTES_SHA256"
            ],
        ),
        (
            "README.md",
            values[
                "KUMA_STT_MODEL_README_SHA256"
            ],
        ),
        (
            "config.json",
            values[
                "KUMA_STT_MODEL_CONFIG_SHA256"
            ],
        ),
        (
            "weights.npz",
            values[
                "KUMA_STT_MODEL_WEIGHTS_SHA256"
            ],
        ),
    )

    for (
        filename,
        digest,
    ) in files:

        if (
            not filename
            or Path(
                filename
            ).name
            != filename
        ):
            raise ValueError(
                "STT model contract files "
                "must be top-level filenames"
            )

        if not _sha256_hex(
            digest
        ):
            raise ValueError(
                f"invalid sha256 for {filename}"
            )

    return ModelContract(
        python_series=python_series,
        provider_package=values[
            "KUMA_STT_PROVIDER_PACKAGE"
        ],
        provider_version=values[
            "KUMA_STT_PROVIDER_VERSION"
        ],
        mlx_package=values[
            "KUMA_STT_MLX_PACKAGE"
        ],
        mlx_version=values[
            "KUMA_STT_MLX_VERSION"
        ],
        hub_package=values[
            "KUMA_STT_HUB_PACKAGE"
        ],
        hub_version=values[
            "KUMA_STT_HUB_VERSION"
        ],
        repo_id=values[
            "KUMA_STT_MODEL_REPO"
        ],
        revision=revision,
        relative_path=relative_path,
        files=files,
    )


def provider_errors(
    contract: ModelContract,
) -> list[str]:
    errors: list[str] = []

    actual_series = (
        sys.version_info.major,
        sys.version_info.minor,
    )

    if (
        actual_series
        != contract.python_series
    ):
        errors.append(
            "STT provisioner must run under "
            f"Python {contract.python_series[0]}."
            f"{contract.python_series[1]}.x; "
            f"found {sys.version_info.major}."
            f"{sys.version_info.minor}."
            f"{sys.version_info.micro}"
        )

    for (
        package,
        expected,
    ) in (
        (
            contract.provider_package,
            contract.provider_version,
        ),
        (
            contract.mlx_package,
            contract.mlx_version,
        ),
        (
            contract.hub_package,
            contract.hub_version,
        ),
    ):
        try:
            actual = (
                distribution_version(
                    package
                )
            )
        except PackageNotFoundError:
            errors.append(
                f"required package missing: {package}"
            )
            continue

        if actual != expected:
            errors.append(
                f"{package} must be "
                f"{expected}; found {actual}"
            )

    return errors


def verify_destination(
    destination: Path,
    expected_files: tuple[
        tuple[str, str],
        ...,
    ],
) -> list[str]:
    if not destination.is_dir():
        return [
            f"model directory missing: {destination}"
        ]

    errors: list[str] = []

    expected_names = {
        name
        for (
            name,
            _digest,
        )
        in expected_files
    }

    actual_names: set[str] = set()

    for child in destination.iterdir():
        actual_names.add(
            child.name
        )

        if child.is_symlink():
            errors.append(
                f"model file must not be symlink: "
                f"{child.name}"
            )

        elif not child.is_file():
            errors.append(
                f"unexpected non-file in model: "
                f"{child.name}"
            )

    missing = (
        expected_names
        - actual_names
    )

    extra = (
        actual_names
        - expected_names
    )

    if missing:
        errors.append(
            "model missing file(s): "
            + ", ".join(
                sorted(
                    missing
                )
            )
        )

    if extra:
        errors.append(
            "model has unexpected file(s): "
            + ", ".join(
                sorted(
                    extra
                )
            )
        )

    for (
        filename,
        expected_digest,
    ) in expected_files:

        path = (
            destination
            / filename
        )

        if (
            not path.is_file()
            or path.is_symlink()
        ):
            continue

        actual_digest = (
            _sha256_file(
                path
            )
        )

        if (
            actual_digest
            != expected_digest
        ):
            errors.append(
                f"sha256 mismatch: {filename}"
            )

    return errors


def _default_downloader(
    *,
    repo_id: str,
    revision: str,
    filename: str,
    cache_dir: Path,
) -> Path:
    # Imported only on explicit --install when a
    # verified local destination is absent.
    from huggingface_hub import (
        hf_hub_download,
    )

    downloaded = hf_hub_download(
        repo_id=repo_id,
        revision=revision,
        filename=filename,
        cache_dir=str(
            cache_dir
        ),
    )

    return Path(
        downloaded
    )


Downloader = Callable[
    ...,
    Path,
]


def provision_model(
    contract: ModelContract,
    destination: Path,
    *,
    downloader: Downloader = _default_downloader,
) -> str:
    if destination.exists():
        raise FileExistsError(
            "refusing to replace an existing "
            "model destination"
        )

    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    work_root = Path(
        tempfile.mkdtemp(
            prefix=(
                f".{destination.name}."
                "provision-"
            ),
            dir=str(
                destination.parent
            ),
        )
    )

    stage = (
        work_root
        / "payload"
    )

    cache = (
        work_root
        / "hub-cache"
    )

    stage.mkdir()
    cache.mkdir()

    try:
        for (
            filename,
            expected_digest,
        ) in contract.files:

            source = Path(
                downloader(
                    repo_id=contract.repo_id,
                    revision=contract.revision,
                    filename=filename,
                    cache_dir=cache,
                )
            )

            if not source.is_file():
                raise RuntimeError(
                    "download did not produce "
                    f"a file: {filename}"
                )

            source_digest = (
                _sha256_file(
                    source
                )
            )

            if (
                source_digest
                != expected_digest
            ):
                raise RuntimeError(
                    "download sha256 mismatch: "
                    f"{filename}"
                )

            target = (
                stage
                / filename
            )

            shutil.copyfile(
                source,
                target,
            )

        stage_errors = (
            verify_destination(
                stage,
                contract.files,
            )
        )

        if stage_errors:
            raise RuntimeError(
                "staged model verification failed: "
                + "; ".join(
                    stage_errors
                )
            )

        if destination.exists():
            raise FileExistsError(
                "model destination appeared "
                "during provisioning"
            )

        os.replace(
            stage,
            destination,
        )

        published_errors = (
            verify_destination(
                destination,
                contract.files,
            )
        )

        if published_errors:
            raise RuntimeError(
                "published model verification failed: "
                + "; ".join(
                    published_errors
                )
            )

        return "installed"

    finally:
        shutil.rmtree(
            work_root,
            ignore_errors=True,
        )


def _default_destination(
    contract: ModelContract,
) -> Path:
    return (
        DEFAULT_MODELS_ROOT
        / contract.relative_path
    )


def _print_contract(
    contract: ModelContract,
    destination: Path,
) -> None:
    print(
        "provider    → "
        f"{contract.provider_package}"
        f"=={contract.provider_version}"
    )

    print(
        "mlx         → "
        f"{contract.mlx_package}"
        f"=={contract.mlx_version}"
    )

    print(
        "hub         → "
        f"{contract.hub_package}"
        f"=={contract.hub_version}"
    )

    print(
        "model repo  →",
        contract.repo_id,
    )

    print(
        "revision    →",
        contract.revision,
    )

    print(
        "destination →",
        destination,
    )

    print()
    print("required files:")

    for (
        filename,
        digest,
    ) in contract.files:
        print(
            f"  {filename}"
            f"  sha256={digest}"
        )


def _emit_errors(
    errors: list[str],
) -> None:
    for error in errors:
        print(
            "ERROR —",
            error,
            file=sys.stderr,
        )


def main(
    argv: list[str] | None = None,
) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Provision or verify the immutable "
            "KUMA local STT model."
        )
    )

    mode = (
        parser.add_mutually_exclusive_group(
            required=True
        )
    )

    mode.add_argument(
        "--plan",
        action="store_true",
        help=(
            "show the pinned provisioning plan; "
            "perform no mutation"
        ),
    )

    mode.add_argument(
        "--check-only",
        action="store_true",
        help=(
            "verify provider and local model; "
            "perform no mutation"
        ),
    )

    mode.add_argument(
        "--install",
        action="store_true",
        help=(
            "explicitly download and atomically "
            "publish the model if absent"
        ),
    )

    parser.add_argument(
        "--destination",
        type=Path,
        default=None,
        help=(
            "override the local model destination"
        ),
    )

    args = parser.parse_args(
        argv
    )

    try:
        contract = (
            load_contract()
        )
    except Exception as error:
        print(
            "ERROR — invalid STT model contract: "
            f"{error}",
            file=sys.stderr,
        )
        return 1

    destination = (
        args.destination.expanduser()
        if args.destination
        is not None
        else _default_destination(
            contract
        )
    )

    destination = (
        destination.resolve()
    )

    if args.plan:
        print(
            "KUMA STT-1E → provisioning plan"
        )

        _print_contract(
            contract,
            destination,
        )

        print()
        print(
            "PLAN → network/download occurs "
            "only with explicit --install"
        )

        print(
            "PLAN → verify every file hash "
            "before publication"
        )

        print(
            "PLAN → atomically publish only "
            "a complete verified payload"
        )

        print(
            "PLAN → do not load model"
        )

        print(
            "PLAN → do not start recognizer"
        )

        print(
            "PLAN → do not open microphone"
        )

        print(
            "AUTHORITY → NONE"
        )

        return 0

    environment_errors = (
        provider_errors(
            contract
        )
    )

    if environment_errors:
        _emit_errors(
            environment_errors
        )
        return 1

    if args.check_only:
        model_errors = (
            verify_destination(
                destination,
                contract.files,
            )
        )

        if model_errors:
            _emit_errors(
                model_errors
            )
            return 1

        print(
            "KUMA STT-1E → READY"
        )

        _print_contract(
            contract,
            destination,
        )

        print()
        print(
            "model load → NOT PERFORMED"
        )

        print(
            "recognizer start → NOT PERFORMED"
        )

        print(
            "microphone → NOT OPENED"
        )

        print(
            "AUTHORITY → NONE"
        )

        return 0

    # Explicit --install.
    if destination.exists():
        model_errors = (
            verify_destination(
                destination,
                contract.files,
            )
        )

        if model_errors:
            _emit_errors(
                [
                    (
                        "existing model destination "
                        "does not match immutable "
                        "contract"
                    ),
                    *model_errors,
                ]
            )

            return 1

        print(
            "model → REUSE exact verified payload"
        )

        print(
            "download → NOT PERFORMED"
        )

        print(
            "model load → NOT PERFORMED"
        )

        print(
            "recognizer start → NOT PERFORMED"
        )

        print(
            "microphone → NOT OPENED"
        )

        print(
            "AUTHORITY → NONE"
        )

        return 0

    print(
        "model → DOWNLOAD explicit immutable revision"
    )

    print(
        "repo  →",
        contract.repo_id,
    )

    print(
        "rev   →",
        contract.revision,
    )

    try:
        result = (
            provision_model(
                contract,
                destination,
            )
        )
    except Exception as error:
        print(
            "ERROR — STT model provisioning failed: "
            f"{error}",
            file=sys.stderr,
        )
        return 1

    print(
        "model →",
        result.upper(),
    )

    print(
        "destination →",
        destination,
    )

    print(
        "model load → NOT PERFORMED"
    )

    print(
        "recognizer start → NOT PERFORMED"
    )

    print(
        "microphone → NOT OPENED"
    )

    print(
        "AUTHORITY → NONE"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
