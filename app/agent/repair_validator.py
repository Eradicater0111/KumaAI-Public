from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess
import tokenize

from app.agent.repair_policy import (
    RepairDecision,
)
from app.agent.repair_workspace import (
    RepairWorkspace,
    RepairWorkspaceError,
)


@dataclass(frozen=True)
class RepairValidationResult:
    """
    Immutable evidence from static validation of one repair candidate.

    A valid result means only that the candidate is structurally safe
    enough to proceed to a future execution-isolation stage. It does
    not authorize test execution or application to the main checkout.
    """

    valid: bool
    reason: str
    changed_files: tuple[str, ...] = ()
    diff: str = ""


class RepairValidator:
    """
    Static, fail-closed validation for an isolated repair candidate.

    6C.3 deliberately does NOT execute candidate Python code.

    It may:
    - inspect Git metadata inside the isolated clone
    - inspect changed source files
    - compile source text without executing it
    - collect a textual Git diff as evidence

    It may NOT:
    - run unit tests
    - import candidate modules
    - invoke execute_command
    - commit, merge, push, or apply changes to the source checkout
    """

    def __init__(
        self,
        *,
        git_timeout_seconds: int = 30,
        max_file_bytes: int = 1_000_000,
        max_diff_chars: int = 200_000,
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
            (
                "max_diff_chars",
                max_diff_chars,
            ),
        ):
            if (
                type(value) is not int
                or value < 1
            ):
                raise ValueError(
                    f"{name} must be a positive integer."
                )

        self.git_timeout_seconds = git_timeout_seconds
        self.max_file_bytes = max_file_bytes
        self.max_diff_chars = max_diff_chars

    @staticmethod
    def _invalid(
        reason: str,
        *,
        changed_files: tuple[str, ...] = (),
        diff: str = "",
    ) -> RepairValidationResult:
        return RepairValidationResult(
            valid=False,
            reason=reason,
            changed_files=changed_files,
            diff=diff,
        )

    def _run_git(
        self,
        workspace_root: Path,
        *args: str,
    ) -> subprocess.CompletedProcess:
        try:
            return subprocess.run(
                [
                    "git",
                    "-C",
                    str(workspace_root),
                    *args,
                ],
                capture_output=True,
                text=False,
                timeout=self.git_timeout_seconds,
                check=False,
                shell=False,
            )
        except subprocess.TimeoutExpired as error:
            raise RepairWorkspaceError(
                "Git operation timed out during repair validation."
            ) from error
        except OSError as error:
            raise RepairWorkspaceError(
                f"Could not execute Git during repair validation: "
                f"{error}"
            ) from error

    @staticmethod
    def _git_error(
        result: subprocess.CompletedProcess,
    ) -> str:
        for payload in (
            result.stderr,
            result.stdout,
        ):
            if payload:
                return payload.decode(
                    "utf-8",
                    errors="replace",
                ).strip()

        return "unknown Git error"

    def _require_git_success(
        self,
        result: subprocess.CompletedProcess,
        operation: str,
    ) -> bytes:
        if result.returncode != 0:
            raise RepairWorkspaceError(
                f"{operation} failed: "
                f"{self._git_error(result)}"
            )

        return result.stdout or b""

    @staticmethod
    def _decode_nul_paths(
        payload: bytes,
    ) -> tuple[str, ...]:
        if not payload:
            return ()

        raw_items = payload.split(b"\0")

        if raw_items[-1] == b"":
            raw_items = raw_items[:-1]

        paths = []

        for raw_item in raw_items:
            try:
                path = raw_item.decode(
                    "utf-8",
                    errors="strict",
                )
            except UnicodeDecodeError as error:
                raise RepairWorkspaceError(
                    "Git returned a non-UTF-8 candidate path."
                ) from error

            if not path:
                raise RepairWorkspaceError(
                    "Git returned an empty candidate path."
                )

            paths.append(path)

        return tuple(paths)

    @staticmethod
    def _path_is_within(
        path: Path,
        root: Path,
    ) -> bool:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            return False

    def _validate_contracts(
        self,
        workspace: RepairWorkspace,
        decision: RepairDecision,
    ) -> RepairValidationResult | None:
        if not isinstance(
            workspace,
            RepairWorkspace,
        ):
            return self._invalid(
                "Repair workspace contract is invalid."
            )

        if not isinstance(
            decision,
            RepairDecision,
        ):
            return self._invalid(
                "Repair decision contract is invalid."
            )

        if not decision.eligible_for_isolated_evaluation:
            return self._invalid(
                "Repair decision does not authorize isolated "
                "candidate evaluation."
            )

        if decision.automatic_main_checkout_apply:
            return self._invalid(
                "Repair decision illegally claims automatic "
                "main-checkout authority."
            )

        if (
            type(decision.normalized_target_files) is not tuple
            or not decision.normalized_target_files
        ):
            return self._invalid(
                "Repair decision has no immutable approved target scope."
            )

        for target in decision.normalized_target_files:
            if (
                type(target) is not str
                or not target
            ):
                return self._invalid(
                    "Repair decision contains an invalid target path."
                )

        return None

    def validate(
        self,
        *,
        workspace: RepairWorkspace,
        decision: RepairDecision,
    ) -> RepairValidationResult:
        contract_failure = self._validate_contracts(
            workspace,
            decision,
        )

        if contract_failure is not None:
            return contract_failure

        try:
            info = workspace.info
        except RepairWorkspaceError as error:
            return self._invalid(
                f"Repair workspace is not active: {error}"
            )

        root = info.workspace_root.resolve()

        if not root.exists() or not root.is_dir():
            return self._invalid(
                "Repair workspace root is unavailable."
            )

        git_dir = root / ".git"

        if not git_dir.is_dir():
            return self._invalid(
                "Repair workspace Git metadata is unavailable."
            )

        try:
            head_payload = self._require_git_success(
                self._run_git(
                    root,
                    "rev-parse",
                    "--verify",
                    "HEAD",
                ),
                "Candidate HEAD verification",
            )

            candidate_head = head_payload.decode(
                "ascii",
                errors="strict",
            ).strip()

            if candidate_head != info.source_head:
                return self._invalid(
                    "Candidate HEAD changed after workspace creation."
                )

            symbolic_result = self._run_git(
                root,
                "symbolic-ref",
                "-q",
                "HEAD",
            )

            if symbolic_result.returncode == 0:
                return self._invalid(
                    "Candidate workspace is no longer detached."
                )

            if symbolic_result.returncode != 1:
                return self._invalid(
                    "Could not safely verify detached candidate HEAD."
                )

            untracked_payload = self._require_git_success(
                self._run_git(
                    root,
                    "ls-files",
                    "--others",
                    "--exclude-standard",
                    "-z",
                ),
                "Untracked-file inspection",
            )

            untracked_files = self._decode_nul_paths(
                untracked_payload
            )

            if untracked_files:
                return self._invalid(
                    "Repair candidate contains untracked files; "
                    "6C.3 permits modification of tracked Python "
                    "targets only.",
                    changed_files=tuple(
                        sorted(untracked_files)
                    ),
                )

            changed_payload = self._require_git_success(
                self._run_git(
                    root,
                    "diff",
                    "--name-only",
                    "--no-renames",
                    "-z",
                    "HEAD",
                    "--",
                ),
                "Candidate changed-file inspection",
            )

            changed_files = tuple(
                sorted(
                    set(
                        self._decode_nul_paths(
                            changed_payload
                        )
                    )
                )
            )

            if not changed_files:
                return self._invalid(
                    "Repair candidate contains no source changes."
                )

            approved_targets = set(
                decision.normalized_target_files
            )

            unexpected = tuple(
                path
                for path in changed_files
                if path not in approved_targets
            )

            if unexpected:
                return self._invalid(
                    "Repair candidate modified files outside the "
                    "approved target scope.",
                    changed_files=changed_files,
                )

            for relative_path in changed_files:
                candidate_path = (
                    root
                    / relative_path
                )

                if candidate_path.is_symlink():
                    return self._invalid(
                        "Repair candidate may not replace a target "
                        "with a symbolic link.",
                        changed_files=changed_files,
                    )

                if (
                    not candidate_path.exists()
                    or not candidate_path.is_file()
                ):
                    return self._invalid(
                        "Repair candidate may not delete or replace "
                        "an approved source target with a non-file.",
                        changed_files=changed_files,
                    )

                resolved_candidate = (
                    candidate_path.resolve()
                )

                if not self._path_is_within(
                    resolved_candidate,
                    root,
                ):
                    return self._invalid(
                        "Repair target escaped the isolated workspace.",
                        changed_files=changed_files,
                    )

                if (
                    not relative_path.startswith("app/")
                    or not relative_path.endswith(".py")
                ):
                    return self._invalid(
                        "Repair candidate contains an unsupported "
                        "source target.",
                        changed_files=changed_files,
                    )

                try:
                    file_size = candidate_path.stat().st_size
                except OSError as error:
                    return self._invalid(
                        f"Could not inspect candidate source size: "
                        f"{error}",
                        changed_files=changed_files,
                    )

                if file_size > self.max_file_bytes:
                    return self._invalid(
                        "Repair candidate source exceeds the bounded "
                        "validation size.",
                        changed_files=changed_files,
                    )

                try:
                    with tokenize.open(
                        candidate_path
                    ) as source_file:
                        source = source_file.read()

                    compile(
                        source,
                        str(candidate_path),
                        "exec",
                        dont_inherit=True,
                    )

                except (
                    OSError,
                    SyntaxError,
                    UnicodeError,
                    ValueError,
                ) as error:
                    return self._invalid(
                        "Repair candidate failed static Python "
                        f"compilation: {error}",
                        changed_files=changed_files,
                    )

            diff_payload = self._require_git_success(
                self._run_git(
                    root,
                    "diff",
                    "--no-ext-diff",
                    "--no-color",
                    "--unified=3",
                    "HEAD",
                    "--",
                    *changed_files,
                ),
                "Candidate diff collection",
            )

            diff = diff_payload.decode(
                "utf-8",
                errors="replace",
            )

            if not diff.strip():
                return self._invalid(
                    "Repair candidate changed-file evidence exists "
                    "but the textual diff is empty.",
                    changed_files=changed_files,
                )

            if len(diff) > self.max_diff_chars:
                return self._invalid(
                    "Repair candidate diff exceeds the bounded "
                    "evidence size.",
                    changed_files=changed_files,
                )

            return RepairValidationResult(
                valid=True,
                reason=(
                    "Repair candidate passed static scope, Git-state, "
                    "path, size, and Python compilation checks. "
                    "Candidate code has not been executed."
                ),
                changed_files=changed_files,
                diff=diff,
            )

        except (
            RepairWorkspaceError,
            UnicodeError,
        ) as error:
            return self._invalid(
                f"Repair validation failed closed: {error}"
            )
