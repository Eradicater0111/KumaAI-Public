#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import zipfile
from collections import Counter
from datetime import datetime
from pathlib import Path


# ============================================================
# KUMA SAFE REVIEW PACKAGER
# ============================================================
#
# Creates a review ZIP of the local KumaAI repository while:
# - excluding virtualenvs, caches, build artifacts, logs, DBs
# - excluding obvious credential/private-key files
# - never following symlinks
# - redacting likely literal secrets from text files in the ZIP
# - keeping source/config/docs/tests/assets needed for review
# - verifying the generated archive before reporting success
#
# IMPORTANT:
# This script NEVER modifies the KumaAI repository.
# ============================================================


MAX_BINARY_FILE_BYTES = 25 * 1024 * 1024
MAX_TEXT_SCAN_BYTES = 8 * 1024 * 1024

REDACTION = "<REDACTED_BY_KUMA_SAFE_REVIEW_PACKAGER>"


EXCLUDED_DIR_NAMES = {
    ".git",
    ".venv",
    ".voice-venv",
    "venv",
    "env",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    ".nox",
    ".cache",
    ".idea",
    ".vscode",
    "node_modules",
    "dist",
    "build",
    ".build",
    "coverage",
    "htmlcov",
    ".next",
    ".parcel-cache",
    ".gradle",
    ".terraform",
    "DerivedData",
}

EXCLUDED_SUFFIXES = {
    ".pyc",
    ".pyo",
    ".log",
    ".sqlite",
    ".sqlite3",
    ".db",
    ".pem",
    ".key",
    ".p12",
    ".pfx",
    ".jks",
    ".keystore",
    ".mobileprovision",
    ".dmg",
    ".iso",
    ".whl",
    ".tar",
    ".gz",
    ".7z",
}

MODEL_OR_CACHE_SUFFIXES = {
    ".gguf",
    ".ggml",
    ".safetensors",
    ".ckpt",
    ".pt",
    ".pth",
    ".onnx",
    ".bin",
}

ALLOWED_ENV_TEMPLATE_NAMES = {
    ".env.example",
    ".env.sample",
    ".env.template",
}

EXACT_SENSITIVE_NAMES = {
    ".DS_Store",
    ".npmrc",
    ".pypirc",
    "credentials.json",
    "credential.json",
    "tokens.json",
    "token.json",
    "cookies.json",
    "cookie.json",
    "session.json",
    "sessions.json",
    "client_secret.json",
    "client-secrets.json",
    "service_account.json",
    "service-account.json",
    "firebase-adminsdk.json",
    "id_rsa",
    "id_ed25519",
    "known_hosts",
}

RUNTIME_DB_NAME = re.compile(
    r"(?i)\.(?:db|sqlite|sqlite3)(?:[^a-z0-9].*)?$"
)

SQLITE_MAGIC = b"SQLite format 3\x00"

PRIVATE_KEY_BLOCK = re.compile(
    r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----\r?\n"
    r"(?:[A-Za-z0-9+/=]{16,}\r?\n)+"
    r"-----END (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----"
)

PERSONAL_RUNTIME_NAMES = {
    "memory.db",
    "memories.db",
    "memory.sqlite",
    "memories.sqlite",
    "history.db",
    "history.sqlite",
    "conversation.db",
    "conversations.db",
    "conversation_history.json",
    "chat_history.json",
    "user_profile.json",
    "user_data.json",
}

TEXT_SUFFIXES = {
    "",
    ".py",
    ".pyi",
    ".qml",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".json",
    ".jsonc",
    ".toml",
    ".yaml",
    ".yml",
    ".md",
    ".rst",
    ".txt",
    ".sh",
    ".zsh",
    ".bash",
    ".fish",
    ".plist",
    ".xml",
    ".html",
    ".htm",
    ".css",
    ".scss",
    ".ini",
    ".cfg",
    ".conf",
    ".properties",
    ".gradle",
    ".kt",
    ".kts",
    ".java",
    ".swift",
    ".m",
    ".mm",
    ".h",
    ".hpp",
    ".c",
    ".cc",
    ".cpp",
    ".rs",
    ".go",
    ".sql",
    ".graphql",
    ".gql",
    ".csv",
    ".tsv",
    ".svg",
}

SPECIAL_TEXT_NAMES = {
    "Dockerfile",
    "Makefile",
    "Procfile",
    "Gemfile",
    "Rakefile",
    "requirements.txt",
    "requirements-dev.txt",
    "pyproject.toml",
    "poetry.lock",
    "Pipfile",
    "Pipfile.lock",
    "package.json",
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    ".gitignore",
    ".gitattributes",
    ".dockerignore",
}


# Known high-confidence secret formats.
SECRET_PATTERNS = [
    (
        "private-key",
        re.compile(
            r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----"
        ),
    ),
    (
        "aws-access-key",
        re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    ),
    (
        "github-token",
        re.compile(
            r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}\b"
        ),
    ),
    (
        "github-fine-grained-token",
        re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    ),
    (
        "google-api-key",
        re.compile(r"\bAIza[0-9A-Za-z_-]{25,}\b"),
    ),
    (
        "slack-token",
        re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    ),
    (
        "openai-style-key",
        re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    ),
    (
        "tavily-key",
        re.compile(r"\btvly-[A-Za-z0-9_-]{16,}\b"),
    ),
    (
        "bearer-token",
        re.compile(
            r"(?i)(Authorization\s*[:=]\s*['\"]?Bearer\s+)"
            r"([A-Za-z0-9._~+/=-]{16,})"
        ),
    ),
    (
        "jwt",
        re.compile(
            r"\beyJ[A-Za-z0-9_-]{8,}\."
            r"[A-Za-z0-9_-]{8,}\."
            r"[A-Za-z0-9_-]{8,}\b"
        ),
    ),
]

# Literal assignments such as:
# API_KEY = "actual-secret-value"
# password: "actual-password"
SENSITIVE_LITERAL_ASSIGNMENT = re.compile(
    r"""(?ix)
    \b(
        api[_-]?key
        | access[_-]?token
        | auth[_-]?token
        | refresh[_-]?token
        | client[_-]?secret
        | secret[_-]?key
        | password
        | passwd
        | database[_-]?url
        | private[_-]?key
    )
    (\s*[:=]\s*)
    (["'])
    ([^"'\r\n]{8,})
    \3
    """
)

SENSITIVE_UNQUOTED_ASSIGNMENT = re.compile(
    r"""(?ix)
    \b(
        api[_-]?key
        | access[_-]?token
        | auth[_-]?token
        | refresh[_-]?token
        | client[_-]?secret
        | secret[_-]?key
        | password
        | passwd
    )
    (\s*[:=]\s*)
    ([A-Za-z0-9._~+/=-]{16,})
    """
)

PLACEHOLDER_MARKERS = (
    "example",
    "sample",
    "dummy",
    "fake",
    "test",
    "testing",
    "placeholder",
    "changeme",
    "change-me",
    "your_",
    "your-",
    "insert_",
    "insert-",
    "replace_",
    "replace-",
    "<",
    "${",
    "{{",
    "none",
    "null",
)


def run_git(repo: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
            timeout=10,
        )
    except Exception:
        return ""

    if result.returncode != 0:
        return ""

    return result.stdout.strip()


def looks_placeholder(value: str) -> bool:
    lowered = value.strip().lower()

    if not lowered:
        return True

    return any(
        marker in lowered
        for marker in PLACEHOLDER_MARKERS
    )


def redact_text(text: str) -> tuple[str, Counter]:
    counts: Counter = Counter()
    result = text

    # Private-key blocks are not useful in a review archive.
    result, n = PRIVATE_KEY_BLOCK.subn(
        REDACTION,
        result,
    )
    if n:
        counts["private-key-block"] += n

    for label, pattern in SECRET_PATTERNS:
        if label == "private-key":
            continue

        if label == "bearer-token":
            def bearer_replace(match):
                counts[label] += 1
                return match.group(1) + REDACTION

            result = pattern.sub(
                bearer_replace,
                result,
            )
            continue

        def replace_secret(match, secret_label=label):
            counts[secret_label] += 1
            return REDACTION

        result = pattern.sub(
            replace_secret,
            result,
        )

    def quoted_assignment_replace(match):
        value = match.group(4)

        if looks_placeholder(value):
            return match.group(0)

        counts["literal-secret-assignment"] += 1

        return (
            match.group(1)
            + match.group(2)
            + match.group(3)
            + REDACTION
            + match.group(3)
        )

    result = SENSITIVE_LITERAL_ASSIGNMENT.sub(
        quoted_assignment_replace,
        result,
    )

    def unquoted_assignment_replace(match):
        value = match.group(3)

        if looks_placeholder(value):
            return match.group(0)

        counts["literal-secret-assignment"] += 1

        return (
            match.group(1)
            + match.group(2)
            + REDACTION
        )

    result = SENSITIVE_UNQUOTED_ASSIGNMENT.sub(
        unquoted_assignment_replace,
        result,
    )

    return result, counts


def is_text_candidate(path: Path, size: int) -> bool:
    if size > MAX_TEXT_SCAN_BYTES:
        return False

    if path.name in SPECIAL_TEXT_NAMES:
        return True

    return path.suffix.lower() in TEXT_SUFFIXES


def _sensitive_magic(path: Path) -> str | None:
    try:
        with path.open("rb") as handle:
            head = handle.read(128)
    except OSError:
        return "unreadable"

    if head.startswith(SQLITE_MAGIC):
        return "sqlite-magic"

    if b"-----BEGIN " in head and b"PRIVATE KEY-----" in head:
        return "private-key-magic"

    return None


def exclude_reason(
    repo: Path,
    path: Path,
) -> str | None:

    rel = path.relative_to(repo)

    if path.is_symlink():
        return "symlink"

    if any(
        part in EXCLUDED_DIR_NAMES
        for part in rel.parts[:-1]
    ):
        return "generated-or-environment-directory"

    name_lower = path.name.lower()

    if RUNTIME_DB_NAME.search(name_lower):
        return "runtime-database-name"

    magic_reason = _sensitive_magic(path)
    if magic_reason:
        return magic_reason

    if (
        name_lower.startswith(".env")
        and name_lower not in ALLOWED_ENV_TEMPLATE_NAMES
    ):
        return "environment-secret-file"

    if name_lower in EXACT_SENSITIVE_NAMES:
        return "credential-or-session-file"

    if name_lower in PERSONAL_RUNTIME_NAMES:
        return "personal-runtime-data"

    suffix = path.suffix.lower()

    if suffix in EXCLUDED_SUFFIXES:
        return "runtime-or-sensitive-file-type"

    if suffix in MODEL_OR_CACHE_SUFFIXES:
        return "model-or-binary-cache"

    try:
        size = path.stat().st_size
    except OSError:
        return "unreadable"

    if size > MAX_BINARY_FILE_BYTES:
        return "large-binary-or-generated-file"

    return None


def iter_files(repo: Path):
    for root, dirs, files in os.walk(
        repo,
        topdown=True,
        followlinks=False,
    ):
        root_path = Path(root)

        dirs[:] = [
            d
            for d in dirs
            if d not in EXCLUDED_DIR_NAMES
            and not (root_path / d).is_symlink()
        ]

        for name in files:
            path = root_path / name
            yield path


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_metadata(repo: Path) -> dict:
    branch = run_git(
        repo,
        "rev-parse",
        "--abbrev-ref",
        "HEAD",
    )

    commit = run_git(
        repo,
        "rev-parse",
        "HEAD",
    )

    dirty = bool(
        run_git(
            repo,
            "status",
            "--porcelain",
        )
    )

    return {
        "repository_name": repo.name,
        "created_at_local": datetime.now().astimezone().isoformat(),
        "git_branch": branch or None,
        "git_commit": commit or None,
        "working_tree_has_changes": dirty,
        "packager_policy": {
            "virtualenvs_included": False,
            "git_database_included": False,
            "logs_included": False,
            "runtime_databases_included": False,
            "private_keys_included": False,
            "credential_files_included": False,
            "likely_literal_secrets": "redacted from archive copy",
            "symlinks_followed": False,
        },
    }


def verify_archive(zip_path: Path) -> None:
    high_confidence_patterns = [
        (label, pattern)
        for label, pattern in SECRET_PATTERNS
        if label not in {
            "private-key",
        }
    ]

    with zipfile.ZipFile(zip_path, "r") as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue

            if info.file_size > MAX_TEXT_SCAN_BYTES:
                continue

            suffix = Path(info.filename).suffix.lower()
            name = Path(info.filename).name

            if (
                suffix not in TEXT_SUFFIXES
                and name not in SPECIAL_TEXT_NAMES
                and not info.filename.startswith(
                    "_KUMA_SAFE_REVIEW/"
                )
            ):
                continue

            raw = archive.read(info.filename)

            if RUNTIME_DB_NAME.search(Path(info.filename).name.lower()):
                zip_path.unlink(missing_ok=True)
                raise RuntimeError(
                    "archive verification found a runtime database-like filename"
                )

            if raw.startswith(SQLITE_MAGIC):
                zip_path.unlink(missing_ok=True)
                raise RuntimeError(
                    "archive verification found SQLite database content"
                )

            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                continue

            if PRIVATE_KEY_BLOCK.search(text):
                zip_path.unlink(missing_ok=True)
                raise RuntimeError(
                    "archive verification found a private key block"
                )

            for label, pattern in high_confidence_patterns:
                if pattern.search(text):
                    zip_path.unlink(missing_ok=True)
                    raise RuntimeError(
                        "archive verification found an unredacted "
                        f"high-confidence secret pattern: {label}"
                    )


def build_archive(repo: Path, output: Path) -> None:
    included = 0
    included_bytes = 0
    redacted_files = 0
    redaction_counts: Counter = Counter()
    excluded_counts: Counter = Counter()
    errors: Counter = Counter()

    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    if output.exists():
        output.unlink()

    root_name = repo.name

    with zipfile.ZipFile(
        output,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=6,
    ) as archive:

        for path in iter_files(repo):
            # Never accidentally package a ZIP produced inside repo.
            try:
                if path.resolve() == output.resolve():
                    continue
            except OSError:
                pass

            reason = exclude_reason(
                repo,
                path,
            )

            if reason:
                excluded_counts[reason] += 1
                continue

            rel = path.relative_to(repo)
            arcname = str(
                Path(root_name)
                / rel
            )

            try:
                size = path.stat().st_size
            except OSError:
                errors["stat-failed"] += 1
                continue

            if is_text_candidate(path, size):
                try:
                    raw = path.read_bytes()
                except OSError:
                    errors["read-failed"] += 1
                    continue

                try:
                    text = raw.decode("utf-8")
                except UnicodeDecodeError:
                    # Treat as binary if text decoding is not safe.
                    archive.write(
                        path,
                        arcname,
                    )
                    included += 1
                    included_bytes += size
                    continue

                redacted, counts = redact_text(
                    text
                )

                if counts:
                    redacted_files += 1
                    redaction_counts.update(
                        counts
                    )

                data = redacted.encode(
                    "utf-8"
                )

                archive.writestr(
                    arcname,
                    data,
                )

                included += 1
                included_bytes += len(data)

            else:
                try:
                    archive.write(
                        path,
                        arcname,
                    )
                except OSError:
                    errors["read-failed"] += 1
                    continue

                included += 1
                included_bytes += size

        metadata = safe_metadata(
            repo
        )

        metadata["archive_summary"] = {
            "included_files": included,
            "included_uncompressed_bytes": included_bytes,
            "redacted_files": redacted_files,
            "redactions_by_type": dict(
                sorted(
                    redaction_counts.items()
                )
            ),
            "excluded_files_by_reason": dict(
                sorted(
                    excluded_counts.items()
                )
            ),
            "packaging_errors_by_type": dict(
                sorted(
                    errors.items()
                )
            ),
        }

        readme = f"""KUMA SAFE REVIEW ARCHIVE
========================

Purpose:
This archive is intended for full architectural/code review of KumaAI
without intentionally including local secrets, credentials, runtime
databases, virtual environments, logs, model weights, or Git internals.

Repository:
{repo}

Included files:
{included}

Files containing redacted secret-like literals:
{redacted_files}

Important:
- The original repository was NOT modified.
- Secret redaction applies only to copies written into this ZIP.
- Private keys and obvious credential/session files are excluded entirely.
- Runtime SQLite/DB files are excluded.
- .env files are excluded except .env.example/.sample/.template.
- Symlinks are not followed.
- Large model/cache binaries are excluded.
- No automated scanner can guarantee detection of every possible secret.
  The generated ZIP is additionally scanned for several high-confidence
  token/key formats before success is reported.

Review metadata is stored in:
_KUMA_SAFE_REVIEW/metadata.json
"""

        archive.writestr(
            "_KUMA_SAFE_REVIEW/README.txt",
            readme,
        )

        archive.writestr(
            "_KUMA_SAFE_REVIEW/metadata.json",
            json.dumps(
                metadata,
                indent=2,
                sort_keys=True,
            )
            + "\n",
        )

    verify_archive(
        output
    )

    final_size = output.stat().st_size

    print()
    print(
        "===== KUMA SAFE REVIEW ARCHIVE ====="
    )
    print(
        f"Repository: {repo}"
    )
    print(
        f"Included files: {included}"
    )
    print(
        f"Redacted files: {redacted_files}"
    )
    print(
        f"Excluded files: {sum(excluded_counts.values())}"
    )
    print(
        f"Archive size: {final_size / (1024 * 1024):.2f} MiB"
    )
    print(
        f"Output: {output}"
    )
    print()
    print(
        "PASS — archive created."
    )
    print(
        "PASS — original repository was not modified."
    )
    print(
        "PASS — obvious credential/private-key/runtime files excluded."
    )
    print(
        "PASS — likely literal secrets redacted in archive copies."
    )
    print(
        "PASS — post-build high-confidence secret verification passed."
    )
    print()
    print(
        "Upload this ZIP to ChatGPT and ask for the full KUMA review."
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Create a secret-scrubbed KumaAI ZIP for code review."
        )
    )

    parser.add_argument(
        "repo",
        nargs="?",
        default=".",
        help=(
            "KumaAI repository path. "
            "Defaults to the current directory."
        ),
    )

    parser.add_argument(
        "--output",
        default=None,
        help=(
            "Destination ZIP path. "
            "Defaults to ~/Desktop/KumaAI_SAFE_REVIEW_<timestamp>.zip"
        ),
    )

    args = parser.parse_args()

    repo = Path(
        args.repo
    ).expanduser().resolve()

    if not repo.is_dir():
        raise SystemExit(
            f"ERROR — repository directory not found: {repo}"
        )

    expected = (
        repo
        / "app"
        / "agent"
        / "kuma_agent.py"
    )

    if not expected.is_file():
        raise SystemExit(
            "ERROR — this does not look like the KumaAI repository root. "
            "Expected app/agent/kuma_agent.py"
        )

    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    if args.output:
        output = Path(
            args.output
        ).expanduser().resolve()
    else:
        desktop = (
            Path.home()
            / "Desktop"
        )

        destination_dir = (
            desktop
            if desktop.is_dir()
            else repo.parent
        )

        output = (
            destination_dir
            / f"KumaAI_SAFE_REVIEW_{timestamp}.zip"
        )

    try:
        build_archive(
            repo,
            output,
        )
    except Exception as error:
        if output.exists():
            output.unlink(
                missing_ok=True
            )

        raise SystemExit(
            f"ERROR — safe review archive was not produced: {error}"
        ) from error


if __name__ == "__main__":
    main()
