#!/usr/bin/env python3
"""
KUMA Bootstrap-A read-only environment readiness checker.

This checker validates dependency/bootstrap facts only.

BOOTSTRAP != RUNTIME AUTHORITY
DEPENDENCY CHECK != TOOL PERMISSION
ENVIRONMENT DETECTION != EXECUTION AUTHORIZATION
OPTIONAL CAPABILITY MISSING != CORE STARTUP CORRUPTION
VOICE PROCESS OWNER != AGENT EXECUTION OWNER
AUTHORITY:NONE

It does not:
- start KUMA,
- start Ollama,
- start a model,
- start microphone capture,
- synthesize speech,
- execute agent tools,
- mutate memory,
- mutate runtime state,
- install packages.
"""

from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path
import shutil
import subprocess
import sys


ROOT = (
    Path(__file__)
    .resolve()
    .parents[1]
)

VERSION_CONTRACT = (
    ROOT
    / "bootstrap-versions.env"
)

MAIN_REQUIREMENTS = (
    ROOT
    / "requirements.txt"
)

VOICE_REQUIREMENTS = (
    ROOT
    / "requirements-voice.txt"
)

DEV_REQUIREMENTS = (
    ROOT
    / "requirements-dev.txt"
)

VOICE_PYTHON = (
    ROOT
    / ".voice-venv"
    / "bin"
    / "python"
)

CANONICAL_GUI = (
    "python -m app.main"
)

CANONICAL_CLI = (
    "python -m app.agent.kuma_runtime"
)

MAIN_PYTHON_SERIES = (
    3,
    14,
)

VOICE_PYTHON_SERIES = (
    3,
    12,
)

MAIN_IMPORTS = (
    "PySide6",
    "ollama",
    "google.genai",
    "httpx",
    "dotenv",
    "sentence_transformers",
)

VOICE_IMPORTS = (
    "kokoro_mlx",
    "mlx_whisper",
    "mlx",
    "numpy",
    "soundfile",
)

REQUIRED_MACOS_BINARIES = (
    "/usr/bin/say",
    "/usr/bin/afplay",
)

REQUIRED_PATH_BINARIES = (
    "ollama",
)

OPTIONAL_BINARIES = (
    "ffmpeg",
    "ffprobe",
)

MAIN_REQUIRED_PINS = (
    "PySide6==6.11.1",
    "ollama==0.6.2",
    "google-genai==2.18.1",
    "httpx==0.28.1",
    "python-dotenv==1.2.2",
    "sentence-transformers==5.7.0",
)

VOICE_REQUIRED_PINS = (
    "kokoro-mlx==0.1.2",
    "mlx-whisper==0.4.3",
    "mlx==0.32.2",
    "numpy==2.5.3",
    "soundfile==0.14.0",
    "huggingface-hub==2.0.0",
)


def _read_noncomment_lines(
    path: Path,
) -> tuple[str, ...]:
    return tuple(
        line.strip()
        for line in path.read_text().splitlines()
        if (
            line.strip()
            and not line.lstrip().startswith("#")
        )
    )


def _check_python_series(
    expected: tuple[int, int],
) -> str | None:
    current = (
        sys.version_info.major,
        sys.version_info.minor,
    )

    if current != expected:
        return (
            "main Python must be "
            f"{expected[0]}.{expected[1]}.x; "
            f"found {sys.version_info.major}."
            f"{sys.version_info.minor}."
            f"{sys.version_info.micro}"
        )

    return None


def _check_manifest_pins(
    path: Path,
    required: tuple[str, ...],
) -> list[str]:
    if not path.is_file():
        return [
            f"missing manifest: {path.name}"
        ]

    declared = set(
        _read_noncomment_lines(
            path
        )
    )

    return [
        (
            f"{path.name} missing exact pin: "
            f"{pin}"
        )
        for pin in required
        if pin not in declared
    ]


def _check_main_imports() -> list[str]:
    errors = []

    for module in MAIN_IMPORTS:
        try:
            spec = (
                importlib.util.find_spec(
                    module
                )
            )
        except (
            ImportError,
            ModuleNotFoundError,
            AttributeError,
        ):
            spec = None

        if spec is None:
            errors.append(
                f"main import unavailable: {module}"
            )

    return errors


def _check_voice_environment() -> list[str]:
    if not VOICE_PYTHON.is_file():
        return [
            (
                "voice Python missing: "
                f"{VOICE_PYTHON}"
            )
        ]

    code = (
        "import importlib.util,sys\n"
        f"mods={VOICE_IMPORTS!r}\n"
        "missing=[]\n"
        "for m in mods:\n"
        "    try:\n"
        "        s=importlib.util.find_spec(m)\n"
        "    except Exception:\n"
        "        s=None\n"
        "    if s is None:\n"
        "        missing.append(m)\n"
        "print('.'.join(map(str,sys.version_info[:3])))\n"
        "print('\\n'.join(missing))\n"
        "raise SystemExit(1 if missing else 0)\n"
    )

    completed = subprocess.run(
        [
            str(
                VOICE_PYTHON
            ),
            "-B",
            "-c",
            code,
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    lines = (
        completed.stdout
        .splitlines()
    )

    if not lines:
        return [
            "voice Python readiness probe produced no version."
        ]

    version = lines[0].strip()
    pieces = version.split(".")

    if len(pieces) < 2:
        return [
            f"invalid voice Python version: {version!r}"
        ]

    series = (
        int(
            pieces[0]
        ),
        int(
            pieces[1]
        ),
    )

    errors = []

    if series != VOICE_PYTHON_SERIES:
        errors.append(
            (
                "voice Python must be "
                f"{VOICE_PYTHON_SERIES[0]}."
                f"{VOICE_PYTHON_SERIES[1]}.x; "
                f"found {version}"
            )
        )

    if completed.returncode != 0:
        missing = tuple(
            line.strip()
            for line in lines[1:]
            if line.strip()
        )

        for module in missing:
            errors.append(
                f"voice import unavailable: {module}"
            )

        if not missing:
            errors.append(
                (
                    "voice environment readiness probe failed: "
                    + (
                        completed.stderr.strip()
                        or "unknown error"
                    )
                )
            )

    return errors


def _pip_check(
    python: Path,
    label: str,
) -> list[str]:
    completed = subprocess.run(
        [
            str(
                python
            ),
            "-B",
            "-m",
            "pip",
            "check",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    if completed.returncode == 0:
        return []

    detail = (
        completed.stdout.strip()
        or completed.stderr.strip()
        or "unknown pip check failure"
    )

    return [
        f"{label} pip check failed: {detail}"
    ]


def _check_binaries() -> tuple[
    list[str],
    list[str],
]:
    errors = []
    optional = []

    for binary in REQUIRED_MACOS_BINARIES:
        path = Path(
            binary
        )

        if not (
            path.is_file()
            and path.stat().st_mode
        ):
            errors.append(
                f"required macOS binary missing: {binary}"
            )

    for binary in REQUIRED_PATH_BINARIES:
        resolved = shutil.which(
            binary
        )

        if resolved is None:
            errors.append(
                f"required PATH binary missing: {binary}"
            )

    for binary in OPTIONAL_BINARIES:
        resolved = shutil.which(
            binary
        )

        if resolved is None:
            optional.append(
                f"optional binary unavailable: {binary}"
            )

    return (
        errors,
        optional,
    )


def validate() -> tuple[
    tuple[str, ...],
    tuple[str, ...],
]:
    errors = []
    notes = []

    python_error = (
        _check_python_series(
            MAIN_PYTHON_SERIES
        )
    )

    if python_error:
        errors.append(
            python_error
        )

    errors.extend(
        _check_manifest_pins(
            MAIN_REQUIREMENTS,
            MAIN_REQUIRED_PINS,
        )
    )

    errors.extend(
        _check_manifest_pins(
            VOICE_REQUIREMENTS,
            VOICE_REQUIRED_PINS,
        )
    )

    if not VERSION_CONTRACT.is_file():
        errors.append(
            "missing bootstrap-versions.env"
        )

    if not DEV_REQUIREMENTS.is_file():
        errors.append(
            "missing requirements-dev.txt"
        )

    errors.extend(
        _check_main_imports()
    )

    errors.extend(
        _check_voice_environment()
    )

    errors.extend(
        _pip_check(
            Path(
                sys.executable
            ),
            "main",
        )
    )

    if VOICE_PYTHON.is_file():
        errors.extend(
            _pip_check(
                VOICE_PYTHON,
                "voice",
            )
        )

    binary_errors, optional = (
        _check_binaries()
    )

    errors.extend(
        binary_errors
    )

    notes.extend(
        optional
    )

    return (
        tuple(
            errors
        ),
        tuple(
            notes
        ),
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validate KUMA's Bootstrap-A "
            "environment contract without "
            "starting KUMA or installing packages."
        ),
    )

    parser.add_argument(
        "--show-launch",
        action="store_true",
        help=(
            "Print canonical GUI and CLI "
            "entrypoints."
        ),
    )

    args = parser.parse_args()

    errors, notes = validate()

    print(
        "KUMA BOOTSTRAP-A → "
        "read-only readiness check"
    )

    print(
        "main Python series → "
        f"{MAIN_PYTHON_SERIES[0]}."
        f"{MAIN_PYTHON_SERIES[1]}.x"
    )

    print(
        "voice Python series → "
        f"{VOICE_PYTHON_SERIES[0]}."
        f"{VOICE_PYTHON_SERIES[1]}.x"
    )

    if args.show_launch:
        print(
            "canonical GUI → "
            + CANONICAL_GUI
        )
        print(
            "canonical CLI → "
            + CANONICAL_CLI
        )

    for note in notes:
        print(
            "OPTIONAL → "
            + note
        )

    if errors:
        for error in errors:
            print(
                "ERROR → "
                + error,
                file=sys.stderr,
            )

        print(
            "KUMA BOOTSTRAP-A → NOT READY",
            file=sys.stderr,
        )

        return 1

    print(
        "KUMA BOOTSTRAP-A → READY"
    )

    print(
        "AUTHORITY → NONE"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
