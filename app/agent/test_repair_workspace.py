from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile
import unittest

from app.agent.repair_workspace import (
    RepairWorkspace,
    RepairWorkspaceError,
)


class TestRepairWorkspace(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.repo = self.root / "source"

        self.repo.mkdir()

        self.git(
            "init",
            "--quiet",
            cwd=self.repo,
        )

        tracked = self.repo / "app" / "agent"
        tracked.mkdir(parents=True)

        (tracked / "sample.py").write_text(
            "VALUE = 1\n"
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

    def tearDown(self):
        self.temp_dir.cleanup()

    @staticmethod
    def git(
        *args: str,
        cwd: Path,
    ) -> subprocess.CompletedProcess:
        return subprocess.run(
            [
                "git",
                *args,
            ],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=True,
            shell=False,
        )

    def head(self, repo: Path) -> str:
        return self.git(
            "rev-parse",
            "HEAD",
            cwd=repo,
        ).stdout.strip()

    def test_nonexistent_source_is_rejected(self):
        workspace = RepairWorkspace(
            self.root / "missing"
        )

        with self.assertRaises(RepairWorkspaceError):
            workspace.create()

    def test_source_file_is_rejected(self):
        source_file = self.root / "not-a-repo"
        source_file.write_text("x")

        workspace = RepairWorkspace(
            source_file
        )

        with self.assertRaises(RepairWorkspaceError):
            workspace.create()

    def test_non_git_directory_is_rejected(self):
        directory = self.root / "plain"
        directory.mkdir()

        workspace = RepairWorkspace(
            directory
        )

        with self.assertRaises(RepairWorkspaceError):
            workspace.create()

    def test_nested_repo_path_is_rejected(self):
        workspace = RepairWorkspace(
            self.repo / "app"
        )

        with self.assertRaises(RepairWorkspaceError):
            workspace.create()

    def test_dirty_tracked_source_is_rejected(self):
        (
            self.repo
            / "app"
            / "agent"
            / "sample.py"
        ).write_text(
            "VALUE = 2\n"
        )

        workspace = RepairWorkspace(
            self.repo
        )

        with self.assertRaises(RepairWorkspaceError):
            workspace.create()

    def test_untracked_source_is_rejected(self):
        (
            self.repo
            / "untracked.txt"
        ).write_text(
            "not committed"
        )

        workspace = RepairWorkspace(
            self.repo
        )

        with self.assertRaises(RepairWorkspaceError):
            workspace.create()

    def test_workspace_matches_exact_source_head(self):
        source_head = self.head(
            self.repo
        )

        with RepairWorkspace(
            self.repo
        ) as workspace:

            self.assertEqual(
                workspace.source_head,
                source_head,
            )

            self.assertEqual(
                self.head(workspace.root),
                source_head,
            )

    def test_workspace_is_detached(self):
        with RepairWorkspace(
            self.repo
        ) as workspace:

            result = subprocess.run(
                [
                    "git",
                    "-C",
                    str(workspace.root),
                    "symbolic-ref",
                    "-q",
                    "HEAD",
                ],
                capture_output=True,
                text=True,
                check=False,
                shell=False,
            )

            self.assertEqual(
                result.returncode,
                1,
            )

    def test_workspace_root_is_outside_source_checkout(self):
        with RepairWorkspace(
            self.repo
        ) as workspace:

            self.assertNotEqual(
                workspace.root,
                self.repo.resolve(),
            )

            self.assertNotIn(
                self.repo.resolve(),
                workspace.root.parents,
            )

    def test_candidate_change_does_not_modify_source(self):
        source_file = (
            self.repo
            / "app"
            / "agent"
            / "sample.py"
        )

        with RepairWorkspace(
            self.repo
        ) as workspace:

            candidate_file = (
                workspace.root
                / "app"
                / "agent"
                / "sample.py"
            )

            candidate_file.write_text(
                "VALUE = 999\n"
            )

            self.assertEqual(
                source_file.read_text(),
                "VALUE = 1\n",
            )

            self.assertEqual(
                candidate_file.read_text(),
                "VALUE = 999\n",
            )

    def test_git_metadata_is_independent_directory(self):
        with RepairWorkspace(
            self.repo
        ) as workspace:

            source_git = (
                self.repo
                / ".git"
            )

            candidate_git = (
                workspace.root
                / ".git"
            )

            self.assertTrue(
                source_git.is_dir()
            )

            self.assertTrue(
                candidate_git.is_dir()
            )

            self.assertNotEqual(
                source_git.resolve(),
                candidate_git.resolve(),
            )

            alternates = (
                candidate_git
                / "objects"
                / "info"
                / "alternates"
            )

            self.assertFalse(
                alternates.exists()
            )

    def test_cleanup_removes_candidate_workspace(self):
        workspace = RepairWorkspace(
            self.repo
        )

        info = workspace.create()
        candidate_root = info.workspace_root

        self.assertTrue(
            candidate_root.exists()
        )

        workspace.cleanup()

        self.assertFalse(
            candidate_root.exists()
        )

    def test_cleanup_is_idempotent(self):
        workspace = RepairWorkspace(
            self.repo
        )

        workspace.create()
        workspace.cleanup()
        workspace.cleanup()

    def test_create_twice_is_rejected(self):
        workspace = RepairWorkspace(
            self.repo
        )

        try:
            workspace.create()

            with self.assertRaises(
                RepairWorkspaceError
            ):
                workspace.create()

        finally:
            workspace.cleanup()

    def test_context_manager_cleans_up_after_exception(self):
        candidate_root = None

        with self.assertRaises(RuntimeError):

            with RepairWorkspace(
                self.repo
            ) as workspace:

                candidate_root = (
                    workspace.root
                )

                raise RuntimeError(
                    "simulated repair failure"
                )

        self.assertIsNotNone(
            candidate_root
        )

        self.assertFalse(
            candidate_root.exists()
        )

    def test_invalid_timeout_is_rejected(self):
        for value in (
            0,
            -1,
            True,
            1.5,
        ):
            with self.subTest(value=value):
                with self.assertRaises(
                    ValueError
                ):
                    RepairWorkspace(
                        self.repo,
                        git_timeout_seconds=value,
                    )


if __name__ == "__main__":
    unittest.main()
