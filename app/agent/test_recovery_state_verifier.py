import tempfile
import unittest
from pathlib import Path

from app.agent.recovery_state_verifier import (
    RecoveryStateVerifier,
    StateVerificationResult,
)


class TestRecoveryStateVerifier(unittest.TestCase):

    def test_unknown_mutating_tool_is_conservative(self):
        verifier = RecoveryStateVerifier()

        result = verifier.verify(
            tool_name="delete_file",
            arguments={
                "path": "/tmp/example.txt",
            },
        )

        self.assertIsInstance(
            result,
            StateVerificationResult,
        )
        self.assertFalse(result.known)
        self.assertIsNone(result.state_changed)
        self.assertEqual(result.state, "unknown")

    def test_open_file_existing_target_is_present(self):
        verifier = RecoveryStateVerifier()

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "existing.txt"
            path.write_text("kuma")

            result = verifier.verify(
                tool_name="open_file",
                arguments={
                    "file_path": str(path),
                },
            )

            self.assertTrue(result.known)
            self.assertFalse(result.state_changed)
            self.assertEqual(result.state, "present")
            self.assertIn(
                str(path),
                result.evidence,
            )

    def test_open_file_missing_target_is_absent(self):
        verifier = RecoveryStateVerifier()

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "missing.txt"

            result = verifier.verify(
                tool_name="open_file",
                arguments={
                    "file_path": str(path),
                },
            )

            self.assertTrue(result.known)
            self.assertFalse(result.state_changed)
            self.assertEqual(result.state, "absent")

    def test_missing_path_argument_is_unknown(self):
        verifier = RecoveryStateVerifier()

        result = verifier.verify(
            tool_name="open_file",
            arguments={},
        )

        self.assertFalse(result.known)
        self.assertIsNone(result.state_changed)
        self.assertEqual(result.state, "unknown")

    def test_verification_does_not_modify_file(self):
        verifier = RecoveryStateVerifier()

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "protected.txt"
            path.write_text("do not modify")

            before = path.read_text()

            result = verifier.verify(
                tool_name="open_file",
                arguments={
                    "file_path": str(path),
                },
            )

            after = path.read_text()

            self.assertEqual(before, after)
            self.assertTrue(result.known)
            self.assertFalse(result.state_changed)
            self.assertEqual(result.state, "present")


if __name__ == "__main__":
    unittest.main()
