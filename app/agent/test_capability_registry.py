import unittest

from app.agent.capability_registry import (
    Capability,
    CapabilityRegistry,
    create_default_capability_registry,
)
from app.agent.mission_result import (
    MissionExecutionResult,
)

from app.agent.mission_runner import (
    MissionRunner,
)


class TestCapabilityRegistry(unittest.TestCase):

    def test_default_registry_contains_expected_capabilities(self):

        registry = (
            create_default_capability_registry()
        )

        expected = {
            "filesystem",
            "application_control",
            "system_inspection",
            "terminal",
            "screen_vision",
            "mouse_control",
            "keyboard_control",
            "screen_navigation",
            "memory",
        }

        self.assertTrue(
            expected.issubset(
                registry.names()
            )
        )

    def test_filesystem_maps_to_real_tools(self):

        registry = (
            create_default_capability_registry()
        )

        self.assertEqual(
            registry.tools_for(
                "filesystem"
            ),
            (
                "list_files",
                "open_file",
            ),
        )

    def test_screen_vision_maps_to_real_tools(self):

        registry = (
            create_default_capability_registry()
        )

        self.assertEqual(
            registry.tools_for(
                "screen_vision"
            ),
            (
                "screenshot_screen",
                "analyze_screen",
            ),
        )

    def test_unknown_capability_returns_none(self):

        registry = (
            create_default_capability_registry()
        )

        self.assertIsNone(
            registry.get(
                "does_not_exist"
            )
        )

    def test_unknown_capability_has_no_tools(self):

        registry = (
            create_default_capability_registry()
        )

        self.assertEqual(
            registry.tools_for(
                "does_not_exist"
            ),
            (),
        )

    def test_duplicate_capability_is_rejected(self):

        registry = CapabilityRegistry()

        capability = Capability(
            name="filesystem",
            description="Read files.",
            tools=("open_file",),
        )

        registry.register(
            capability
        )

        with self.assertRaises(
            ValueError
        ):
            registry.register(
                capability
            )

    def test_empty_capability_name_is_rejected(self):

        registry = CapabilityRegistry()

        with self.assertRaises(
            ValueError
        ):
            registry.register(
                Capability(
                    name="",
                    description="Invalid.",
                    tools=(),
                )
            )

    def test_tool_maps_back_to_capability(self):

        registry = (
            create_default_capability_registry()
        )

        self.assertEqual(
            registry.capability_for_tool(
                "open_file"
            ),
            "filesystem",
        )

        self.assertEqual(
            registry.capability_for_tool(
                "analyze_screen"
            ),
            "screen_vision",
        )

    def test_unknown_tool_has_no_capability(self):

        registry = (
            create_default_capability_registry()
        )

        self.assertIsNone(
            registry.capability_for_tool(
                "does_not_exist"
            )
        )

    def test_planner_description_contains_tools(self):

        registry = (
            create_default_capability_registry()
        )

        description = (
            registry.describe()
        )

        self.assertIn(
            "filesystem",
            description,
        )

        self.assertIn(
            "list_files",
            description,
        )

        self.assertIn(
            "screen_vision",
            description,
        )

        self.assertIn(
            "analyze_screen",
            description,
        )


if __name__ == "__main__":
    unittest.main()