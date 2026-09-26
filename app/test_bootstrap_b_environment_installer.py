from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import sys


ROOT = (
    Path(__file__)
    .resolve()
    .parents[1]
)

INSTALLER = (
    ROOT
    / "scripts"
    / "kuma_bootstrap_install.sh"
)

VERSION_CONTRACT = (
    ROOT
    / "bootstrap-versions.env"
)

MAIN_REQUIREMENTS = (
    ROOT
    / "requirements-dev.txt"
)

VOICE_REQUIREMENTS = (
    ROOT
    / "requirements-voice.txt"
)

READINESS_CHECKER = (
    ROOT
    / "scripts"
    / "kuma_bootstrap_check.py"
)

VOICE_PYTHON = (
    ROOT
    / ".voice-venv"
    / "bin"
    / "python"
)


def _run(
    *args,
    cwd=ROOT,
):
    return subprocess.run(
        [
            "/bin/bash",
            str(
                INSTALLER
                if cwd == ROOT
                else cwd
                / "scripts"
                / "kuma_bootstrap_install.sh"
            ),
            *map(
                str,
                args,
            ),
        ],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )


def _base_executable(
    python,
):
    completed = subprocess.run(
        [
            str(
                python
            ),
            "-B",
            "-c",
            (
                "import sys;"
                "print("
                "getattr(sys,'_base_executable',None)"
                " or sys.executable"
                ")"
            ),
        ],
        text=True,
        capture_output=True,
        check=True,
    )

    return Path(
        completed.stdout.strip()
    )


def _minimal_root(
    tmp_path,
):
    root = (
        tmp_path
        / "KumaAI"
    )

    scripts = (
        root
        / "scripts"
    )

    scripts.mkdir(
        parents=True
    )

    shutil.copy2(
        INSTALLER,
        scripts
        / INSTALLER.name,
    )

    shutil.copy2(
        VERSION_CONTRACT,
        root
        / VERSION_CONTRACT.name,
    )

    shutil.copy2(
        MAIN_REQUIREMENTS,
        root
        / MAIN_REQUIREMENTS.name,
    )

    shutil.copy2(
        VOICE_REQUIREMENTS,
        root
        / VOICE_REQUIREMENTS.name,
    )

    # The installer only needs the readiness checker after a real install/check.
    # Plan-mode tests intentionally never execute it.
    shutil.copy2(
        READINESS_CHECKER,
        scripts
        / READINESS_CHECKER.name,
    )

    return root


def test_bootstrap_b_installer_exists_and_has_valid_bash_syntax():
    assert (
        INSTALLER.is_file()
    )

    completed = subprocess.run(
        [
            "/bin/bash",
            "-n",
            str(
                INSTALLER
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
    ), completed.stderr


def test_bootstrap_b_authority_boundary_is_explicit():
    source = (
        INSTALLER.read_text()
    )

    for marker in (
        "BOOTSTRAP INSTALL != KUMA START",
        "DEPENDENCY INSTALL != TOOL EXECUTION PERMISSION",
        "VOICE ENVIRONMENT READY != MICROPHONE CONSENT",
        "ENVIRONMENT CREATION != RUNTIME AUTHORITY",
        "AUTHORITY:NONE",
    ):
        assert marker in source


def test_bootstrap_b_never_contains_destructive_or_runtime_start_commands():
    source = (
        INSTALLER.read_text()
    )

    for forbidden in (
        "rm -rf",
        "brew install",
        "ollama serve",
        "ollama run",
        "ollama pull",
        "python -m app.main",
        "python -m app.agent.kuma_runtime",
        "start_microphone",
        "start_capture",
        "/usr/bin/say",
        "/usr/bin/afplay",
    ):
        assert (
            forbidden
            not in source
        )


def test_bootstrap_b_uses_only_frozen_environment_manifests():
    source = (
        INSTALLER.read_text()
    )

    assert (
        'MAIN_REQUIREMENTS="$ROOT/requirements-dev.txt"'
        in source
    )

    assert (
        'VOICE_REQUIREMENTS="$ROOT/requirements-voice.txt"'
        in source
    )

    assert (
        'VERSION_CONTRACT="$ROOT/bootstrap-versions.env"'
        in source
    )

    assert (
        'READINESS_CHECKER="$ROOT/scripts/kuma_bootstrap_check.py"'
        in source
    )


def test_bootstrap_b_help_is_non_mutating():
    completed = _run(
        "--help"
    )

    assert (
        completed.returncode
        == 0
    )

    assert (
        "The installer never launches KUMA."
        in completed.stdout
    )


def test_bootstrap_b_unknown_argument_fails_with_usage_exit_2():
    completed = _run(
        "--not-a-bootstrap-option"
    )

    assert (
        completed.returncode
        == 2
    )

    assert (
        "Unknown argument"
        in completed.stderr
    )


def test_bootstrap_b_current_environment_check_only_is_green():
    completed = _run(
        "--check-only"
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
        "mode → check"
        in completed.stdout
    )

    assert (
        "KUMA BOOTSTRAP-A → READY"
        in completed.stdout
    )

    assert (
        "KUMA BOOTSTRAP-B → READY"
        in completed.stdout
    )

    assert (
        "KUMA launch → NOT PERFORMED"
        in completed.stdout
    )

    assert (
        "AUTHORITY → NONE"
        in completed.stdout
    )


def test_bootstrap_b_current_environment_plan_is_idempotent():
    first = _run(
        "--plan"
    )

    second = _run(
        "--plan"
    )

    assert (
        first.returncode
        == 0
    ), first.stderr

    assert (
        second.returncode
        == 0
    ), second.stderr

    assert (
        first.stdout
        == second.stdout
    )

    assert (
        "PLAN → reuse .venv"
        in first.stdout
    )

    assert (
        "PLAN → reuse .voice-venv"
        in first.stdout
    )

    assert (
        "PLAN → stop; KUMA is not launched"
        in first.stdout
    )


def test_bootstrap_b_fresh_plan_locates_explicit_base_interpreters(
    tmp_path,
):
    root = (
        _minimal_root(
            tmp_path
        )
    )

    main_base = (
        _base_executable(
            sys.executable
        )
    )

    voice_base = (
        _base_executable(
            VOICE_PYTHON
        )
    )

    installer = (
        root
        / "scripts"
        / "kuma_bootstrap_install.sh"
    )

    completed = subprocess.run(
        [
            "/bin/bash",
            str(
                installer
            ),
            "--plan",
            "--main-python",
            str(
                main_base
            ),
            "--voice-python",
            str(
                voice_base
            ),
        ],
        cwd=root,
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
        "PLAN → create .venv"
        in completed.stdout
    )

    assert (
        "PLAN → create .voice-venv"
        in completed.stdout
    )

    assert not (
        root
        / ".venv"
    ).exists()

    assert not (
        root
        / ".voice-venv"
    ).exists()


def test_bootstrap_b_incompatible_existing_main_environment_fails_closed(
    tmp_path,
):
    root = (
        _minimal_root(
            tmp_path
        )
    )

    voice_base = (
        _base_executable(
            VOICE_PYTHON
        )
    )

    bad_main = (
        root
        / ".venv"
    )

    subprocess.run(
        [
            str(
                voice_base
            ),
            "-m",
            "venv",
            str(
                bad_main
            ),
        ],
        check=True,
        text=True,
        capture_output=True,
    )

    installer = (
        root
        / "scripts"
        / "kuma_bootstrap_install.sh"
    )

    completed = subprocess.run(
        [
            "/bin/bash",
            str(
                installer
            ),
            "--plan",
            "--voice-python",
            str(
                voice_base
            ),
        ],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )

    assert (
        completed.returncode
        != 0
    )

    combined = (
        completed.stdout
        + "\n"
        + completed.stderr
    )

    assert (
        "main environment must use Python 3.14.x"
        in combined
    )

    assert (
        "will not delete or replace it automatically"
        in combined
    )

    assert (
        bad_main.is_dir()
    )


def test_bootstrap_b_check_only_does_not_contain_install_output():
    completed = _run(
        "--check-only"
    )

    assert (
        completed.returncode
        == 0
    )

    assert (
        "dependencies → INSTALL"
        not in completed.stdout
    )


def test_bootstrap_b_plan_does_not_execute_readiness_checker():
    completed = _run(
        "--plan"
    )

    assert (
        completed.returncode
        == 0
    )

    assert (
        "KUMA BOOTSTRAP-A → READY"
        not in completed.stdout
    )

    assert (
        "PLAN → run frozen Bootstrap-A readiness checker"
        in completed.stdout
    )


def test_bootstrap_b_fail_helper_emits_real_newline():
    lines = INSTALLER.read_text().splitlines()

    assert r"    printf '\\n' >&2" not in lines
    assert r"    printf '\n' >&2" in lines
