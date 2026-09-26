from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import pytest

from app.agent.permissions import PermissionLevel
from app.agent.repair_execution_sandbox import (
    RepairExecutionResult,
    RepairExecutionSandbox,
)
from app.agent.repair_policy import (
    RepairPolicy,
    RepairProposal,
)
from app.agent.repair_validator import (
    RepairValidationResult,
    RepairValidator,
)
from app.agent.repair_workspace import (
    RepairWorkspace,
    RepairWorkspaceError,
)


class TestRepairExecutionSandbox(
    unittest.TestCase
):

    def setUp(self):
        self.temp_dir = (
            tempfile.TemporaryDirectory()
        )

        self.root = Path(
            self.temp_dir.name
        )

        self.repo = (
            self.root
            / "source"
        )

        self.repo.mkdir()

        self.git(
            "init",
            "--quiet",
            cwd=self.repo,
        )

        app_dir = (
            self.repo
            / "app"
        )

        agent_dir = (
            app_dir
            / "agent"
        )

        agent_dir.mkdir(
            parents=True
        )

        (
            app_dir
            / "__init__.py"
        ).write_text(
            "",
            encoding="utf-8",
        )

        (
            agent_dir
            / "__init__.py"
        ).write_text(
            "",
            encoding="utf-8",
        )

        (
            agent_dir
            / "sample.py"
        ).write_text(
            "VALUE = 1\n",
            encoding="utf-8",
        )

        (
            agent_dir
            / "other.py"
        ).write_text(
            "OTHER = 1\n",
            encoding="utf-8",
        )

        self.git(
            "add",
            ".",
            cwd=self.repo,
        )

        self.git(
            "-c",
            "user.name=KUMA Test",
            "-c",
            "user.email=kuma-test@example.invalid",
            "commit",
            "--quiet",
            "-m",
            "initial",
            cwd=self.repo,
        )

        proposal = RepairProposal(
            summary="Fix sample.",
            rationale=(
                "Observed deterministic failure."
            ),
            target_files=(
                "app/agent/sample.py",
            ),
            permission_level=(
                PermissionLevel.SAFE
            ),
        )

        self.decision = (
            RepairPolicy().evaluate(
                proposal
            )
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    @staticmethod
    def git(
        *args: str,
        cwd: Path,
        check: bool = True,
    ) -> subprocess.CompletedProcess:
        return subprocess.run(
            [
                "git",
                *args,
            ],
            cwd=str(
                cwd
            ),
            capture_output=True,
            text=True,
            check=check,
            shell=False,
        )

    @staticmethod
    def candidate_file(
        workspace: RepairWorkspace,
    ) -> Path:
        return (
            workspace.root
            / "app"
            / "agent"
            / "sample.py"
        )

    def prepare(
        self,
        workspace: RepairWorkspace,
        source: str,
    ) -> RepairValidationResult:
        self.candidate_file(
            workspace
        ).write_text(
            source,
            encoding="utf-8",
        )

        result = (
            RepairValidator().validate(
                workspace=workspace,
                decision=self.decision,
            )
        )

        self.assertTrue(
            result.valid,
            result.reason,
        )

        return result

    def execute(
        self,
        workspace: RepairWorkspace,
        validation: RepairValidationResult,
        *,
        sandbox: (
            RepairExecutionSandbox
            | None
        ) = None,
    ) -> RepairExecutionResult:
        runner = (
            sandbox
            or RepairExecutionSandbox()
        )

        return runner.execute(
            workspace=workspace,
            decision=self.decision,
            validation=validation,
            relative_path=(
                "app/agent/sample.py"
            ),
        )

    def test_containment_failure_is_not_execution_success(self):
        with RepairWorkspace(self.repo) as workspace:
            validation = self.prepare(workspace, 'VALUE = 2\n')
            with patch.object(RepairExecutionSandbox, '_run_contained_python',
                              side_effect=RepairWorkspaceError('memory inspection unavailable')):
                result = self.execute(workspace, validation)
            self.assertFalse(result.executed)
            self.assertFalse(result.success)
            self.assertIn('Contained execution unavailable', result.reason)

    @pytest.mark.native_sandbox
    def test_validated_candidate_executes(
        self
    ):
        with RepairWorkspace(
            self.repo
        ) as workspace:
            validation = self.prepare(
                workspace,
                (
                    'print("CANDIDATE-OK")\n'
                    "VALUE = 2\n"
                ),
            )

            result = self.execute(
                workspace,
                validation,
            )

            self.assertTrue(
                result.executed,
                result.reason,
            )

            self.assertTrue(
                result.success,
                result.stderr,
            )

            self.assertEqual(
                result.returncode,
                0,
            )

            self.assertIn(
                "CANDIDATE-OK",
                result.stdout,
            )

            self.assertIn(
                "does not authorize",
                result.reason,
            )

    def test_invalid_validation_never_executes(
        self
    ):
        with RepairWorkspace(
            self.repo
        ) as workspace:
            invalid = (
                RepairValidationResult(
                    valid=False,
                    reason="invalid",
                )
            )

            result = self.execute(
                workspace,
                invalid,
            )

            self.assertFalse(
                result.executed
            )

            self.assertFalse(
                result.success
            )

    def test_stale_validation_never_executes(
        self
    ):
        with RepairWorkspace(
            self.repo
        ) as workspace:
            validation = self.prepare(
                workspace,
                (
                    'print("OLD")\n'
                    "VALUE = 2\n"
                ),
            )

            self.candidate_file(
                workspace
            ).write_text(
                (
                    'print("NEW")\n'
                    "VALUE = 3\n"
                ),
                encoding="utf-8",
            )

            result = self.execute(
                workspace,
                validation,
            )

            self.assertFalse(
                result.executed
            )

            self.assertIn(
                "stale",
                result.reason.lower(),
            )

    @pytest.mark.native_sandbox
    def test_live_source_read_is_blocked(
        self
    ):
        live_target = (
            self.repo
            / "app"
            / "agent"
            / "sample.py"
        ).resolve()

        source = f"""
from pathlib import Path

try:
    Path({str(live_target)!r}).read_text()
except PermissionError:
    print("LIVE-READ-BLOCKED")
else:
    raise SystemExit("LIVE SOURCE WAS READ")
"""

        with RepairWorkspace(
            self.repo
        ) as workspace:
            validation = self.prepare(
                workspace,
                source,
            )

            result = self.execute(
                workspace,
                validation,
            )

            self.assertTrue(
                result.success,
                result.stderr,
            )

            self.assertIn(
                "LIVE-READ-BLOCKED",
                result.stdout,
            )

    @pytest.mark.native_sandbox
    def test_candidate_write_is_blocked(
        self
    ):
        source = """
from pathlib import Path

target = Path(__file__).with_name(
    "candidate-write.txt"
)

try:
    target.write_text("NO")
except PermissionError:
    print("CANDIDATE-WRITE-BLOCKED")
else:
    raise SystemExit("CANDIDATE WAS WRITABLE")
"""

        with RepairWorkspace(
            self.repo
        ) as workspace:
            validation = self.prepare(
                workspace,
                source,
            )

            result = self.execute(
                workspace,
                validation,
            )

            self.assertTrue(
                result.success,
                result.stderr,
            )

            self.assertIn(
                "CANDIDATE-WRITE-BLOCKED",
                result.stdout,
            )

            self.assertFalse(
                (
                    workspace.root
                    / "app"
                    / "agent"
                    / "candidate-write.txt"
                ).exists()
            )

    @pytest.mark.native_sandbox
    def test_scratch_is_writable(
        self
    ):
        source = """
import os
from pathlib import Path

target = (
    Path(os.environ["HOME"])
    / "scratch-ok.txt"
)

target.write_text("ok")

print(
    "SCRATCH-WRITE-" + target.read_text()
)
"""

        with RepairWorkspace(
            self.repo
        ) as workspace:
            validation = self.prepare(
                workspace,
                source,
            )

            result = self.execute(
                workspace,
                validation,
            )

            self.assertTrue(
                result.success,
                result.stderr,
            )

            self.assertIn(
                "SCRATCH-WRITE-ok",
                result.stdout,
            )

    @pytest.mark.native_sandbox
    def test_environment_secret_is_removed(
        self
    ):
        source = """
import os

if os.environ.get(
    "KUMA_REPAIR_TEST_SECRET"
) is None:
    print("ENV-SECRET-BLOCKED")
else:
    raise SystemExit(
        "INHERITED SECRET VISIBLE"
    )
"""

        previous = os.environ.get(
            "KUMA_REPAIR_TEST_SECRET"
        )

        os.environ[
            "KUMA_REPAIR_TEST_SECRET"
        ] = "DO-NOT-INHERIT"

        try:
            with RepairWorkspace(
                self.repo
            ) as workspace:
                validation = self.prepare(
                    workspace,
                    source,
                )

                result = self.execute(
                    workspace,
                    validation,
                )

                self.assertTrue(
                    result.success,
                    result.stderr,
                )

                self.assertIn(
                    "ENV-SECRET-BLOCKED",
                    result.stdout,
                )

        finally:
            if previous is None:
                os.environ.pop(
                    "KUMA_REPAIR_TEST_SECRET",
                    None,
                )
            else:
                os.environ[
                    "KUMA_REPAIR_TEST_SECRET"
                ] = previous

    @pytest.mark.native_sandbox
    def test_network_is_blocked(
        self
    ):
        source = """
import socket

try:
    socket.create_connection(
        ("1.1.1.1", 53),
        timeout=1,
    )
except PermissionError:
    print("NETWORK-BLOCKED")
else:
    raise SystemExit(
        "NETWORK WAS AVAILABLE"
    )
"""

        with RepairWorkspace(
            self.repo
        ) as workspace:
            validation = self.prepare(
                workspace,
                source,
            )

            result = self.execute(
                workspace,
                validation,
            )

            self.assertTrue(
                result.success,
                result.stderr,
            )

            self.assertIn(
                "NETWORK-BLOCKED",
                result.stdout,
            )

    @pytest.mark.native_sandbox
    def test_subprocess_is_blocked(
        self
    ):
        source = """
import subprocess

try:
    subprocess.run(
        ["/bin/echo", "NO"],
        check=True,
    )
except PermissionError:
    print("SUBPROCESS-BLOCKED")
else:
    raise SystemExit(
        "SUBPROCESS WAS AVAILABLE"
    )
"""

        with RepairWorkspace(
            self.repo
        ) as workspace:
            validation = self.prepare(
                workspace,
                source,
            )

            result = self.execute(
                workspace,
                validation,
            )

            self.assertTrue(
                result.success,
                result.stderr,
            )

            self.assertIn(
                "SUBPROCESS-BLOCKED",
                result.stdout,
            )

    @pytest.mark.native_sandbox
    def test_fork_is_blocked(
        self
    ):
        source = """
import os

try:
    pid = os.fork()
except PermissionError:
    print("FORK-BLOCKED")
else:
    if pid == 0:
        os._exit(0)

    os.waitpid(
        pid,
        0,
    )

    raise SystemExit(
        "FORK WAS AVAILABLE"
    )
"""

        with RepairWorkspace(
            self.repo
        ) as workspace:
            validation = self.prepare(
                workspace,
                source,
            )

            result = self.execute(
                workspace,
                validation,
            )

            self.assertTrue(
                result.success,
                result.stderr,
            )

            self.assertIn(
                "FORK-BLOCKED",
                result.stdout,
            )

    @pytest.mark.native_sandbox
    def test_timeout_fails_closed(
        self
    ):
        source = """
while True:
    pass
"""

        with RepairWorkspace(
            self.repo
        ) as workspace:
            validation = self.prepare(
                workspace,
                source,
            )

            sandbox = (
                RepairExecutionSandbox(
                    wall_timeout_seconds=2,
                    cpu_timeout_seconds=1,
                )
            )

            result = self.execute(
                workspace,
                validation,
                sandbox=sandbox,
            )

            self.assertTrue(
                result.executed,
                result.reason,
            )

            self.assertFalse(
                result.success
            )

            self.assertTrue(
                result.timed_out
                or (
                    result.returncode
                    is not None
                    and result.returncode
                    != 0
                )
            )

    @pytest.mark.native_sandbox
    def test_memory_limit_fails_closed(
        self
    ):
        source = """
while True:
    pass
"""

        with RepairWorkspace(
            self.repo
        ) as workspace:
            validation = self.prepare(
                workspace,
                source,
            )

            sandbox = (
                RepairExecutionSandbox(
                    wall_timeout_seconds=5,
                    cpu_timeout_seconds=4,
                    max_resident_memory_bytes=1,
                )
            )

            result = self.execute(
                workspace,
                validation,
                sandbox=sandbox,
            )

            self.assertTrue(
                result.executed,
                result.reason,
            )

            self.assertFalse(
                result.success
            )

            self.assertTrue(
                result.memory_limit_exceeded
            )

    @pytest.mark.native_sandbox
    def test_output_limit_fails_closed(
        self
    ):
        source = """
while True:
    print(
        "X" * 4096,
        flush=True,
    )
"""

        with RepairWorkspace(
            self.repo
        ) as workspace:
            validation = self.prepare(
                workspace,
                source,
            )

            sandbox = (
                RepairExecutionSandbox(
                    wall_timeout_seconds=5,
                    cpu_timeout_seconds=4,
                    max_output_bytes=16000,
                )
            )

            result = self.execute(
                workspace,
                validation,
                sandbox=sandbox,
            )

            self.assertTrue(
                result.executed,
                result.reason,
            )

            self.assertFalse(
                result.success
            )

            self.assertTrue(
                result.output_limit_exceeded
            )

            self.assertLessEqual(
                len(
                    result.stdout.encode(
                        "utf-8"
                    )
                ),
                16000,
            )

    @pytest.mark.native_sandbox
    def test_main_checkout_unchanged(
        self
    ):
        source_file = (
            self.repo
            / "app"
            / "agent"
            / "sample.py"
        )

        original = (
            source_file.read_text(
                encoding="utf-8"
            )
        )

        with RepairWorkspace(
            self.repo
        ) as workspace:
            validation = self.prepare(
                workspace,
                (
                    'print("ISOLATED")\n'
                    "VALUE = 999\n"
                ),
            )

            result = self.execute(
                workspace,
                validation,
            )

            self.assertTrue(
                result.success,
                result.stderr,
            )

        self.assertEqual(
            source_file.read_text(
                encoding="utf-8"
            ),
            original,
        )


class TestRepairExecutionSandboxContracts(
    unittest.TestCase
):

    def test_invalid_limits_are_rejected(
        self
    ):
        for value in (
            0,
            -1,
            True,
            1.5,
            "5",
        ):
            with self.subTest(
                value=value
            ):
                with self.assertRaises(
                    ValueError
                ):
                    RepairExecutionSandbox(
                        max_output_bytes=value
                    )

    def test_cpu_limit_cannot_exceed_wall_limit(
        self
    ):
        with self.assertRaises(
            ValueError
        ):
            RepairExecutionSandbox(
                wall_timeout_seconds=1,
                cpu_timeout_seconds=2,
            )

    def test_result_is_immutable(
        self
    ):
        result = RepairExecutionResult(
            executed=False,
            success=False,
            reason="blocked",
        )

        with self.assertRaises(
            Exception
        ):
            result.success = True


if __name__ == "__main__":
    unittest.main()
