from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
import selectors
import signal
import subprocess
import sys
import tempfile
import time

from app.agent.repair_policy import RepairDecision
from app.agent.repair_validator import (
    RepairValidationResult,
    RepairValidator,
)
from app.agent.repair_workspace import (
    RepairWorkspace,
    RepairWorkspaceError,
)


@dataclass(frozen=True)
class RepairExecutionResult:
    """
    Immutable evidence from contained candidate execution.

    success=True means only that candidate code ran successfully
    inside the execution sandbox and the candidate evidence remained
    unchanged afterwards.

    It never authorizes modification of KUMA's main checkout.
    """

    executed: bool
    success: bool
    reason: str
    relative_path: str = ""
    returncode: int | None = None
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    output_limit_exceeded: bool = False
    memory_limit_exceeded: bool = False


class RepairExecutionSandbox:
    """
    Execute one statically validated changed Python module inside
    KUMA's 6C.4 containment boundary.

    Security properties:
    - active isolated RepairWorkspace required
    - successful current RepairValidationResult required
    - validation is repeated immediately before execution
    - candidate workspace is read-only
    - disposable scratch directory is writable
    - inherited environment is stripped
    - network access is denied
    - process fork is denied
    - arbitrary subprocess execution is denied
    - only the trusted framework Python executable may exec
    - candidate output is bounded
    - wall-clock execution is bounded
    - candidate static evidence is verified again afterwards
    - no commit, merge, push, apply-back, or main-checkout mutation

    This implementation is intentionally macOS-specific and fails
    closed when the required host containment facilities are absent.
    """

    _SANDBOX_EXEC = Path(
        "/usr/bin/sandbox-exec"
    )

    _PS = Path(
        "/bin/ps"
    )

    _MODULE_COMPONENT = re.compile(
        r"^[A-Za-z_][A-Za-z0-9_]*$"
    )

    _RESOURCE_HARNESS = r"""
import resource
import sys

cpu_seconds = int(sys.argv[1])
max_open_files = int(sys.argv[2])
max_file_bytes = int(sys.argv[3])
candidate_root = sys.argv[4]
payload_count = int(sys.argv[5])

if payload_count < 0:
    raise RuntimeError(
        "Contained payload count is invalid."
    )

payload_start = 6
payload_end = (
    payload_start
    + payload_count
)

payload = sys.argv[
    payload_start:payload_end
]

if len(payload) != payload_count:
    raise RuntimeError(
        "Contained payload is incomplete."
    )

extra_paths = sys.argv[
    payload_end:
]


def lower_soft_limit(
    limit,
    target,
):
    current_soft, current_hard = (
        resource.getrlimit(
            limit
        )
    )

    if (
        current_hard
        != resource.RLIM_INFINITY
        and target > current_hard
    ):
        raise RuntimeError(
            "Requested resource limit exceeds "
            "the host hard limit."
        )

    if (
        current_soft
        != resource.RLIM_INFINITY
    ):
        target = min(
            target,
            current_soft,
        )

    resource.setrlimit(
        limit,
        (
            target,
            current_hard,
        ),
    )


lower_soft_limit(
    resource.RLIMIT_CPU,
    cpu_seconds,
)

lower_soft_limit(
    resource.RLIMIT_NOFILE,
    max_open_files,
)

lower_soft_limit(
    resource.RLIMIT_FSIZE,
    max_file_bytes,
)

if hasattr(
    resource,
    "RLIMIT_CORE",
):
    resource.setrlimit(
        resource.RLIMIT_CORE,
        (
            0,
            0,
        ),
    )

sys.path.insert(
    0,
    candidate_root,
)

for path in reversed(
    extra_paths
):
    if path not in sys.path:
        sys.path.insert(
            1,
            path,
        )
"""

    _MODULE_HARNESS = r"""
import runpy

if len(payload) != 1:
    raise RuntimeError(
        "Contained module execution requires "
        "exactly one module."
    )

module_name = payload[0]

sys.argv = [
    module_name,
]

runpy.run_module(
    module_name,
    run_name="__main__",
    alter_sys=True,
)
"""

    def __init__(
        self,
        *,
        wall_timeout_seconds: int = 10,
        cpu_timeout_seconds: int = 5,
        max_resident_memory_bytes: int = 2_000_000_000,
        max_output_bytes: int = 256_000,
        max_open_files: int = 128,
        max_scratch_file_bytes: int = 10_000_000,
    ):
        values = (
            (
                "wall_timeout_seconds",
                wall_timeout_seconds,
            ),
            (
                "cpu_timeout_seconds",
                cpu_timeout_seconds,
            ),
            (
                "max_resident_memory_bytes",
                max_resident_memory_bytes,
            ),
            (
                "max_output_bytes",
                max_output_bytes,
            ),
            (
                "max_open_files",
                max_open_files,
            ),

            (
                "max_scratch_file_bytes",
                max_scratch_file_bytes,
            ),
        )

        for name, value in values:
            if (
                type(value) is not int
                or value < 1
            ):
                raise ValueError(
                    f"{name} must be a positive integer."
                )

        if (
            cpu_timeout_seconds
            > wall_timeout_seconds
        ):
            raise ValueError(
                "cpu_timeout_seconds may not exceed "
                "wall_timeout_seconds."
            )

        self.wall_timeout_seconds = (
            wall_timeout_seconds
        )
        self.cpu_timeout_seconds = (
            cpu_timeout_seconds
        )
        self.max_resident_memory_bytes = (
            max_resident_memory_bytes
        )
        self.max_output_bytes = (
            max_output_bytes
        )
        self.max_open_files = (
            max_open_files
        )

        self.max_scratch_file_bytes = (
            max_scratch_file_bytes
        )

    @staticmethod
    def _reject(
        reason: str,
        *,
        relative_path: str = "",
    ) -> RepairExecutionResult:
        return RepairExecutionResult(
            executed=False,
            success=False,
            reason=reason,
            relative_path=relative_path,
        )

    @staticmethod
    def _path_is_within(
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
    def _profile_path(
        path: Path,
    ) -> str:
        value = str(
            path.resolve()
        )

        if any(
            character in value
            for character in (
                "\0",
                "\n",
                "\r",
            )
        ):
            raise RepairWorkspaceError(
                "Sandbox path contains unsupported "
                "control characters."
            )

        return (
            value
            .replace(
                "\\",
                "\\\\",
            )
            .replace(
                '"',
                '\\"',
            )
        )

    @classmethod
    def _module_name(
        cls,
        relative_path: str,
    ) -> str | None:
        if (
            type(relative_path) is not str
            or not relative_path
            or not relative_path.startswith(
                "app/"
            )
            or not relative_path.endswith(
                ".py"
            )
        ):
            return None

        parts = relative_path.split(
            "/"
        )

        if any(
            part in {
                "",
                ".",
                "..",
            }
            for part in parts
        ):
            return None

        filename = parts[-1]

        if filename == "__init__.py":
            module_parts = parts[:-1]
        else:
            stem = filename[:-3]

            module_parts = [
                *parts[:-1],
                stem,
            ]

        if not module_parts:
            return None

        if any(
            not cls._MODULE_COMPONENT.fullmatch(
                part
            )
            for part in module_parts
        ):
            return None

        return ".".join(
            module_parts
        )

    @staticmethod
    def _trusted_python() -> tuple[
        Path,
        Path,
    ]:
        if sys.platform != "darwin":
            raise RepairWorkspaceError(
                "Contained repair execution currently "
                "requires macOS."
            )

        python_prefix = Path(
            sys.base_prefix
        ).expanduser().resolve()

        python_app = (
            python_prefix
            / "Resources"
            / "Python.app"
            / "Contents"
            / "MacOS"
            / "Python"
        ).resolve()

        if (
            not python_app.is_file()
            or not os.access(
                python_app,
                os.X_OK,
            )
        ):
            raise RepairWorkspaceError(
                "Trusted macOS framework Python "
                "runtime is unavailable."
            )

        return (
            python_app,
            python_prefix,
        )

    @staticmethod
    def _site_package_roots() -> tuple[
        Path,
        ...,
    ]:
        roots: list[Path] = []

        for raw_path in sys.path:
            if (
                type(raw_path) is not str
                or not raw_path
            ):
                continue

            if (
                "site-packages"
                not in raw_path
                and "dist-packages"
                not in raw_path
            ):
                continue

            path = Path(
                raw_path
            ).expanduser().resolve()

            if (
                path.is_dir()
                and path not in roots
            ):
                roots.append(
                    path
                )

        return tuple(
            roots
        )

    def _host_support(
        self,
    ) -> tuple[
        Path,
        Path,
        Path,
        tuple[Path, ...],
    ]:
        sandbox_exec = (
            self._SANDBOX_EXEC.resolve()
        )

        if (
            sys.platform != "darwin"
            or not sandbox_exec.is_file()
            or not os.access(
                sandbox_exec,
                os.X_OK,
            )
        ):
            raise RepairWorkspaceError(
                "macOS sandbox-exec is unavailable; "
                "candidate execution fails closed."
            )

        ps = self._PS.resolve()

        if (
            not ps.is_file()
            or not os.access(
                ps,
                os.X_OK,
            )
        ):
            raise RepairWorkspaceError(
                "macOS process inspection is unavailable; "
                "memory containment fails closed."
            )

        (
            python_app,
            python_prefix,
        ) = self._trusted_python()

        return (
            sandbox_exec,
            python_app,
            python_prefix,
            self._site_package_roots(),
        )

    @staticmethod
    def _validation_matches(
        expected: RepairValidationResult,
        current: RepairValidationResult,
    ) -> bool:
        return (
            expected.valid is True
            and current.valid is True
            and (
                expected.changed_files
                == current.changed_files
            )
            and (
                expected.diff
                == current.diff
            )
        )

    def _validate_contracts(
        self,
        *,
        workspace: RepairWorkspace,
        decision: RepairDecision,
        validation: RepairValidationResult,
        relative_path: str,
    ) -> RepairExecutionResult | None:
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
            validation,
            RepairValidationResult,
        ):
            return self._reject(
                "Repair validation contract is invalid."
            )

        if (
            not decision
            .eligible_for_isolated_evaluation
        ):
            return self._reject(
                "Repair decision does not authorize "
                "isolated candidate evaluation."
            )

        if (
            decision
            .automatic_main_checkout_apply
        ):
            return self._reject(
                "Repair decision illegally claims "
                "automatic main-checkout authority."
            )

        if validation.valid is not True:
            return self._reject(
                "Candidate code may execute only after "
                "successful static validation."
            )

        if (
            type(validation.changed_files)
            is not tuple
            or not validation.changed_files
        ):
            return self._reject(
                "Static validation contains no immutable "
                "changed-file evidence."
            )

        if (
            type(validation.diff) is not str
            or not validation.diff.strip()
        ):
            return self._reject(
                "Static validation contains no candidate "
                "diff evidence."
            )

        if (
            type(relative_path) is not str
            or relative_path
            not in validation.changed_files
        ):
            return self._reject(
                "Execution target is not one of the "
                "statically validated changed files.",
                relative_path=(
                    relative_path
                    if type(relative_path) is str
                    else ""
                ),
            )

        return None

    def _build_profile(
        self,
        *,
        python_app: Path,
        python_prefix: Path,
        candidate_root: Path,
        scratch_root: Path,
        site_package_roots: tuple[
            Path,
            ...,
        ],
    ) -> str:
        read_paths = [
            python_prefix,
            candidate_root,
            scratch_root,
            Path(
                "/System/Library"
            ),
            Path(
                "/usr/lib"
            ),
            *site_package_roots,
        ]

        unique_paths: list[
            Path
        ] = []

        for path in read_paths:
            resolved = path.resolve()

            if (
                resolved
                not in unique_paths
            ):
                unique_paths.append(
                    resolved
                )

        read_rules = "\n".join(
            (
                '    (subpath "'
                + self._profile_path(
                    path
                )
                + '")'
            )
            for path in unique_paths
        )

        return (
            "(version 1)\n"
            "(deny default)\n"
            "(allow process-exec\n"
            '    (literal "'
            + self._profile_path(
                python_app
            )
            + '"))\n'
            "(deny process-fork)\n"
            "(deny network*)\n"
            "(allow file-read*\n"
            '    (literal "/")\n'
            + read_rules
            + ")\n"
            "(allow file-write*\n"
            '    (subpath "'
            + self._profile_path(
                scratch_root
            )
            + '"))\n'
        )

    @staticmethod
    def _kill_group(
        process: subprocess.Popen,
    ) -> None:
        if (
            process.poll()
            is not None
        ):
            return

        try:
            os.killpg(
                process.pid,
                signal.SIGKILL,
            )
        except ProcessLookupError:
            return
        except OSError:
            try:
                process.kill()
            except OSError:
                pass

    def _resident_memory_bytes(
        self,
        process: subprocess.Popen,
    ) -> int | None:
        if process.poll() is not None:
            return None

        try:
            result = subprocess.run(
                [
                    str(
                        self._PS
                    ),
                    "-o",
                    "rss=",
                    "-p",
                    str(
                        process.pid
                    ),
                ],
                capture_output=True,
                text=True,
                timeout=1,
                check=False,
                shell=False,
            )
        except (
            OSError,
            subprocess.TimeoutExpired,
        ) as error:
            raise RepairWorkspaceError(
                "Could not inspect contained process "
                f"memory safely: {error}"
            ) from error

        if result.returncode != 0:
            if process.poll() is not None:
                return None

            raise RepairWorkspaceError(
                "Contained process memory inspection "
                "failed closed."
            )

        payload = (
            result.stdout
            or ""
        ).strip()

        if not payload:
            if process.poll() is not None:
                return None

            raise RepairWorkspaceError(
                "Contained process memory inspection "
                "returned no evidence."
            )

        token = payload.split()[0]

        try:
            rss_kib = int(
                token
            )
        except ValueError as error:
            raise RepairWorkspaceError(
                "Contained process memory evidence "
                "was malformed."
            ) from error

        if rss_kib < 0:
            raise RepairWorkspaceError(
                "Contained process memory evidence "
                "was invalid."
            )

        return (
            rss_kib
            * 1024
        )

    def _collect_output(
        self,
        process: subprocess.Popen,
    ) -> tuple[
        bytes,
        bytes,
        bool,
        bool,
        bool,
    ]:
        if (
            process.stdout is None
            or process.stderr is None
        ):
            raise RepairWorkspaceError(
                "Contained process output pipes "
                "are unavailable."
            )

        selector = (
            selectors.DefaultSelector()
        )

        for stream in (
            process.stdout,
            process.stderr,
        ):
            os.set_blocking(
                stream.fileno(),
                False,
            )

            selector.register(
                stream,
                selectors.EVENT_READ,
            )

        stdout = bytearray()
        stderr = bytearray()

        timed_out = False
        output_limit_exceeded = False
        memory_limit_exceeded = False

        deadline = (
            time.monotonic()
            + self.wall_timeout_seconds
        )

        try:
            while selector.get_map():
                resident_memory = (
                    self._resident_memory_bytes(
                        process
                    )
                )

                if (
                    resident_memory
                    is not None
                    and resident_memory
                    > self.max_resident_memory_bytes
                ):
                    memory_limit_exceeded = True

                    self._kill_group(
                        process
                    )
                    break

                remaining = (
                    deadline
                    - time.monotonic()
                )

                if remaining <= 0:
                    timed_out = True

                    self._kill_group(
                        process
                    )
                    break

                events = selector.select(
                    timeout=min(
                        0.1,
                        remaining,
                    )
                )

                if (
                    not events
                    and process.poll()
                    is not None
                ):
                    events = (
                        selector.select(
                            timeout=0
                        )
                    )

                    if not events:
                        break

                for key, _ in events:
                    stream = key.fileobj

                    try:
                        chunk = os.read(
                            stream.fileno(),
                            8192,
                        )
                    except BlockingIOError:
                        continue

                    if not chunk:
                        try:
                            selector.unregister(
                                stream
                            )
                        except Exception:
                            pass

                        continue

                    target = (
                        stdout
                        if stream
                        is process.stdout
                        else stderr
                    )

                    remaining_capacity = (
                        self.max_output_bytes
                        - len(target)
                    )

                    if remaining_capacity > 0:
                        target.extend(
                            chunk[
                                :remaining_capacity
                            ]
                        )

                    if (
                        len(chunk)
                        > remaining_capacity
                    ):
                        output_limit_exceeded = (
                            True
                        )

                        self._kill_group(
                            process
                        )
                        break

                if output_limit_exceeded:
                    break

        finally:
            selector.close()

        try:
            process.wait(
                timeout=2
            )
        except subprocess.TimeoutExpired:
            self._kill_group(
                process
            )

            try:
                process.wait(
                    timeout=2
                )
            except subprocess.TimeoutExpired:
                pass

        for stream in (
            process.stdout,
            process.stderr,
        ):
            try:
                stream.close()
            except OSError:
                pass

        return (
            bytes(
                stdout
            ),
            bytes(
                stderr
            ),
            timed_out,
            output_limit_exceeded,
            memory_limit_exceeded,
        )

    def _run_contained_python(
        self,
        *,
        candidate_root: Path,
        harness_body: str,
        payload_args: tuple[str, ...],
    ) -> tuple[
        int | None,
        str,
        str,
        bool,
        bool,
        bool,
    ]:
        """
        Run one trusted KUMA-owned Python harness inside the same
        containment primitive used by 6C.4.

        harness_body is trusted application code, never model output
        or candidate-controlled text.
        """

        if (
            type(harness_body) is not str
            or not harness_body.strip()
        ):
            raise RepairWorkspaceError(
                "Contained Python harness is invalid."
            )

        if type(payload_args) is not tuple:
            raise RepairWorkspaceError(
                "Contained Python payload must be immutable."
            )

        if any(
            type(argument) is not str
            for argument in payload_args
        ):
            raise RepairWorkspaceError(
                "Contained Python payload contains "
                "an invalid argument."
            )

        root = (
            candidate_root
            .resolve()
        )

        if (
            not root.exists()
            or not root.is_dir()
        ):
            raise RepairWorkspaceError(
                "Contained candidate root is unavailable."
            )

        (
            sandbox_exec,
            python_app,
            python_prefix,
            site_package_roots,
        ) = self._host_support()

        harness = (
            self._RESOURCE_HARNESS
            + "\n"
            + harness_body
        )

        with tempfile.TemporaryDirectory(
            prefix="kuma-repair-exec-"
        ) as scratch_name:
            scratch_root = Path(
                scratch_name
            ).resolve()

            profile_path = (
                scratch_root
                / "profile.sb"
            )

            try:
                profile_path.write_text(
                    self._build_profile(
                        python_app=python_app,
                        python_prefix=(
                            python_prefix
                        ),
                        candidate_root=root,
                        scratch_root=(
                            scratch_root
                        ),
                        site_package_roots=(
                            site_package_roots
                        ),
                    ),
                    encoding="utf-8",
                )

            except OSError as error:
                raise RepairWorkspaceError(
                    "Could not create contained "
                    "execution profile: "
                    f"{error}"
                ) from error

            command = [
                str(
                    sandbox_exec
                ),
                "-f",
                str(
                    profile_path
                ),
                str(
                    python_app
                ),
                "-I",
                "-c",
                harness,
                str(
                    self.cpu_timeout_seconds
                ),
                str(
                    self.max_open_files
                ),
                str(
                    self.max_scratch_file_bytes
                ),
                str(
                    root
                ),
                str(
                    len(
                        payload_args
                    )
                ),
                *payload_args,
                *(
                    str(
                        path
                    )
                    for path
                    in site_package_roots
                ),
            ]

            environment = {
                "HOME": str(
                    scratch_root
                ),
                "TMPDIR": str(
                    scratch_root
                ),
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONNOUSERSITE": "1",
                "LANG": "C",
                "LC_ALL": "C",
            }

            try:
                process = subprocess.Popen(
                    command,
                    cwd=str(
                        root
                    ),
                    env=environment,
                    stdin=(
                        subprocess.DEVNULL
                    ),
                    stdout=(
                        subprocess.PIPE
                    ),
                    stderr=(
                        subprocess.PIPE
                    ),
                    shell=False,
                    start_new_session=True,
                )

            except OSError as error:
                raise RepairWorkspaceError(
                    "Contained candidate process "
                    "could not start: "
                    f"{error}"
                ) from error

            try:
                (
                    stdout_payload,
                    stderr_payload,
                    timed_out,
                    output_limit_exceeded,
                    memory_limit_exceeded,
                ) = self._collect_output(
                    process
                )

            except Exception:
                self._kill_group(
                    process
                )

                try:
                    process.wait(
                        timeout=2
                    )
                except subprocess.TimeoutExpired:
                    pass

                for stream in (
                    process.stdout,
                    process.stderr,
                ):
                    if stream is None:
                        continue

                    try:
                        stream.close()
                    except OSError:
                        pass

                raise

            stdout = (
                stdout_payload.decode(
                    "utf-8",
                    errors="replace",
                )
            )

            stderr = (
                stderr_payload.decode(
                    "utf-8",
                    errors="replace",
                )
            )

            return (
                process.returncode,
                stdout,
                stderr,
                timed_out,
                output_limit_exceeded,
                memory_limit_exceeded,
            )

    def execute(
        self,
        *,
        workspace: RepairWorkspace,
        decision: RepairDecision,
        validation: RepairValidationResult,
        relative_path: str,
    ) -> RepairExecutionResult:
        contract_failure = (
            self._validate_contracts(
                workspace=workspace,
                decision=decision,
                validation=validation,
                relative_path=relative_path,
            )
        )

        if contract_failure is not None:
            return contract_failure

        try:
            info = workspace.info
        except RepairWorkspaceError as error:
            return self._reject(
                "Repair workspace is not active: "
                f"{error}",
                relative_path=relative_path,
            )

        root = (
            info.workspace_root
            .resolve()
        )

        candidate_path = (
            root
            / relative_path
        )

        if (
            candidate_path.is_symlink()
            or not candidate_path.is_file()
        ):
            return self._reject(
                "Contained execution target is "
                "unavailable or unsafe.",
                relative_path=relative_path,
            )

        resolved_candidate = (
            candidate_path.resolve()
        )

        if not self._path_is_within(
            resolved_candidate,
            root,
        ):
            return self._reject(
                "Contained execution target escaped "
                "the isolated workspace.",
                relative_path=relative_path,
            )

        module_name = (
            self._module_name(
                relative_path
            )
        )

        if module_name is None:
            return self._reject(
                "Contained execution target cannot "
                "be mapped to a safe Python module.",
                relative_path=relative_path,
            )

        current_validation = (
            RepairValidator().validate(
                workspace=workspace,
                decision=decision,
            )
        )

        if not self._validation_matches(
            validation,
            current_validation,
        ):
            return self._reject(
                "Static validation evidence is stale "
                "or no longer matches the candidate.",
                relative_path=relative_path,
            )

        try:
            (
                returncode,
                stdout,
                stderr,
                timed_out,
                output_limit_exceeded,
                memory_limit_exceeded,
            ) = self._run_contained_python(
                candidate_root=root,
                harness_body=(
                    self._MODULE_HARNESS
                ),
                payload_args=(
                    module_name,
                ),
            )

        except RepairWorkspaceError as error:
            return self._reject(
                "Contained execution unavailable: "
                f"{error}",
                relative_path=relative_path,
            )

        post_validation = (
            RepairValidator().validate(
                workspace=workspace,
                decision=decision,
            )
        )

        if not self._validation_matches(
            validation,
            post_validation,
        ):
            return RepairExecutionResult(
                executed=True,
                success=False,
                reason=(
                    "Candidate workspace evidence "
                    "changed during contained "
                    "execution; execution fails closed."
                ),
                relative_path=relative_path,
                returncode=returncode,
                stdout=stdout,
                stderr=stderr,
                timed_out=timed_out,
                output_limit_exceeded=(
                    output_limit_exceeded
                ),
                memory_limit_exceeded=(
                    memory_limit_exceeded
                ),
            )

        if memory_limit_exceeded:
            return RepairExecutionResult(
                executed=True,
                success=False,
                reason=(
                    "Contained candidate execution "
                    "exceeded the resident-memory limit."
                ),
                relative_path=relative_path,
                returncode=returncode,
                stdout=stdout,
                stderr=stderr,
                memory_limit_exceeded=True,
            )

        if timed_out:
            return RepairExecutionResult(
                executed=True,
                success=False,
                reason=(
                    "Contained candidate execution "
                    "exceeded the wall-clock limit."
                ),
                relative_path=relative_path,
                returncode=returncode,
                stdout=stdout,
                stderr=stderr,
                timed_out=True,
            )

        if output_limit_exceeded:
            return RepairExecutionResult(
                executed=True,
                success=False,
                reason=(
                    "Contained candidate execution "
                    "exceeded the output limit."
                ),
                relative_path=relative_path,
                returncode=returncode,
                stdout=stdout,
                stderr=stderr,
                output_limit_exceeded=True,
            )

        if returncode != 0:
            return RepairExecutionResult(
                executed=True,
                success=False,
                reason=(
                    "Contained candidate execution "
                    "exited unsuccessfully."
                ),
                relative_path=relative_path,
                returncode=returncode,
                stdout=stdout,
                stderr=stderr,
            )

        return RepairExecutionResult(
            executed=True,
            success=True,
            reason=(
                "Candidate code completed inside the "
                "isolated execution sandbox and static "
                "evidence remained unchanged. This "
                "does not authorize main-checkout "
                "application."
            ),
            relative_path=relative_path,
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
        )
