from __future__ import annotations

from dataclasses import dataclass, field

@dataclass(frozen=True)
class Capability:
    """
    Semantic capability available to KUMA's planner.

    A capability maps to one or more registered runtime tools.
    """

    name: str

    description: str

    tools: tuple[str, ...]

    platform: str = "macos"

    risk_level: str = "normal"

    tags: tuple[str, ...] = field(
        default_factory=tuple
    )


class CapabilityRegistry:
    """
    Canonical semantic registry for KUMA capabilities.

    This registry does not execute anything.
    It only describes what KUMA can do.
    """

    def __init__(
        self,
        capabilities: list[Capability] | None = None,
    ):
        self._capabilities = {}

        for capability in capabilities or []:
            self.register(capability)

    def register(
        self,
        capability: Capability,
    ) -> None:
        """
        Register a semantic capability.
        """

        if not capability.name.strip():
            raise ValueError(
                "Capability name cannot be empty."
            )

        if capability.name in self._capabilities:
            raise ValueError(
                f"Capability already registered: "
                f"{capability.name}"
            )

        self._capabilities[
            capability.name
        ] = capability

    def get(
        self,
        name: str,
    ) -> Capability | None:
        return self._capabilities.get(
            name
        )

    def names(self) -> set[str]:
        return set(
            self._capabilities.keys()
        )

    def all(self) -> list[Capability]:
        return list(
            self._capabilities.values()
        )

    def has(
        self,
        name: str,
    ) -> bool:
        return name in self._capabilities

    def tools_for(
        self,
        capability_name: str,
    ) -> tuple[str, ...]:
        capability = self.get(
            capability_name
        )

        if capability is None:
            return ()

        return capability.tools

    def describe(self) -> str:
        """
        Produce a compact planner-facing capability description.
        """

        lines = [
            "KUMA CAPABILITY REGISTRY",
            "",
        ]

        for capability in self.all():

            lines.append(
                f"- {capability.name}: "
                f"{capability.description}"
            )

            lines.append(
                f"  Tools: "
                f"{', '.join(capability.tools)}"
            )

            lines.append(
                f"  Platform: {capability.platform}"
            )

            lines.append(
                f"  Risk: {capability.risk_level}"
            )

        return "\n".join(lines)

    def capability_for_tool(
        self,
        tool_name: str,
    ) -> str | None:
        """
        Find the semantic capability that owns a runtime tool.
        """

        for capability in self._capabilities.values():

            if tool_name in capability.tools:
                return capability.name

        return None

    def capabilities_for_tools(
        self,
        tool_names: set[str],
    ) -> dict[str, str]:
        """
        Map runtime tools to their semantic capabilities.
        """

        result = {}

        for tool_name in tool_names:

            capability = self.capability_for_tool(
                tool_name
            )

            if capability is not None:
                result[tool_name] = capability

        return result


def create_default_capability_registry() -> CapabilityRegistry:
    """
    Build the canonical capabilities for the current macOS KUMA runtime.
    """

    capabilities = [

        Capability(
            name="filesystem",
            description=(
                "Inspect directories and read files."
            ),
            tools=(
                "list_files",
                "open_file",
            ),
            tags=(
                "files",
                "storage",
            ),
        ),

        Capability(
            name="application_control",
            description=(
                "Launch desktop applications."
            ),
            tools=(
                "open_app",
            ),
            tags=(
                "apps",
                "desktop",
            ),
        ),

        Capability(
            name="system_inspection",
            description=(
                "Inspect information about the computer."
            ),
            tools=(
                "inspect_system",
            ),
            tags=(
                "system",
                "diagnostics",
            ),
        ),

        Capability(
            name="terminal",
            description=(
                "Execute shell commands on the local computer."
            ),
            tools=(
                "execute_command",
            ),
            risk_level="high",
            tags=(
                "shell",
                "command",
            ),
        ),

        Capability(
            name="screen_vision",
            description=(
                "Capture and interpret the current screen."
            ),
            tools=(
                "screenshot_screen",
                "analyze_screen",
            ),
            tags=(
                "vision",
                "screen",
                "observation",
            ),
        ),

        Capability(
            name="mouse_control",
            description=(
                "Move, click, hold, and release the mouse."
            ),
            tools=(
                "move_mouse",
                "move_mouse_vision",
                "click",
                "click_vision",
                "hold_mouse",
                "hold_mouse_vision",
                "release_mouse",
            ),
            tags=(
                "mouse",
                "computer_control",
            ),
        ),

        Capability(
            name="keyboard_control",
            description=(
                "Type text and press keyboard keys."
            ),
            tools=(
                "type_text",
                "press_key",
            ),
            tags=(
                "keyboard",
                "computer_control",
            ),
        ),

        Capability(
            name="screen_navigation",
            description=(
                "Scroll through visible application content."
            ),
            tools=(
                "scroll",
            ),
            tags=(
                "scroll",
                "navigation",
            ),
        ),

        # =================================================
        # KUMA LOCATION-1 — LIVE ROAMING LOCATION
        # =================================================

        Capability(
            name="live_location",
            description=(
                "Retrieve the user's current approximate macOS "
                "location as sensitive read-only local-device evidence."
            ),
            tools=(
                "get_current_location",
            ),
            risk_level="sensitive",
            tags=(
                "location",
                "current_location",
                "roaming",
                "local_device",
                "sensitive",
                "read_only",
                "no_action_authority",
            ),
        ),

        Capability(
            name="internet_knowledge",
            description=(
                "Retrieve current public internet knowledge "
                "as read-only external untrusted evidence."
            ),
            tools=(
                "web_search",
                "fetch_webpage",
            ),
            tags=(
                "internet",
                "web",
                "research",
                "current_information",
                "read_only",
                "untrusted_evidence",
            ),
        ),

        Capability(
            name="memory",
            description=(
                "Store, recall, and forget long-term information."
            ),
            tools=(
                "remember",
                "recall",
                "forget",
            ),
            tags=(
                "memory",
                "context",
            ),
        ),
    ]

    return CapabilityRegistry(
        capabilities
    )