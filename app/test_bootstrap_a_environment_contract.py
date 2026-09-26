from __future__ import annotations

import ast
from pathlib import Path
import subprocess
import sys


ROOT = (
    Path(__file__)
    .resolve()
    .parents[1]
)

CHECKER = (
    ROOT
    / "scripts"
    / "kuma_bootstrap_check.py"
)

MAIN_REQ = (
    ROOT
    / "requirements.txt"
)

VOICE_REQ = (
    ROOT
    / "requirements-voice.txt"
)

DEV_REQ = (
    ROOT
    / "requirements-dev.txt"
)

VERSION_CONTRACT = (
    ROOT
    / "bootstrap-versions.env"
)

GITIGNORE = (
    ROOT
    / ".gitignore"
)


def _checker_source():
    return (
        CHECKER.read_text()
    )


def test_bootstrap_a_checker_exists_and_compiles():
    source = (
        _checker_source()
    )

    ast.parse(
        source,
        filename=str(
            CHECKER
        ),
    )


def test_bootstrap_a_checker_is_standard_library_only():
    tree = ast.parse(
        _checker_source(),
        filename=str(
            CHECKER
        ),
    )

    imports = set()

    for node in ast.walk(
        tree
    ):
        if isinstance(
            node,
            ast.Import,
        ):
            imports.update(
                alias.name.split(
                    ".",
                    1,
                )[0]
                for alias in node.names
            )

        elif (
            isinstance(
                node,
                ast.ImportFrom,
            )
            and node.module
        ):
            imports.add(
                node.module.split(
                    ".",
                    1,
                )[0]
            )

    assert imports <= {
        "__future__",
        "argparse",
        "importlib",
        "pathlib",
        "shutil",
        "subprocess",
        "sys",
    }


def test_bootstrap_a_authority_markers_are_explicit():
    source = (
        _checker_source()
    )

    for marker in (
        "BOOTSTRAP != RUNTIME AUTHORITY",
        "DEPENDENCY CHECK != TOOL PERMISSION",
        "ENVIRONMENT DETECTION != EXECUTION AUTHORIZATION",
        "OPTIONAL CAPABILITY MISSING != CORE STARTUP CORRUPTION",
        "VOICE PROCESS OWNER != AGENT EXECUTION OWNER",
        "AUTHORITY:NONE",
    ):
        assert marker in source


def test_bootstrap_a_checker_has_no_agent_runtime_imports():
    source = (
        _checker_source()
    )

    for forbidden in (
        "from app.",
        "import app.",
        "KumaAgent",
        "KumaRuntimeV2LiveOwner",
        "KumaIntegrationV2LiveTurnOwner",
        "MissionService",
        "MemoryStore",
        "QApplication",
        "QAudioSource",
    ):
        assert forbidden not in source


def test_bootstrap_a_main_runtime_direct_dependencies_declared():
    lines = set(
        MAIN_REQ
        .read_text()
        .splitlines()
    )

    for pin in (
        "PySide6==6.11.1",
        "ollama==0.6.2",
        "google-genai==2.18.1",
        "httpx==0.28.1",
        "python-dotenv==1.2.2",
        "sentence-transformers==5.7.0",
    ):
        assert pin in lines


def test_bootstrap_a_voice_manifest_is_exact_direct_known_good_surface():
    declared = tuple(
        line.strip()
        for line
        in VOICE_REQ
        .read_text()
        .splitlines()
        if (
            line.strip()
            and not line.startswith(
                "#"
            )
        )
    )

    assert declared == (
        "kokoro-mlx==0.1.2",
        "mlx-whisper==0.4.3",
        "mlx==0.32.2",
        "numpy==2.5.3",
        "soundfile==0.14.0",
        "huggingface-hub==2.0.0",
    )

    assert all(
        not line.startswith(
            "scipy"
        )
        for line
        in declared
    )


def test_bootstrap_a_dev_manifest_composes_existing_surfaces():
    text = (
        DEV_REQ.read_text()
    )

    assert (
        "-r requirements.txt"
        in text
    )

    assert (
        "-r requirements-desktop.txt"
        in text
    )

    assert (
        "-r requirements-3d-dev.txt"
        in text
    )

    assert (
        "pytest==9.1.1"
        in text
    )


def test_bootstrap_a_dual_python_contract_is_explicit():
    text = (
        VERSION_CONTRACT
        .read_text()
    )

    assert (
        "KUMA_MAIN_PYTHON_SERIES=3.14"
        in text
    )

    assert (
        "KUMA_MAIN_PYTHON_KNOWN_GOOD=3.14.6"
        in text
    )

    assert (
        "KUMA_VOICE_PYTHON_SERIES=3.12"
        in text
    )

    assert (
        "KUMA_VOICE_PYTHON_KNOWN_GOOD=3.12.14"
        in text
    )

    assert (
        "AUTHORITY:NONE"
        in text
    )


def test_bootstrap_a_voice_venv_is_explicitly_ignored():
    lines = (
        GITIGNORE
        .read_text()
        .splitlines()
    )

    assert (
        ".voice-venv/"
        in lines
    )


def test_bootstrap_a_ffmpeg_is_optional_not_required():
    source = (
        _checker_source()
    )

    assert (
        'OPTIONAL_BINARIES = ('
        in source
    )

    assert (
        '"ffmpeg",'
        in source
    )

    assert (
        '"ffprobe",'
        in source
    )

    required_section = (
        source[
            source.index(
                "REQUIRED_PATH_BINARIES"
            ):
            source.index(
                "OPTIONAL_BINARIES"
            )
        ]
    )

    assert (
        "ffmpeg"
        not in required_section
    )

    assert (
        "ffprobe"
        not in required_section
    )


def test_bootstrap_a_canonical_entrypoints_are_explicit():
    source = (
        _checker_source()
    )

    assert (
        'CANONICAL_GUI = (\n'
        '    "python -m app.main"\n'
        ')'
        in source
    )

    assert (
        'CANONICAL_CLI = (\n'
        '    "python -m app.agent.kuma_runtime"\n'
        ')'
        in source
    )


def test_bootstrap_a_checker_does_not_install_or_start_runtime_services():
    source = (
        _checker_source()
    )

    for forbidden in (
        '"install"',
        "'install'",
        "pip install",
        "brew install",
        "ollama serve",
        "ollama run",
        "start_microphone",
        "start_capture",
        "QProcess",
        "Popen(",
    ):
        assert forbidden not in source


def test_bootstrap_a_live_readiness_check_is_green():
    completed = subprocess.run(
        [
            sys.executable,
            "-B",
            str(
                CHECKER
            ),
            "--show-launch",
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
        + "\n"
        + completed.stderr
    )

    assert (
        "KUMA BOOTSTRAP-A → READY"
        in completed.stdout
    )

    assert (
        "canonical GUI → python -m app.main"
        in completed.stdout
    )

    assert (
        "canonical CLI → python -m app.agent.kuma_runtime"
        in completed.stdout
    )

    assert (
        "AUTHORITY → NONE"
        in completed.stdout
    )



def test_bootstrap_a_stt_provider_is_part_of_voice_readiness_contract():
    source = (
        _checker_source()
    )

    for expected in (
        '"mlx_whisper"',
        '"mlx-whisper==0.4.3"',
        '"huggingface-hub==2.0.0"',
    ):
        assert expected in source

    assert (
        '"huggingface-hub==1.30.0"'
        not in source
    )
