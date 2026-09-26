from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess
import tempfile


class RepairWorkspaceError(RuntimeError):
    """
    Raised when an isolated repair workspace cannot be created safely.
    """


@dataclass(frozen=True)
class RepairWorkspaceInfo:
    """
    Immutable evidence describing one isolated repair workspace.
    """

    source_root: Path
    workspace_root: Path
    source_head: str


class RepairWorkspace:
    """
    Create an isolated local Git clone at the source repository's
    exact committed HEAD.

    Safety boundary for 6C.2:
    - never edits the source checkout
    - never uses shell=True
    - never commits, merges, pushes, or applies changes back
    - requires a clean source checkout before cloning
    - uses --no-hardlinks so the candidate clone does not share
      Git object files with the source repository
    - cleans up the temporary clone on exit

    This class creates the isolated workspace only. It does not
    generate or apply repair candidates.
    """

    def __init__(
        self,
        repo_root: str | Path,
        *,
        git_timeout_seconds: int = 30,
    ):
        if (
            type(git_timeout_seconds) is not int
            or git_timeout_seconds < 1
        ):
            raise ValueError(
                "git_timeout_seconds must be a positive integer."
            )

        self._repo_root = Path(repo_root).expanduser().resolve()
        self._git_timeout_seconds = git_timeout_seconds
        self._temporary_directory: tempfile.TemporaryDirectory | None = None
        self._info: RepairWorkspaceInfo | None = None

    @property
    def info(self) -> RepairWorkspaceInfo:
        if self._info is None:
            raise RepairWorkspaceError(
                "Repair workspace has not been created."
            )

        return self._info

    @property
    def root(self) -> Path:
        return self.info.workspace_root

    @property
    def source_root(self) -> Path:
        return self.info.source_root

    @property
    def source_head(self) -> str:
        return self.info.source_head

    def _run_git(
        self,
        *args: str,
        cwd: Path | None = None,
    ) -> subprocess.CompletedProcess:
        command = [
            "git",
            *args,
        ]

        try:
            return subprocess.run(
                command,
                cwd=(
                    str(cwd)
                    if cwd is not None
                    else None
                ),
                capture_output=True,
                text=True,
                timeout=self._git_timeout_seconds,
                check=False,
                shell=False,
            )
        except subprocess.TimeoutExpired as error:
            raise RepairWorkspaceError(
                "Git operation timed out while creating the "
                "isolated repair workspace."
            ) from error
        except OSError as error:
            raise RepairWorkspaceError(
                f"Could not execute Git safely: {error}"
            ) from error

    @staticmethod
    def _output_or_default(
        result: subprocess.CompletedProcess,
        default: str,
    ) -> str:
        return (
            (result.stderr or "").strip()
            or (result.stdout or "").strip()
            or default
        )

    def _require_git_success(
        self,
        result: subprocess.CompletedProcess,
        *,
        operation: str,
    ) -> str:
        if result.returncode != 0:
            raise RepairWorkspaceError(
                f"{operation} failed: "
                f"{self._output_or_default(result, 'unknown Git error')}"
            )

        return (result.stdout or "").strip()

    def _validate_source_repository(self) -> tuple[Path, str]:
        if not self._repo_root.exists():
            raise RepairWorkspaceError(
                "Repair source repository does not exist."
            )

        if not self._repo_root.is_dir():
            raise RepairWorkspaceError(
                "Repair source repository must be a directory."
            )

        top_level_result = self._run_git(
            "-C",
            str(self._repo_root),
            "rev-parse",
            "--show-toplevel",
        )

        top_level = self._require_git_success(
            top_level_result,
            operation="Repository-root verification",
        )

        resolved_top_level = Path(
            top_level
        ).expanduser().resolve()

        if resolved_top_level != self._repo_root:
            raise RepairWorkspaceError(
                "Repair source path must be the exact Git "
                "repository root."
            )

        head_result = self._run_git(
            "-C",
            str(self._repo_root),
            "rev-parse",
            "--verify",
            "HEAD",
        )

        source_head = self._require_git_success(
            head_result,
            operation="Source HEAD verification",
        )

        if not source_head:
            raise RepairWorkspaceError(
                "Repair source repository has no committed HEAD."
            )

        status_result = self._run_git(
            "-C",
            str(self._repo_root),
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        )

        status_output = self._require_git_success(
            status_result,
            operation="Source cleanliness verification",
        )

        if status_output:
            raise RepairWorkspaceError(
                "Repair source repository must be clean before "
                "an isolated candidate workspace is created."
            )

        return resolved_top_level, source_head

    def create(self) -> RepairWorkspaceInfo:
        if self._info is not None:
            raise RepairWorkspaceError(
                "Repair workspace is already active."
            )

        source_root, source_head = (
            self._validate_source_repository()
        )

        temporary_directory = tempfile.TemporaryDirectory(
            prefix="kuma-repair-"
        )

        workspace_root = (
            Path(temporary_directory.name)
            / "candidate"
        )

        try:
            clone_result = self._run_git(
                "clone",
                "--quiet",
                "--no-hardlinks",
                "--no-checkout",
                "--",
                str(source_root),
                str(workspace_root),
            )

            self._require_git_success(
                clone_result,
                operation="Isolated repository clone",
            )

            checkout_result = self._run_git(
                "-C",
                str(workspace_root),
                "checkout",
                "--quiet",
                "--detach",
                source_head,
            )

            self._require_git_success(
                checkout_result,
                operation="Detached candidate checkout",
            )

            candidate_head_result = self._run_git(
                "-C",
                str(workspace_root),
                "rev-parse",
                "--verify",
                "HEAD",
            )

            candidate_head = self._require_git_success(
                candidate_head_result,
                operation="Candidate HEAD verification",
            )

            if candidate_head != source_head:
                raise RepairWorkspaceError(
                    "Candidate workspace HEAD does not match "
                    "the captured source HEAD."
                )

            symbolic_result = self._run_git(
                "-C",
                str(workspace_root),
                "symbolic-ref",
                "-q",
                "HEAD",
            )

            if symbolic_result.returncode == 0:
                raise RepairWorkspaceError(
                    "Candidate workspace must use detached HEAD."
                )

            if symbolic_result.returncode not in {1}:
                raise RepairWorkspaceError(
                    "Could not verify detached candidate HEAD: "
                    f"{self._output_or_default(symbolic_result, 'unknown Git error')}"
                )

            # Detect a source checkout that changed while isolation
            # was being created. Do not silently evaluate a repair
            # against a stale or ambiguous live source state.
            source_head_after_result = self._run_git(
                "-C",
                str(source_root),
                "rev-parse",
                "--verify",
                "HEAD",
            )

            source_head_after = self._require_git_success(
                source_head_after_result,
                operation="Source HEAD re-verification",
            )

            source_status_after_result = self._run_git(
                "-C",
                str(source_root),
                "status",
                "--porcelain=v1",
                "--untracked-files=all",
            )

            source_status_after = self._require_git_success(
                source_status_after_result,
                operation="Source cleanliness re-verification",
            )

            if (
                source_head_after != source_head
                or source_status_after
            ):
                raise RepairWorkspaceError(
                    "Repair source repository changed while the "
                    "isolated workspace was being created."
                )

            info = RepairWorkspaceInfo(
                source_root=source_root,
                workspace_root=workspace_root.resolve(),
                source_head=source_head,
            )

            self._temporary_directory = temporary_directory
            self._info = info

            return info

        except Exception:
            temporary_directory.cleanup()
            raise

    def cleanup(self) -> None:
        temporary_directory = self._temporary_directory

        self._info = None
        self._temporary_directory = None

        if temporary_directory is not None:
            temporary_directory.cleanup()

    def __enter__(self) -> "RepairWorkspace":
        self.create()
        return self

    def __exit__(
        self,
        exc_type,
        exc_value,
        traceback,
    ) -> bool:
        self.cleanup()
        return False
