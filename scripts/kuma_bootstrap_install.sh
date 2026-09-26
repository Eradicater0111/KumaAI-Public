#!/usr/bin/env bash

set -euo pipefail

# ============================================================
# KUMA BOOTSTRAP-B — ENVIRONMENT CREATION / INSTALL OWNER
# ============================================================
#
# Explicit invocation only.
#
# BOOTSTRAP INSTALL != KUMA START
# DEPENDENCY INSTALL != TOOL EXECUTION PERMISSION
# VOICE ENVIRONMENT READY != MICROPHONE CONSENT
# ENVIRONMENT CREATION != RUNTIME AUTHORITY
# AUTHORITY:NONE
#
# This script may:
#   - locate already-installed compatible Python interpreters
#   - create .venv / .voice-venv when absent
#   - install dependencies from frozen repository manifests
#   - run pip check
#   - run the frozen Bootstrap-A readiness checker
#
# This script deliberately does NOT:
#   - delete or replace an existing environment
#   - install Homebrew or Python
#   - install optional system binaries
#   - start model services or download models
#   - launch KUMA GUI or CLI
#   - access microphone capture
#   - start speech output
#
# Re-running a successful installation is supported.
# ============================================================

SCRIPT_DIR="$(
    cd "$(
        dirname "${BASH_SOURCE[0]}"
    )" >/dev/null 2>&1
    pwd
)"

ROOT="$(
    cd "$SCRIPT_DIR/.." >/dev/null 2>&1
    pwd
)"

VERSION_CONTRACT="$ROOT/bootstrap-versions.env"
MAIN_VENV="$ROOT/.venv"
VOICE_VENV="$ROOT/.voice-venv"

MAIN_REQUIREMENTS="$ROOT/requirements-dev.txt"
VOICE_REQUIREMENTS="$ROOT/requirements-voice.txt"
READINESS_CHECKER="$ROOT/scripts/kuma_bootstrap_check.py"

MODE="install"
MAIN_OVERRIDE=""
VOICE_OVERRIDE=""

usage() {
    cat <<'EOF'
Usage:
  bash scripts/kuma_bootstrap_install.sh [options]

Options:
  --plan
      Print the environment actions that would be taken.
      Creates nothing and installs nothing.

  --check-only
      Require both environments to already exist, run pip check,
      then run the frozen Bootstrap-A readiness checker.
      Installs nothing.

  --main-python PATH
      Explicit base interpreter to use if .venv must be created.
      Must be a non-virtual Python 3.14.x interpreter.

  --voice-python PATH
      Explicit base interpreter to use if .voice-venv must be created.
      Must be a non-virtual Python 3.12.x interpreter.

  -h, --help
      Show this help.

Default mode:
  Create missing compatible environments, reuse compatible existing
  environments, install the frozen manifests, validate both environments,
  run Bootstrap-A readiness, then stop.

The installer never launches KUMA.
EOF
}


fail() {
    printf '%s' "ERROR — " >&2
    printf '%s' "$@" >&2
    printf '\n' >&2
    exit 1
}


contract_value() {
    key="$1"

    [ -f "$VERSION_CONTRACT" ] || {
        fail "missing version contract: $VERSION_CONTRACT"
    }

    values="$(
        sed -n \
            "s/^${key}=//p" \
            "$VERSION_CONTRACT"
    )"

    count="$(
        printf '%s\n' "$values" \
        | sed '/^$/d' \
        | wc -l \
        | tr -d ' '
    )"

    if [ "$count" != "1" ]; then
        fail "version contract must define $key exactly once"
    fi

    printf '%s\n' "$values"
}


python_probe() {
    python="$1"

    "$python" -B - <<'PY'
import platform
import sys

print(platform.python_version())
print(
    f"{sys.version_info.major}."
    f"{sys.version_info.minor}"
)
print(
    "1"
    if sys.prefix != sys.base_prefix
    else "0"
)
PY
}


validate_existing_environment() {
    label="$1"
    directory="$2"
    expected_series="$3"

    python="$directory/bin/python"

    if [ ! -d "$directory" ]; then
        fail "$label environment path exists but is not a directory: $directory"
    fi

    if [ ! -x "$python" ]; then
        fail \
            "$label environment exists but has no executable Python: $python"
    fi

    probe="$(
        python_probe "$python"
    )" || {
        fail "$label environment Python probe failed: $python"
    }

    version="$(
        printf '%s\n' "$probe" \
        | sed -n '1p'
    )"

    series="$(
        printf '%s\n' "$probe" \
        | sed -n '2p'
    )"

    is_venv="$(
        printf '%s\n' "$probe" \
        | sed -n '3p'
    )"

    if [ "$series" != "$expected_series" ]; then
        fail \
            "$label environment must use Python " \
            "$expected_series.x; found $version at $python. " \
            "Bootstrap-B will not delete or replace it automatically."
    fi

    if [ "$is_venv" != "1" ]; then
        fail "$label environment Python does not report virtual-environment isolation"
    fi

    echo "$label environment → REUSE $directory (Python $version)"
}


candidate_is_inside_managed_environment() {
    candidate="$1"

    case "$candidate" in
        "$MAIN_VENV"/*|"$VOICE_VENV"/*)
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}


validate_base_interpreter() {
    python="$1"
    expected_series="$2"

    [ -x "$python" ] || return 1

    candidate_is_inside_managed_environment "$python" \
        && return 1

    probe="$(
        python_probe "$python" 2>/dev/null
    )" || return 1

    series="$(
        printf '%s\n' "$probe" \
        | sed -n '2p'
    )"

    is_venv="$(
        printf '%s\n' "$probe" \
        | sed -n '3p'
    )"

    [ "$series" = "$expected_series" ] || return 1
    [ "$is_venv" = "0" ] || return 1

    return 0
}


resolve_base_interpreter() {
    label="$1"
    expected_series="$2"
    override="$3"
    shift 3

    if [ -n "$override" ]; then
        if validate_base_interpreter \
            "$override" \
            "$expected_series"
        then
            printf '%s\n' "$override"
            return 0
        fi

        fail \
            "$label interpreter override is not a non-virtual " \
            "Python $expected_series.x interpreter: $override"
    fi

    candidates=()

    while [ "$#" -gt 0 ]; do
        candidates+=("$1")
        shift
    done

    command_candidate="$(
        command -v "python${expected_series}" 2>/dev/null \
        || true
    )"

    if [ -n "$command_candidate" ]; then
        candidates+=("$command_candidate")
    fi

    seen="|"

    for candidate in "${candidates[@]}"; do
        [ -n "$candidate" ] || continue

        case "$seen" in
            *"|$candidate|"*)
                continue
                ;;
        esac

        seen="${seen}${candidate}|"

        if validate_base_interpreter \
            "$candidate" \
            "$expected_series"
        then
            printf '%s\n' "$candidate"
            return 0
        fi
    done

    fail \
        "no compatible non-virtual $label Python " \
        "$expected_series.x interpreter found. " \
        "Install Python manually, or rerun with the explicit interpreter option."
}


show_known_good_note() {
    label="$1"
    python="$2"
    known_good="$3"

    version="$(
        "$python" -B -c \
            'import platform; print(platform.python_version())'
    )"

    if [ "$version" = "$known_good" ]; then
        echo "$label interpreter → $python (known-good $version)"
    else
        echo \
            "$label interpreter → $python (compatible $version; " \
            "known-good baseline is $known_good)"
    fi
}


create_environment() {
    label="$1"
    directory="$2"
    python="$3"

    echo "$label environment → CREATE $directory"

    "$python" -B -m venv "$directory"

    [ -x "$directory/bin/python" ] || {
        fail "$label environment creation did not produce an executable Python"
    }
}


pip_install_manifest() {
    label="$1"
    python="$2"
    manifest="$3"

    [ -f "$manifest" ] || {
        fail "$label manifest missing: $manifest"
    }

    echo "$label dependencies → INSTALL $manifest"

    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    "$python" -B -m pip install \
        --no-input \
        -r "$manifest"
}


pip_check_environment() {
    label="$1"
    python="$2"

    echo "$label dependencies → CHECK"

    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    "$python" -B -m pip check
}


for argument in "$@"; do
    case "$argument" in
        --plan|--check-only|-h|--help)
            ;;
        --main-python|--voice-python)
            ;;
        *)
            ;;
    esac
done


while [ "$#" -gt 0 ]; do
    case "$1" in
        --plan)
            [ "$MODE" = "install" ] || {
                fail "--plan and --check-only are mutually exclusive"
            }
            MODE="plan"
            shift
            ;;

        --check-only)
            [ "$MODE" = "install" ] || {
                fail "--plan and --check-only are mutually exclusive"
            }
            MODE="check"
            shift
            ;;

        --main-python)
            [ "$#" -ge 2 ] || {
                fail "--main-python requires a path"
            }
            MAIN_OVERRIDE="$2"
            shift 2
            ;;

        --voice-python)
            [ "$#" -ge 2 ] || {
                fail "--voice-python requires a path"
            }
            VOICE_OVERRIDE="$2"
            shift 2
            ;;

        -h|--help)
            usage
            exit 0
            ;;

        *)
            echo "Unknown argument: $1" >&2
            usage >&2
            exit 2
            ;;
    esac
done


MAIN_SERIES="$(
    contract_value \
        "KUMA_MAIN_PYTHON_SERIES"
)"

MAIN_KNOWN_GOOD="$(
    contract_value \
        "KUMA_MAIN_PYTHON_KNOWN_GOOD"
)"

VOICE_SERIES="$(
    contract_value \
        "KUMA_VOICE_PYTHON_SERIES"
)"

VOICE_KNOWN_GOOD="$(
    contract_value \
        "KUMA_VOICE_PYTHON_KNOWN_GOOD"
)"


case "$MAIN_SERIES" in
    [0-9]*.[0-9]*)
        ;;
    *)
        fail "invalid main Python series in version contract: $MAIN_SERIES"
        ;;
esac

case "$VOICE_SERIES" in
    [0-9]*.[0-9]*)
        ;;
    *)
        fail "invalid voice Python series in version contract: $VOICE_SERIES"
        ;;
esac


echo "KUMA BOOTSTRAP-B → explicit environment owner"
echo "mode → $MODE"
echo "main Python series → $MAIN_SERIES.x"
echo "voice Python series → $VOICE_SERIES.x"


MAIN_CREATE="0"
VOICE_CREATE="0"
MAIN_BASE=""
VOICE_BASE=""


if [ -e "$MAIN_VENV" ]; then
    validate_existing_environment \
        "main" \
        "$MAIN_VENV" \
        "$MAIN_SERIES"
else
    if [ "$MODE" = "check" ]; then
        fail "main environment missing: $MAIN_VENV"
    fi

    MAIN_BASE="$(
        resolve_base_interpreter \
            "main" \
            "$MAIN_SERIES" \
            "$MAIN_OVERRIDE" \
            "/Library/Frameworks/Python.framework/Versions/${MAIN_SERIES}/bin/python${MAIN_SERIES}" \
            "/usr/local/bin/python${MAIN_SERIES}" \
            "/opt/homebrew/bin/python${MAIN_SERIES}"
    )"

    show_known_good_note \
        "main" \
        "$MAIN_BASE" \
        "$MAIN_KNOWN_GOOD"

    MAIN_CREATE="1"
fi


if [ -e "$VOICE_VENV" ]; then
    validate_existing_environment \
        "voice" \
        "$VOICE_VENV" \
        "$VOICE_SERIES"
else
    if [ "$MODE" = "check" ]; then
        fail "voice environment missing: $VOICE_VENV"
    fi

    VOICE_BASE="$(
        resolve_base_interpreter \
            "voice" \
            "$VOICE_SERIES" \
            "$VOICE_OVERRIDE" \
            "/opt/homebrew/bin/python${VOICE_SERIES}" \
            "/opt/homebrew/opt/python@${VOICE_SERIES}/bin/python${VOICE_SERIES}" \
            "/Library/Frameworks/Python.framework/Versions/${VOICE_SERIES}/bin/python${VOICE_SERIES}" \
            "/usr/local/bin/python${VOICE_SERIES}"
    )"

    show_known_good_note \
        "voice" \
        "$VOICE_BASE" \
        "$VOICE_KNOWN_GOOD"

    VOICE_CREATE="1"
fi


if [ "$MODE" = "plan" ]; then
    if [ "$MAIN_CREATE" = "1" ]; then
        echo "PLAN → create .venv using $MAIN_BASE"
    else
        echo "PLAN → reuse .venv"
    fi

    echo "PLAN → install requirements-dev.txt into .venv"

    if [ "$VOICE_CREATE" = "1" ]; then
        echo "PLAN → create .voice-venv using $VOICE_BASE"
    else
        echo "PLAN → reuse .voice-venv"
    fi

    echo "PLAN → install requirements-voice.txt into .voice-venv"
    echo "PLAN → pip check both environments"
    echo "PLAN → run frozen Bootstrap-A readiness checker"
    echo "PLAN → stop; KUMA is not launched"
    echo "AUTHORITY → NONE"
    exit 0
fi


if [ "$MODE" = "install" ]; then
    if [ "$MAIN_CREATE" = "1" ]; then
        create_environment \
            "main" \
            "$MAIN_VENV" \
            "$MAIN_BASE"
    fi

    validate_existing_environment \
        "main" \
        "$MAIN_VENV" \
        "$MAIN_SERIES"

    pip_install_manifest \
        "main" \
        "$MAIN_VENV/bin/python" \
        "$MAIN_REQUIREMENTS"

    if [ "$VOICE_CREATE" = "1" ]; then
        create_environment \
            "voice" \
            "$VOICE_VENV" \
            "$VOICE_BASE"
    fi

    validate_existing_environment \
        "voice" \
        "$VOICE_VENV" \
        "$VOICE_SERIES"

    pip_install_manifest \
        "voice" \
        "$VOICE_VENV/bin/python" \
        "$VOICE_REQUIREMENTS"
fi


pip_check_environment \
    "main" \
    "$MAIN_VENV/bin/python"

pip_check_environment \
    "voice" \
    "$VOICE_VENV/bin/python"


[ -f "$READINESS_CHECKER" ] || {
    fail "frozen Bootstrap-A readiness checker missing: $READINESS_CHECKER"
}


"$MAIN_VENV/bin/python" -B \
    "$READINESS_CHECKER" \
    --show-launch


echo "KUMA BOOTSTRAP-B → READY"
echo "KUMA launch → NOT PERFORMED"
echo "AUTHORITY → NONE"
