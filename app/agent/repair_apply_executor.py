from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
from typing import Callable

from app.agent.repair_apply_request import (
    RepairApplyRequest,
    RepairApplyRequestBuilder,
)
from app.agent.repair_execution_sandbox import (
    RepairExecutionResult,
)
from app.agent.repair_policy import (
    RepairDecision,
)
from app.agent.repair_result_verifier import (
    RepairResultVerifier,
    RepairVerificationResult,
)
from app.agent.repair_test_executor import (
    RepairTestExecutionResult,
)
from app.agent.repair_test_handoff import (
    RepairTestHandoffResult,
)
from app.agent.repair_test_selector import (
    RepairTestSelectionResult,
)
from app.agent.repair_validator import (
    RepairValidationResult,
)
from app.agent.repair_workspace import (
    RepairWorkspace,
    RepairWorkspaceError,
)


@dataclass(frozen=True)
class RepairApplyResult:
    """
    Result of one explicitly approved transactional repair apply.

    applied=True means verified candidate bytes were installed into
    the source working tree. It does NOT mean committed or pushed.

    rolled_back=True means this executor restored the pre-apply
    snapshots after an application or verification failure.
    """

    attempted: bool
    approved: bool
    applied: bool
    rolled_back: bool
    rollback_failed: bool
    reason: str
    changed_files: tuple[str, ...] = ()
    request_digest: str = ""
    recovered_interrupted_apply: bool = False
    recovery_blocked: bool = False


@dataclass(frozen=True)
class _FileSnapshot:
    relative_path: str
    content: bytes
    mode: int
    digest: str


@dataclass(frozen=True)
class _RollbackJournal:
    """
    Durable evidence for one in-flight approved source repair.

    state:
        prepared -> mutation may be incomplete; safe recovery rolls back
        applied  -> post-apply verification completed; safe recovery
                    preserves the applied repair
    """

    state: str
    source_head: str
    request_digest: str
    changed_files: tuple[str, ...]
    snapshots: tuple[
        _FileSnapshot,
        ...,
    ]
    candidate_digests: tuple[
        tuple[str, str],
        ...,
    ]


class RepairApplyExecutor:
    """
    6C.7 transactional main-checkout repair application.

    Authority is intentionally narrow:
    - explicit human confirmation is mandatory for every repair
    - confirmation is bound to one exact RepairApplyRequest
    - 6C.6 evidence is independently rebuilt before confirmation
    - source HEAD and cleanliness are checked before confirmation
    - all evidence and source state are checked AGAIN after approval
    - only verified changed Python files may be replaced
    - original file bytes and modes are snapshotted first
    - replacement uses same-directory atomic os.replace()
    - post-apply source bytes must exactly match candidate bytes
    - Git may show changes only for the approved repair scope
    - any apply/post-apply failure triggers automatic rollback
    - rollback restores exact original bytes and modes
    - no shell=True
    - no execute_command
    - no git checkout/reset/commit/merge/push
    """

    _CONFIRMATION_ACTION = (
        "apply_verified_repair"
    )

    def __init__(
        self,
        *,
        git_timeout_seconds: int = 30,
        max_file_bytes: int = 1_000_000,
    ):
        for name, value in (
            (
                "git_timeout_seconds",
                git_timeout_seconds,
            ),
            (
                "max_file_bytes",
                max_file_bytes,
            ),
        ):
            if (
                type(value) is not int
                or value < 1
            ):
                raise ValueError(
                    f"{name} must be a positive integer."
                )

        self.git_timeout_seconds = (
            git_timeout_seconds
        )
        self.max_file_bytes = (
            max_file_bytes
        )

    @staticmethod
    def _reject(
        reason: str,
        *,
        attempted: bool = False,
        approved: bool = False,
        changed_files: tuple[str, ...] = (),
        request_digest: str = "",
        recovery_blocked: bool = False,
    ) -> RepairApplyResult:
        return RepairApplyResult(
            attempted=attempted,
            approved=approved,
            applied=False,
            rolled_back=False,
            rollback_failed=False,
            reason=reason,
            changed_files=changed_files,
            request_digest=request_digest,
            recovery_blocked=recovery_blocked,
        )

    def _run_git(
        self,
        root: Path,
        *args: str,
    ) -> subprocess.CompletedProcess:
        try:
            return subprocess.run(
                [
                    "git",
                    "-C",
                    str(root),
                    *args,
                ],
                capture_output=True,
                text=True,
                timeout=self.git_timeout_seconds,
                check=False,
                shell=False,
            )
        except subprocess.TimeoutExpired as error:
            raise RepairWorkspaceError(
                "Git operation timed out during "
                "repair application."
            ) from error
        except OSError as error:
            raise RepairWorkspaceError(
                "Could not execute Git during "
                f"repair application: {error}"
            ) from error

    @staticmethod
    def _git_detail(
        result: subprocess.CompletedProcess,
    ) -> str:
        return (
            (result.stderr or "").strip()
            or (result.stdout or "").strip()
            or "unknown Git error"
        )

    def _require_git(
        self,
        root: Path,
        *args: str,
        operation: str,
    ) -> str:
        result = self._run_git(
            root,
            *args,
        )

        if result.returncode != 0:
            raise RepairWorkspaceError(
                f"{operation} failed: "
                f"{self._git_detail(result)}"
            )

        return (
            result.stdout
            or ""
        ).strip()

    @staticmethod
    def _digest(
        content: bytes,
    ) -> str:
        return hashlib.sha256(
            content
        ).hexdigest()

    @staticmethod
    def _within(
        path: Path,
        root: Path,
    ) -> bool:
        try:
            path.relative_to(
                root
            )
            return True
        except ValueError:
            return False

    @staticmethod
    def _verification_matches(
        expected: RepairVerificationResult,
        current: RepairVerificationResult,
    ) -> bool:
        return (
            expected.evidence_verified is True
            and current.evidence_verified is True
            and (
                expected.eligible_for_apply_review
                is True
            )
            and (
                current.eligible_for_apply_review
                is True
            )
            and (
                expected.source_head
                == current.source_head
            )
            and (
                expected.validation_digest
                == current.validation_digest
            )
            and (
                expected.changed_files
                == current.changed_files
            )
            and (
                expected.executed_files
                == current.executed_files
            )
            and (
                expected.test_files
                == current.test_files
            )
            and (
                expected.tests_run
                == current.tests_run
            )
            and (
                expected.evidence_digest
                == current.evidence_digest
            )
        )

    @staticmethod
    def _request_matches(
        expected: RepairApplyRequest,
        current: RepairApplyRequest,
    ) -> bool:
        return (
            expected
            == current
            and (
                expected
                .requires_explicit_human_approval
                is True
            )
        )

    def _source_preflight(
        self,
        *,
        source_root: Path,
        expected_head: str,
    ) -> None:
        top_level = self._require_git(
            source_root,
            "rev-parse",
            "--show-toplevel",
            operation=(
                "Source repository-root verification"
            ),
        )

        if (
            Path(
                top_level
            ).expanduser().resolve()
            != source_root
        ):
            raise RepairWorkspaceError(
                "Repair source root is not the exact "
                "Git repository root."
            )

        head = self._require_git(
            source_root,
            "rev-parse",
            "--verify",
            "HEAD",
            operation=(
                "Source HEAD verification"
            ),
        )

        if head != expected_head:
            raise RepairWorkspaceError(
                "Source HEAD changed after repair verification."
            )

        status_output = self._require_git(
            source_root,
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
            operation=(
                "Source cleanliness verification"
            ),
        )

        if status_output:
            raise RepairWorkspaceError(
                "Source checkout is not clean."
            )

    def _current_verification(
        self,
        *,
        workspace: RepairWorkspace,
        decision: RepairDecision,
        validation: RepairValidationResult,
        selection: RepairTestSelectionResult,
        handoff: RepairTestHandoffResult,
        execution_results: tuple[
            RepairExecutionResult,
            ...,
        ],
        test_result: RepairTestExecutionResult,
    ) -> RepairVerificationResult:
        return RepairResultVerifier(
            git_timeout_seconds=(
                self.git_timeout_seconds
            )
        ).verify(
            workspace=workspace,
            decision=decision,
            validation=validation,
            selection=selection,
            handoff=handoff,
            execution_results=(
                execution_results
            ),
            test_result=test_result,
        )

    def _current_request(
        self,
        *,
        decision: RepairDecision,
        verification: RepairVerificationResult,
    ) -> RepairApplyRequest | None:
        result = (
            RepairApplyRequestBuilder()
            .build(
                decision=decision,
                verification=verification,
            )
        )

        if (
            result.ready_for_confirmation
            is not True
            or result.request is None
        ):
            return None

        return result.request

    @staticmethod
    def _valid_hex(
        value: object,
        lengths: set[int],
    ) -> bool:
        if (
            type(value) is not str
            or len(value) not in lengths
        ):
            return False

        return all(
            character
            in "0123456789abcdef"
            for character in value
        )

    @staticmethod
    def _valid_journal_target(
        value: object,
    ) -> bool:
        if (
            type(value) is not str
            or not value
            or "\\" in value
            or value.startswith("/")
            or not value.endswith(".py")
        ):
            return False

        parts = value.split(
            "/"
        )

        if (
            not parts
            or parts[0] != "app"
        ):
            return False

        return not any(
            part in {
                "",
                ".",
                "..",
                ".git",
                ".venv",
                "venv",
                "env",
                ".env",
            }
            or part.startswith(
                ".env."
            )
            for part in parts
        )

    @staticmethod
    def _fsync_directory(
        directory: Path,
    ) -> None:
        descriptor = os.open(
            directory,
            os.O_RDONLY,
        )

        try:
            os.fsync(
                descriptor
            )
        finally:
            os.close(
                descriptor
            )

    def _git_directory(
        self,
        *,
        source_root: Path,
    ) -> Path:
        raw = self._require_git(
            source_root,
            "rev-parse",
            "--path-format=absolute",
            "--git-dir",
            operation=(
                "Git metadata-directory verification"
            ),
        )

        git_directory = Path(
            raw
        ).expanduser().resolve()

        if (
            git_directory.is_symlink()
            or not git_directory.exists()
            or not git_directory.is_dir()
        ):
            raise RepairWorkspaceError(
                "Git metadata directory is unavailable "
                "or unsafe for rollback journaling."
            )

        return git_directory

    def _journal_paths(
        self,
        *,
        source_root: Path,
        create: bool,
    ) -> tuple[
        Path,
        Path,
    ]:
        git_directory = (
            self._git_directory(
                source_root=source_root
            )
        )

        journal_root = (
            git_directory
            / "kuma-repair-rollback"
        )

        if journal_root.exists():
            if (
                journal_root.is_symlink()
                or not journal_root.is_dir()
            ):
                raise RepairWorkspaceError(
                    "Rollback journal root is unsafe."
                )

        elif create:
            os.mkdir(
                journal_root,
                0o700,
            )

            self._fsync_directory(
                git_directory
            )

        active = (
            journal_root
            / "active"
        )

        return (
            journal_root,
            active,
        )

    def _cleanup_stale_staging(
        self,
        *,
        journal_root: Path,
    ) -> None:
        if not journal_root.exists():
            return

        for path in tuple(
            journal_root.iterdir()
        ):
            if not path.name.startswith(
                ".staging-"
            ):
                continue

            suffix = path.name[
                len(".staging-"):
            ]

            if not self._valid_hex(
                suffix,
                {
                    64,
                },
            ):
                raise RepairWorkspaceError(
                    "Unexpected rollback-journal staging "
                    "entry requires manual inspection."
                )

            if (
                path.is_symlink()
                or not path.is_dir()
            ):
                raise RepairWorkspaceError(
                    "Rollback-journal staging entry "
                    "is unsafe."
                )

            shutil.rmtree(
                path
            )

        self._fsync_directory(
            journal_root
        )

    @staticmethod
    def _write_fsynced(
        *,
        path: Path,
        content: bytes,
    ) -> None:
        with open(
            path,
            "xb",
        ) as stream:
            stream.write(
                content
            )
            stream.flush()
            os.fsync(
                stream.fileno()
            )

    def _write_journal(
        self,
        *,
        source_root: Path,
        request: RepairApplyRequest,
        snapshots: tuple[
            _FileSnapshot,
            ...,
        ],
        candidate_payloads: dict[
            str,
            bytes,
        ],
    ) -> None:
        (
            journal_root,
            active,
        ) = self._journal_paths(
            source_root=source_root,
            create=True,
        )

        if active.exists():
            raise RepairWorkspaceError(
                "A prior rollback journal is already active."
            )

        self._cleanup_stale_staging(
            journal_root=journal_root
        )

        staging = (
            journal_root
            / (
                ".staging-"
                + request.request_digest
            )
        )

        files_directory = (
            staging
            / "files"
        )

        os.mkdir(
            staging,
            0o700,
        )

        os.mkdir(
            files_directory,
            0o700,
        )

        entries: list[
            dict[str, object]
        ] = []

        try:
            for index, snapshot in enumerate(
                snapshots
            ):
                if (
                    snapshot.relative_path
                    not in candidate_payloads
                ):
                    raise RepairWorkspaceError(
                        "Rollback journal candidate scope "
                        "is incomplete."
                    )

                snapshot_name = (
                    f"{index:03d}.bin"
                )

                snapshot_path = (
                    files_directory
                    / snapshot_name
                )

                self._write_fsynced(
                    path=snapshot_path,
                    content=snapshot.content,
                )

                candidate_digest = (
                    self._digest(
                        candidate_payloads[
                            snapshot.relative_path
                        ]
                    )
                )

                entries.append(
                    {
                        "relative_path": (
                            snapshot.relative_path
                        ),
                        "snapshot_file": (
                            "files/"
                            + snapshot_name
                        ),
                        "original_digest": (
                            snapshot.digest
                        ),
                        "candidate_digest": (
                            candidate_digest
                        ),
                        "mode": (
                            snapshot.mode
                        ),
                        "size": len(
                            snapshot.content
                        ),
                    }
                )

            manifest = {
                "version": 1,
                "source_head": (
                    request.source_head
                ),
                "request_digest": (
                    request.request_digest
                ),
                "changed_files": list(
                    request.changed_files
                ),
                "files": entries,
            }

            manifest_payload = (
                json.dumps(
                    manifest,
                    sort_keys=True,
                    separators=(
                        ",",
                        ":",
                    ),
                    ensure_ascii=False,
                )
                + "\n"
            ).encode(
                "utf-8"
            )

            self._write_fsynced(
                path=(
                    staging
                    / "manifest.json"
                ),
                content=manifest_payload,
            )

            self._write_fsynced(
                path=(
                    staging
                    / "state"
                ),
                content=b"prepared\n",
            )

            self._fsync_directory(
                files_directory
            )

            self._fsync_directory(
                staging
            )

            os.replace(
                staging,
                active,
            )

            self._fsync_directory(
                journal_root
            )

        except Exception:
            if staging.exists():
                shutil.rmtree(
                    staging,
                    ignore_errors=True,
                )

                try:
                    self._fsync_directory(
                        journal_root
                    )
                except OSError:
                    pass

            raise

    def _read_active_journal(
        self,
        *,
        source_root: Path,
    ) -> _RollbackJournal | None:
        (
            journal_root,
            active,
        ) = self._journal_paths(
            source_root=source_root,
            create=False,
        )

        if not journal_root.exists():
            return None

        if not active.exists():
            self._cleanup_stale_staging(
                journal_root=journal_root
            )
            return None

        if (
            active.is_symlink()
            or not active.is_dir()
        ):
            raise RepairWorkspaceError(
                "Active rollback journal is unsafe."
            )

        manifest_path = (
            active
            / "manifest.json"
        )

        state_path = (
            active
            / "state"
        )

        if (
            manifest_path.is_symlink()
            or state_path.is_symlink()
            or not manifest_path.is_file()
            or not state_path.is_file()
        ):
            raise RepairWorkspaceError(
                "Rollback journal is incomplete."
            )

        manifest_bytes = (
            manifest_path.read_bytes()
        )

        if (
            not manifest_bytes
            or len(manifest_bytes)
            > 256_000
        ):
            raise RepairWorkspaceError(
                "Rollback journal manifest is malformed."
            )

        try:
            manifest = json.loads(
                manifest_bytes.decode(
                    "utf-8"
                )
            )
        except (
            UnicodeDecodeError,
            json.JSONDecodeError,
        ) as error:
            raise RepairWorkspaceError(
                "Rollback journal manifest cannot be parsed."
            ) from error

        if (
            type(manifest) is not dict
            or set(manifest) != {
                "version",
                "source_head",
                "request_digest",
                "changed_files",
                "files",
            }
        ):
            raise RepairWorkspaceError(
                "Rollback journal manifest contract "
                "is invalid."
            )

        if manifest["version"] != 1:
            raise RepairWorkspaceError(
                "Rollback journal version is unsupported."
            )

        source_head = (
            manifest["source_head"]
        )

        request_digest = (
            manifest["request_digest"]
        )

        if not self._valid_hex(
            source_head,
            {
                40,
                64,
            },
        ):
            raise RepairWorkspaceError(
                "Rollback journal source HEAD is malformed."
            )

        if not self._valid_hex(
            request_digest,
            {
                64,
            },
        ):
            raise RepairWorkspaceError(
                "Rollback journal request digest is malformed."
            )

        changed_raw = (
            manifest["changed_files"]
        )

        if (
            type(changed_raw) is not list
            or not changed_raw
            or len(changed_raw) > 5
            or len(
                set(
                    changed_raw
                )
            )
            != len(
                changed_raw
            )
            or any(
                not self._valid_journal_target(
                    value
                )
                for value in changed_raw
            )
        ):
            raise RepairWorkspaceError(
                "Rollback journal changed-file scope "
                "is malformed."
            )

        changed_files = tuple(
            changed_raw
        )

        entries = (
            manifest["files"]
        )

        if (
            type(entries) is not list
            or len(entries)
            != len(changed_files)
        ):
            raise RepairWorkspaceError(
                "Rollback journal snapshot evidence "
                "is incomplete."
            )

        try:
            state = (
                state_path
                .read_text(
                    encoding="utf-8"
                )
                .strip()
            )
        except (
            OSError,
            UnicodeDecodeError,
        ) as error:
            raise RepairWorkspaceError(
                "Rollback journal state cannot be read."
            ) from error

        if state not in {
            "prepared",
            "applied",
        }:
            raise RepairWorkspaceError(
                "Rollback journal state is invalid."
            )

        snapshots: list[
            _FileSnapshot
        ] = []

        candidate_digests: list[
            tuple[str, str]
        ] = []

        for index, entry in enumerate(
            entries
        ):
            if (
                type(entry) is not dict
                or set(entry) != {
                    "relative_path",
                    "snapshot_file",
                    "original_digest",
                    "candidate_digest",
                    "mode",
                    "size",
                }
            ):
                raise RepairWorkspaceError(
                    "Rollback journal file evidence "
                    "is malformed."
                )

            relative_path = (
                entry["relative_path"]
            )

            expected_snapshot_file = (
                f"files/{index:03d}.bin"
            )

            if (
                relative_path
                != changed_files[index]
                or entry["snapshot_file"]
                != expected_snapshot_file
                or not self._valid_hex(
                    entry["original_digest"],
                    {
                        64,
                    },
                )
                or not self._valid_hex(
                    entry["candidate_digest"],
                    {
                        64,
                    },
                )
                or type(entry["mode"])
                is not int
                or entry["mode"] < 0
                or entry["mode"] > 0o7777
                or type(entry["size"])
                is not int
                or entry["size"] < 0
                or entry["size"]
                > self.max_file_bytes
            ):
                raise RepairWorkspaceError(
                    "Rollback journal file evidence "
                    "failed strict validation."
                )

            snapshot_path = (
                active
                / expected_snapshot_file
            )

            if (
                snapshot_path.is_symlink()
                or not snapshot_path.is_file()
            ):
                raise RepairWorkspaceError(
                    "Rollback snapshot file is unsafe "
                    "or unavailable."
                )

            content = (
                snapshot_path
                .read_bytes()
            )

            if (
                len(content)
                != entry["size"]
                or self._digest(
                    content
                )
                != entry[
                    "original_digest"
                ]
            ):
                raise RepairWorkspaceError(
                    "Rollback snapshot bytes failed "
                    "integrity verification."
                )

            snapshots.append(
                _FileSnapshot(
                    relative_path=(
                        relative_path
                    ),
                    content=content,
                    mode=(
                        entry["mode"]
                    ),
                    digest=(
                        entry[
                            "original_digest"
                        ]
                    ),
                )
            )

            candidate_digests.append(
                (
                    relative_path,
                    entry[
                        "candidate_digest"
                    ],
                )
            )

        return _RollbackJournal(
            state=state,
            source_head=source_head,
            request_digest=(
                request_digest
            ),
            changed_files=(
                changed_files
            ),
            snapshots=tuple(
                snapshots
            ),
            candidate_digests=tuple(
                candidate_digests
            ),
        )

    def _mark_journal_applied(
        self,
        *,
        source_root: Path,
    ) -> None:
        (
            _,
            active,
        ) = self._journal_paths(
            source_root=source_root,
            create=False,
        )

        if (
            not active.exists()
            or active.is_symlink()
            or not active.is_dir()
        ):
            raise RepairWorkspaceError(
                "Active rollback journal disappeared "
                "before completion could be recorded."
            )

        temporary_state = (
            active
            / ".state.tmp"
        )

        if temporary_state.exists():
            raise RepairWorkspaceError(
                "Unexpected rollback-journal state "
                "temporary file exists."
            )

        self._write_fsynced(
            path=temporary_state,
            content=b"applied\n",
        )

        os.replace(
            temporary_state,
            (
                active
                / "state"
            ),
        )

        self._fsync_directory(
            active
        )

    def _clear_active_journal(
        self,
        *,
        source_root: Path,
    ) -> None:
        (
            journal_root,
            active,
        ) = self._journal_paths(
            source_root=source_root,
            create=False,
        )

        if not journal_root.exists():
            return

        if active.exists():
            if (
                active.is_symlink()
                or not active.is_dir()
            ):
                raise RepairWorkspaceError(
                    "Active rollback journal became unsafe."
                )

            shutil.rmtree(
                active
            )

            self._fsync_directory(
                journal_root
            )

        self._cleanup_stale_staging(
            journal_root=journal_root
        )

    def _recover_pending_journal(
        self,
        *,
        source_root: Path,
    ) -> RepairApplyResult | None:
        journal = (
            self._read_active_journal(
                source_root=source_root
            )
        )

        if journal is None:
            return None

        top_level = self._require_git(
            source_root,
            "rev-parse",
            "--show-toplevel",
            operation=(
                "Interrupted-repair repository verification"
            ),
        )

        if (
            Path(
                top_level
            ).expanduser().resolve()
            != source_root
        ):
            return self._reject(
                "Interrupted repair recovery is blocked: "
                "source repository root changed.",
                changed_files=(
                    journal.changed_files
                ),
                request_digest=(
                    journal.request_digest
                ),
                recovery_blocked=True,
            )

        head = self._require_git(
            source_root,
            "rev-parse",
            "--verify",
            "HEAD",
            operation=(
                "Interrupted-repair HEAD verification"
            ),
        )

        if head != journal.source_head:
            return self._reject(
                "Interrupted repair recovery is blocked: "
                "source HEAD changed.",
                changed_files=(
                    journal.changed_files
                ),
                request_digest=(
                    journal.request_digest
                ),
                recovery_blocked=True,
            )

        candidate_by_path = dict(
            journal.candidate_digests
        )

        live_payloads: dict[
            str,
            bytes,
        ] = {}

        for snapshot in (
            journal.snapshots
        ):
            target = (
                source_root
                / snapshot.relative_path
            )

            if (
                target.is_symlink()
                or not target.exists()
                or not target.is_file()
            ):
                return self._reject(
                    "Interrupted repair recovery is blocked: "
                    "a target became unsafe or unavailable.",
                    changed_files=(
                        journal.changed_files
                    ),
                    request_digest=(
                        journal.request_digest
                    ),
                    recovery_blocked=True,
                )

            resolved = (
                target.resolve()
            )

            if not self._within(
                resolved,
                source_root,
            ):
                return self._reject(
                    "Interrupted repair recovery is blocked: "
                    "a target escaped the repository root.",
                    changed_files=(
                        journal.changed_files
                    ),
                    request_digest=(
                        journal.request_digest
                    ),
                    recovery_blocked=True,
                )

            content = (
                target.read_bytes()
            )

            if (
                len(content)
                > self.max_file_bytes
            ):
                return self._reject(
                    "Interrupted repair recovery is blocked: "
                    "a live target exceeds the size limit.",
                    changed_files=(
                        journal.changed_files
                    ),
                    request_digest=(
                        journal.request_digest
                    ),
                    recovery_blocked=True,
                )

            live_digest = (
                self._digest(
                    content
                )
            )

            current_mode = stat.S_IMODE(
                target.stat().st_mode
            )

            if current_mode != snapshot.mode:
                return self._reject(
                    "Interrupted repair recovery is blocked: "
                    "a live target mode became ambiguous.",
                    changed_files=(
                        journal.changed_files
                    ),
                    request_digest=(
                        journal.request_digest
                    ),
                    recovery_blocked=True,
                )

            if journal.state == "prepared":
                if live_digest not in {
                    snapshot.digest,
                    candidate_by_path[
                        snapshot.relative_path
                    ],
                }:
                    return self._reject(
                        "Interrupted repair recovery is blocked: "
                        "live bytes are neither the original "
                        "snapshot nor the approved candidate.",
                        changed_files=(
                            journal.changed_files
                        ),
                        request_digest=(
                            journal.request_digest
                        ),
                        recovery_blocked=True,
                    )

            else:
                if (
                    live_digest
                    != candidate_by_path[
                        snapshot.relative_path
                    ]
                ):
                    return self._reject(
                        "Completed repair recovery is blocked: "
                        "applied bytes no longer match the "
                        "durably verified candidate.",
                        changed_files=(
                            journal.changed_files
                        ),
                        request_digest=(
                            journal.request_digest
                        ),
                        recovery_blocked=True,
                    )

            live_payloads[
                snapshot.relative_path
            ] = content

        if journal.state == "applied":
            try:
                self._post_apply_verify(
                    source_root=source_root,
                    expected_head=(
                        journal.source_head
                    ),
                    candidate_payloads=(
                        live_payloads
                    ),
                    changed_files=(
                        journal.changed_files
                    ),
                )

                self._clear_active_journal(
                    source_root=source_root
                )

            except Exception as error:
                return RepairApplyResult(
                    attempted=False,
                    approved=True,
                    applied=True,
                    rolled_back=False,
                    rollback_failed=False,
                    reason=(
                        "A previously completed approved repair "
                        "was found, but journal reconciliation "
                        "could not finish safely: "
                        f"{error}"
                    ),
                    changed_files=(
                        journal.changed_files
                    ),
                    request_digest=(
                        journal.request_digest
                    ),
                    recovered_interrupted_apply=True,
                    recovery_blocked=True,
                )

            return RepairApplyResult(
                attempted=False,
                approved=True,
                applied=True,
                rolled_back=False,
                rollback_failed=False,
                reason=(
                    "Recovered a previously completed approved "
                    "repair. Verified candidate bytes were "
                    "preserved and the durable journal was cleared."
                ),
                changed_files=(
                    journal.changed_files
                ),
                request_digest=(
                    journal.request_digest
                ),
                recovered_interrupted_apply=True,
                recovery_blocked=False,
            )

        rollback_ok, failures = (
            self._restore(
                source_root=source_root,
                snapshots=(
                    journal.snapshots
                ),
            )
        )

        if not rollback_ok:
            return RepairApplyResult(
                attempted=False,
                approved=True,
                applied=False,
                rolled_back=False,
                rollback_failed=True,
                reason=(
                    "Interrupted repair rollback could not "
                    "fully restore: "
                    + ", ".join(
                        failures
                    )
                ),
                changed_files=(
                    journal.changed_files
                ),
                request_digest=(
                    journal.request_digest
                ),
                recovered_interrupted_apply=True,
                recovery_blocked=True,
            )

        try:
            self._source_preflight(
                source_root=source_root,
                expected_head=(
                    journal.source_head
                ),
            )

            self._clear_active_journal(
                source_root=source_root
            )

        except Exception as error:
            return RepairApplyResult(
                attempted=False,
                approved=True,
                applied=False,
                rolled_back=True,
                rollback_failed=True,
                reason=(
                    "Interrupted repair source bytes were "
                    "restored, but durable recovery could "
                    "not be finalized safely: "
                    f"{error}"
                ),
                changed_files=(
                    journal.changed_files
                ),
                request_digest=(
                    journal.request_digest
                ),
                recovered_interrupted_apply=True,
                recovery_blocked=True,
            )

        return RepairApplyResult(
            attempted=False,
            approved=True,
            applied=False,
            rolled_back=True,
            rollback_failed=False,
            reason=(
                "Recovered an interrupted approved repair by "
                "restoring the exact pre-apply source snapshot. "
                "A fresh repair verification and approval are "
                "required before another application."
            ),
            changed_files=(
                journal.changed_files
            ),
            request_digest=(
                journal.request_digest
            ),
            recovered_interrupted_apply=True,
            recovery_blocked=False,
        )

    def _candidate_bytes(
        self,
        *,
        workspace_root: Path,
        changed_files: tuple[str, ...],
    ) -> dict[str, bytes]:
        payloads: dict[
            str,
            bytes,
        ] = {}

        for relative_path in changed_files:
            candidate = (
                workspace_root
                / relative_path
            )

            if (
                candidate.is_symlink()
                or not candidate.exists()
                or not candidate.is_file()
            ):
                raise RepairWorkspaceError(
                    "Verified candidate target became "
                    f"unavailable or unsafe: {relative_path}"
                )

            resolved = (
                candidate.resolve()
            )

            if not self._within(
                resolved,
                workspace_root,
            ):
                raise RepairWorkspaceError(
                    "Verified candidate target escaped "
                    "the repair workspace."
                )

            content = (
                candidate.read_bytes()
            )

            if (
                len(content)
                > self.max_file_bytes
            ):
                raise RepairWorkspaceError(
                    "Verified candidate target exceeds "
                    "the apply size limit."
                )

            payloads[
                relative_path
            ] = content

        return payloads

    def _snapshot_source(
        self,
        *,
        source_root: Path,
        changed_files: tuple[str, ...],
    ) -> tuple[
        _FileSnapshot,
        ...,
    ]:
        snapshots: list[
            _FileSnapshot
        ] = []

        for relative_path in changed_files:
            target = (
                source_root
                / relative_path
            )

            if (
                target.is_symlink()
                or not target.exists()
                or not target.is_file()
            ):
                raise RepairWorkspaceError(
                    "Source repair target is unavailable "
                    f"or unsafe: {relative_path}"
                )

            resolved = (
                target.resolve()
            )

            if not self._within(
                resolved,
                source_root,
            ):
                raise RepairWorkspaceError(
                    "Source repair target escaped "
                    "the repository root."
                )

            content = (
                target.read_bytes()
            )

            if (
                len(content)
                > self.max_file_bytes
            ):
                raise RepairWorkspaceError(
                    "Source repair target exceeds "
                    "the apply size limit."
                )

            mode = stat.S_IMODE(
                target.stat().st_mode
            )

            snapshots.append(
                _FileSnapshot(
                    relative_path=(
                        relative_path
                    ),
                    content=content,
                    mode=mode,
                    digest=(
                        self._digest(
                            content
                        )
                    ),
                )
            )

        return tuple(
            snapshots
        )

    @staticmethod
    def _atomic_replace(
        *,
        target: Path,
        content: bytes,
        mode: int,
    ) -> None:
        temporary_path: Path | None = None

        try:
            descriptor, name = (
                tempfile.mkstemp(
                    prefix=".kuma-repair-",
                    suffix=".tmp",
                    dir=str(
                        target.parent
                    ),
                )
            )

            temporary_path = Path(
                name
            )

            with os.fdopen(
                descriptor,
                "wb",
            ) as stream:
                stream.write(
                    content
                )
                stream.flush()
                os.fsync(
                    stream.fileno()
                )

            os.chmod(
                temporary_path,
                mode,
            )

            os.replace(
                temporary_path,
                target,
            )

            RepairApplyExecutor._fsync_directory(
                target.parent
            )

            temporary_path = None

        finally:
            if (
                temporary_path
                is not None
                and temporary_path.exists()
            ):
                try:
                    temporary_path.unlink()
                except OSError:
                    pass

    def _restore(
        self,
        *,
        source_root: Path,
        snapshots: tuple[
            _FileSnapshot,
            ...,
        ],
    ) -> tuple[
        bool,
        tuple[str, ...],
    ]:
        failures: list[str] = []

        for snapshot in snapshots:
            target = (
                source_root
                / snapshot.relative_path
            )

            try:
                self._atomic_replace(
                    target=target,
                    content=snapshot.content,
                    mode=snapshot.mode,
                )

                restored = (
                    target.read_bytes()
                )

                restored_mode = stat.S_IMODE(
                    target.stat().st_mode
                )

                if (
                    self._digest(
                        restored
                    )
                    != snapshot.digest
                    or restored_mode
                    != snapshot.mode
                ):
                    failures.append(
                        snapshot.relative_path
                    )

            except Exception:
                failures.append(
                    snapshot.relative_path
                )

        return (
            not failures,
            tuple(
                failures
            ),
        )

    def _post_apply_verify(
        self,
        *,
        source_root: Path,
        expected_head: str,
        candidate_payloads: dict[
            str,
            bytes,
        ],
        changed_files: tuple[str, ...],
    ) -> None:
        head = self._require_git(
            source_root,
            "rev-parse",
            "--verify",
            "HEAD",
            operation=(
                "Post-apply source HEAD verification"
            ),
        )

        if head != expected_head:
            raise RepairWorkspaceError(
                "Source HEAD changed during repair application."
            )

        for relative_path in changed_files:
            live_target = (
                source_root
                / relative_path
            )

            if (
                live_target.is_symlink()
                or not live_target.is_file()
            ):
                raise RepairWorkspaceError(
                    "Applied repair target became unsafe."
                )

            live_bytes = (
                live_target.read_bytes()
            )

            if (
                live_bytes
                != candidate_payloads[
                    relative_path
                ]
            ):
                raise RepairWorkspaceError(
                    "Applied source bytes do not exactly "
                    "match the verified candidate."
                )

        changed_output = self._require_git(
            source_root,
            "diff",
            "--name-only",
            "--no-renames",
            "-z",
            "HEAD",
            "--",
            operation=(
                "Post-apply changed-file verification"
            ),
        )

        changed = tuple(
            sorted(
                path
                for path
                in changed_output.split(
                    "\0"
                )
                if path
            )
        )

        expected = tuple(
            sorted(
                changed_files
            )
        )

        if changed != expected:
            raise RepairWorkspaceError(
                "Source checkout contains unexpected "
                "post-apply changes."
            )

        untracked_output = self._require_git(
            source_root,
            "ls-files",
            "--others",
            "--exclude-standard",
            "-z",
            operation=(
                "Post-apply untracked-file verification"
            ),
        )

        if untracked_output:
            raise RepairWorkspaceError(
                "Unexpected untracked files appeared "
                "during repair application."
            )

    def apply(
        self,
        *,
        workspace: RepairWorkspace,
        decision: RepairDecision,
        validation: RepairValidationResult,
        selection: RepairTestSelectionResult,
        handoff: RepairTestHandoffResult,
        execution_results: tuple[
            RepairExecutionResult,
            ...,
        ],
        test_result: RepairTestExecutionResult,
        verification: RepairVerificationResult,
        request: RepairApplyRequest,
        confirmation_requester: Callable[
            [
                str,
                dict[str, object],
            ],
            bool,
        ],
    ) -> RepairApplyResult:
        if not isinstance(
            workspace,
            RepairWorkspace,
        ):
            return self._reject(
                "Repair workspace contract is invalid."
            )

        if not isinstance(
            decision,
            RepairDecision,
        ):
            return self._reject(
                "Repair decision contract is invalid."
            )

        if not isinstance(
            verification,
            RepairVerificationResult,
        ):
            return self._reject(
                "Repair verification contract is invalid."
            )

        if not isinstance(
            request,
            RepairApplyRequest,
        ):
            return self._reject(
                "Repair apply-request contract is invalid."
            )

        if not callable(
            confirmation_requester
        ):
            return self._reject(
                "Explicit human confirmation requester "
                "is unavailable."
            )

        if (
            request
            .requires_explicit_human_approval
            is not True
        ):
            return self._reject(
                "Repair request does not require explicit "
                "human approval."
            )

        try:
            info = workspace.info
        except RepairWorkspaceError as error:
            return self._reject(
                "Repair workspace is not active: "
                f"{error}"
            )

        source_root = (
            info.source_root
            .resolve()
        )

        workspace_root = (
            info.workspace_root
            .resolve()
        )

        try:
            pending_recovery = (
                self._recover_pending_journal(
                    source_root=source_root
                )
            )
        except Exception as error:
            return self._reject(
                "A prior repair rollback journal could "
                "not be reconciled safely: "
                f"{error}",
                recovery_blocked=True,
            )

        if pending_recovery is not None:
            return pending_recovery

        current_verification = (
            self._current_verification(
                workspace=workspace,
                decision=decision,
                validation=validation,
                selection=selection,
                handoff=handoff,
                execution_results=(
                    execution_results
                ),
                test_result=test_result,
            )
        )

        if not self._verification_matches(
            verification,
            current_verification,
        ):
            return self._reject(
                "Repair verification is stale, forged, "
                "or no longer matches the candidate.",
                changed_files=(
                    current_verification
                    .changed_files
                ),
            )

        current_request = (
            self._current_request(
                decision=decision,
                verification=(
                    current_verification
                ),
            )
        )

        if (
            current_request is None
            or not self._request_matches(
                request,
                current_request,
            )
        ):
            return self._reject(
                "Repair apply request is stale, forged, "
                "or no longer matches verified evidence."
            )

        try:
            self._source_preflight(
                source_root=source_root,
                expected_head=(
                    request.source_head
                ),
            )

            candidate_payloads = (
                self._candidate_bytes(
                    workspace_root=(
                        workspace_root
                    ),
                    changed_files=(
                        request.changed_files
                    ),
                )
            )

        except (
            RepairWorkspaceError,
            OSError,
        ) as error:
            return self._reject(
                "Repair apply preflight failed closed: "
                f"{error}",
                changed_files=(
                    request.changed_files
                ),
                request_digest=(
                    request.request_digest
                ),
            )

        try:
            approved = (
                confirmation_requester(
                    self._CONFIRMATION_ACTION,
                    request
                    .confirmation_arguments(),
                )
                is True
            )
        except Exception as error:
            return self._reject(
                "Repair confirmation failed closed: "
                f"{error}",
                changed_files=(
                    request.changed_files
                ),
                request_digest=(
                    request.request_digest
                ),
            )

        if not approved:
            return self._reject(
                "User denied repair application.",
                changed_files=(
                    request.changed_files
                ),
                request_digest=(
                    request.request_digest
                ),
            )

        # Approval is not allowed to override changed state.
        # Rebuild the entire evidence/request chain and source
        # preflight immediately after the synchronous confirmation.
        post_approval_verification = (
            self._current_verification(
                workspace=workspace,
                decision=decision,
                validation=validation,
                selection=selection,
                handoff=handoff,
                execution_results=(
                    execution_results
                ),
                test_result=test_result,
            )
        )

        if not self._verification_matches(
            current_verification,
            post_approval_verification,
        ):
            return self._reject(
                "Repair evidence changed while awaiting "
                "human approval.",
                approved=True,
                changed_files=(
                    request.changed_files
                ),
                request_digest=(
                    request.request_digest
                ),
            )

        post_approval_request = (
            self._current_request(
                decision=decision,
                verification=(
                    post_approval_verification
                ),
            )
        )

        if (
            post_approval_request is None
            or not self._request_matches(
                request,
                post_approval_request,
            )
        ):
            return self._reject(
                "Repair identity changed while awaiting "
                "human approval.",
                approved=True,
                changed_files=(
                    request.changed_files
                ),
                request_digest=(
                    request.request_digest
                ),
            )

        try:
            self._source_preflight(
                source_root=source_root,
                expected_head=(
                    request.source_head
                ),
            )

            candidate_payloads_after = (
                self._candidate_bytes(
                    workspace_root=(
                        workspace_root
                    ),
                    changed_files=(
                        request.changed_files
                    ),
                )
            )

            if (
                candidate_payloads_after
                != candidate_payloads
            ):
                raise RepairWorkspaceError(
                    "Candidate bytes changed while awaiting "
                    "human approval."
                )

            snapshots = (
                self._snapshot_source(
                    source_root=(
                        source_root
                    ),
                    changed_files=(
                        request.changed_files
                    ),
                )
            )

            self._write_journal(
                source_root=source_root,
                request=request,
                snapshots=snapshots,
                candidate_payloads=(
                    candidate_payloads
                ),
            )

        except (
            RepairWorkspaceError,
            OSError,
        ) as error:
            return self._reject(
                "Post-approval repair preflight failed "
                f"closed: {error}",
                approved=True,
                changed_files=(
                    request.changed_files
                ),
                request_digest=(
                    request.request_digest
                ),
            )

        attempted = False

        try:
            attempted = True

            snapshot_by_path = {
                snapshot.relative_path:
                snapshot
                for snapshot in snapshots
            }

            for relative_path in (
                request.changed_files
            ):
                snapshot = (
                    snapshot_by_path[
                        relative_path
                    ]
                )

                self._atomic_replace(
                    target=(
                        source_root
                        / relative_path
                    ),
                    content=(
                        candidate_payloads[
                            relative_path
                        ]
                    ),
                    mode=snapshot.mode,
                )

            self._post_apply_verify(
                source_root=source_root,
                expected_head=(
                    request.source_head
                ),
                candidate_payloads=(
                    candidate_payloads
                ),
                changed_files=(
                    request.changed_files
                ),
            )

        except Exception as error:
            rollback_ok, rollback_failures = (
                self._restore(
                    source_root=source_root,
                    snapshots=snapshots,
                )
            )

            if rollback_ok:
                try:
                    self._source_preflight(
                        source_root=source_root,
                        expected_head=(
                            request.source_head
                        ),
                    )

                    self._clear_active_journal(
                        source_root=source_root
                    )

                except Exception as recovery_error:
                    return RepairApplyResult(
                        attempted=attempted,
                        approved=True,
                        applied=False,
                        rolled_back=True,
                        rollback_failed=True,
                        reason=(
                            "Repair application failed and "
                            "source bytes were restored, but "
                            "rollback finalization failed: "
                            f"{recovery_error}"
                        ),
                        changed_files=(
                            request.changed_files
                        ),
                        request_digest=(
                            request.request_digest
                        ),
                        recovery_blocked=True,
                    )

                return RepairApplyResult(
                    attempted=attempted,
                    approved=True,
                    applied=False,
                    rolled_back=True,
                    rollback_failed=False,
                    reason=(
                        "Repair application failed and the "
                        "exact original source snapshot was "
                        "restored and verified: "
                        f"{error}"
                    ),
                    changed_files=(
                        request.changed_files
                    ),
                    request_digest=(
                        request.request_digest
                    ),
                )

            return RepairApplyResult(
                attempted=attempted,
                approved=True,
                applied=False,
                rolled_back=False,
                rollback_failed=True,
                reason=(
                    "Repair application failed and rollback "
                    "could not fully restore: "
                    + ", ".join(
                        rollback_failures
                    )
                ),
                changed_files=(
                    request.changed_files
                ),
                request_digest=(
                    request.request_digest
                ),
                recovery_blocked=True,
            )

        try:
            self._mark_journal_applied(
                source_root=source_root
            )

        except Exception as error:
            rollback_ok, rollback_failures = (
                self._restore(
                    source_root=source_root,
                    snapshots=snapshots,
                )
            )

            if rollback_ok:
                try:
                    self._source_preflight(
                        source_root=source_root,
                        expected_head=(
                            request.source_head
                        ),
                    )

                    self._clear_active_journal(
                        source_root=source_root
                    )
                except Exception:
                    pass

            return RepairApplyResult(
                attempted=True,
                approved=True,
                applied=False,
                rolled_back=rollback_ok,
                rollback_failed=(
                    not rollback_ok
                ),
                reason=(
                    "Repair bytes passed post-apply verification "
                    "but durable completion could not be recorded; "
                    "the repair was rolled back where possible: "
                    f"{error}"
                ),
                changed_files=(
                    request.changed_files
                ),
                request_digest=(
                    request.request_digest
                ),
                recovery_blocked=(
                    not rollback_ok
                ),
            )

        journal_cleanup_error = None

        try:
            self._clear_active_journal(
                source_root=source_root
            )
        except Exception as error:
            # The durable state is already "applied".
            # A future invocation can safely reconcile and
            # preserve the exact verified candidate.
            journal_cleanup_error = error

        return RepairApplyResult(
            attempted=True,
            approved=True,
            applied=True,
            rolled_back=False,
            rollback_failed=False,
            reason=(
                (
                    "Explicitly approved verified repair was "
                    "transactionally applied to the source "
                    "working tree. The repair remains uncommitted "
                    "and no push or Git history mutation occurred."
                )
                if journal_cleanup_error is None
                else (
                    "Explicitly approved verified repair was "
                    "applied and durably marked complete, but "
                    "rollback-journal cleanup is pending: "
                    f"{journal_cleanup_error}"
                )
            ),
            changed_files=(
                request.changed_files
            ),
            request_digest=(
                request.request_digest
            ),
            recovery_blocked=(
                journal_cleanup_error
                is not None
            ),
        )
