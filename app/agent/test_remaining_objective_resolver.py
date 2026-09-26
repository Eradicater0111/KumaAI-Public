import unittest
from types import SimpleNamespace

from app.agent.remaining_objective_resolver import (
    RemainingObjectiveResolver,
    parse_remaining_objective_resolution,
)


def response_with(content):
    return SimpleNamespace(
        message=SimpleNamespace(
            content=content
        )
    )


class TestRemainingObjectiveResolver(unittest.TestCase):

    def test_parser_accepts_known_resolution(self):

        resolution, error = (
            parse_remaining_objective_resolution(
                (
                    '{"known":true,'
                    '"remaining_objective":"Finish validation.",'
                    '"reason":"Creation already occurred."}'
                ),
                evidence_used="STATE_VERIFIED",
            )
        )

        self.assertIsNone(error)
        self.assertTrue(resolution.known)

        self.assertEqual(
            resolution.remaining_objective,
            "Finish validation.",
        )

        self.assertEqual(
            resolution.evidence_used,
            "STATE_VERIFIED",
        )

    def test_parser_accepts_unknown_resolution(self):

        resolution, error = (
            parse_remaining_objective_resolution(
                (
                    '{"known":false,'
                    '"remaining_objective":"",'
                    '"reason":"Evidence is insufficient."}'
                ),
                evidence_used="STATE_VERIFIED",
            )
        )

        self.assertIsNone(error)
        self.assertFalse(resolution.known)

        self.assertEqual(
            resolution.remaining_objective,
            "",
        )

    def test_known_resolution_requires_objective(self):

        resolution, error = (
            parse_remaining_objective_resolution(
                (
                    '{"known":true,'
                    '"remaining_objective":"",'
                    '"reason":"Still unfinished."}'
                ),
                evidence_used="STATE_VERIFIED",
            )
        )

        self.assertIsNone(
            resolution
        )

        self.assertIn(
            "requires a remaining objective",
            error.lower(),
        )

    def test_unknown_resolution_rejects_objective(self):

        resolution, error = (
            parse_remaining_objective_resolution(
                (
                    '{"known":false,'
                    '"remaining_objective":"Do something.",'
                    '"reason":"Unknown."}'
                ),
                evidence_used="STATE_VERIFIED",
            )
        )

        self.assertIsNone(
            resolution
        )

        self.assertIn(
            "cannot contain",
            error.lower(),
        )

    def test_invalid_json_fails_closed(self):

        resolver = RemainingObjectiveResolver(
            model_call=lambda messages: (
                response_with(
                    "not json"
                )
            )
        )

        step = SimpleNamespace(
            objective="Configure the application.",
            success_criteria=[
                "Application is configured."
            ],
            verification_requirements=[
                "Verify configuration."
            ],
        )

        resolution = resolver.resolve(
            step=step,
            evidence="PARTIAL_VERIFIED",
            recovery_reason="Partial execution.",
        )

        self.assertFalse(
            resolution.known
        )

        self.assertEqual(
            resolution.remaining_objective,
            "",
        )

    def test_resolver_uses_authoritative_evidence(self):

        captured = []

        def model_call(messages):

            captured.extend(
                messages
            )

            return response_with(
                (
                    '{"known":true,'
                    '"remaining_objective":'
                    '"Verify the remaining configuration.",'
                    '"reason":'
                    '"The configuration already exists."}'
                )
            )

        resolver = RemainingObjectiveResolver(
            model_call=model_call
        )

        step = SimpleNamespace(
            objective="Configure the application.",
            success_criteria=[
                "Application is configured."
            ],
            verification_requirements=[
                "Verify configuration."
            ],
        )

        resolution = resolver.resolve(
            step=step,
            evidence="TRUSTED_PARTIAL_STATE",
            recovery_reason=(
                "Configuration may already exist."
            ),
        )

        self.assertTrue(
            resolution.known
        )

        self.assertEqual(
            resolution.evidence_used,
            "TRUSTED_PARTIAL_STATE",
        )

        rendered = "\n".join(
            message["content"]
            for message in captured
        )

        self.assertIn(
            "TRUSTED_PARTIAL_STATE",
            rendered,
        )

        self.assertIn(
            "Never return a completion status.",
            rendered,
        )


if __name__ == "__main__":
    unittest.main()
