"""Read-only selector-aware native macOS target evidence for KUMA 8D2.

This provider exists specifically for native focus/target correlation.

It reads only semantic and eligibility attributes required by the exact
StructuredUITargetSelector. Irrelevant optional AX metadata is never queried.

Selector-required evidence remains strict:
hard native attribute-read failures are never downgraded into missing data.

The provider performs no AX action, setter, keyboard action, permission
decision, target authorization, or physical execution.
"""

from __future__ import annotations

import app.ui_observation.target_resolution as target_resolution
from app.ui_observation.focus_macos import (
    MacOSFocusProvider,
)
from app.ui_observation.target_resolution import (
    StructuredUITargetSelector,
)


class MacOSFocusTargetProvider(
    MacOSFocusProvider
):
    """Retain native AX identity while reading selector-relevant evidence."""

    @staticmethod
    def _semantic_state(
        *,
        selector,
        role,
        subrole,
        title,
        description,
    ):
        states = []

        if selector.role is not None:
            if role is None:
                states.append(
                    None
                )
            else:
                states.append(
                    role
                    == selector.role
                )

        if selector.subrole is not None:
            if subrole is None:
                states.append(
                    None
                )
            else:
                states.append(
                    subrole
                    == selector.subrole
                )

        if selector.text is not None:
            wanted = (
                target_resolution
                ._normalized_text(
                    selector.text
                )
            )

            if type(title) is str:
                states.append(
                    target_resolution
                    ._normalized_text(
                        title
                    )
                    == wanted
                )

            elif type(description) is str:
                states.append(
                    target_resolution
                    ._normalized_text(
                        description
                    )
                    == wanted
                )

            else:
                states.append(
                    False
                )

        if any(
            state is False
            for state in states
        ):
            return False

        if any(
            state is None
            for state in states
        ):
            return None

        return True

    def read_target_node(
        self,
        element,
        selector,
    ):
        """Read only evidence required by one exact semantic selector.

        A known semantic mismatch short-circuits later eligibility reads.

        Unsupported/no-value attributes remain ``None`` through the inherited
        strict optional-attribute helper. Other native AX failures raise.

        Focused/selected state is deliberately never queried.
        """

        if (
            type(selector)
            is not StructuredUITargetSelector
        ):
            raise TypeError(
                "selector must be an exact "
                "StructuredUITargetSelector."
            )

        ax = self.ax

        result = {
            "role": None,
            "subrole": None,
            "title": None,
            "description": None,
            "enabled": None,
            "position_x": None,
            "position_y": None,
            "width": None,
            "height": None,
        }

        if selector.role is not None:
            result[
                "role"
            ] = self._text(
                self._copy_optional_attribute(
                    element,
                    ax.kAXRoleAttribute,
                )
            )

            if (
                result[
                    "role"
                ]
                is not None
                and result[
                    "role"
                ]
                != selector.role
            ):
                return result

        if selector.subrole is not None:
            result[
                "subrole"
            ] = self._text(
                self._copy_optional_attribute(
                    element,
                    ax.kAXSubroleAttribute,
                )
            )

            if (
                result[
                    "subrole"
                ]
                is not None
                and result[
                    "subrole"
                ]
                != selector.subrole
            ):
                return result

        if selector.text is not None:
            result[
                "title"
            ] = self._text(
                self._copy_optional_attribute(
                    element,
                    ax.kAXTitleAttribute,
                )
            )

            if (
                result[
                    "title"
                ]
                is None
            ):
                result[
                    "description"
                ] = self._text(
                    self._copy_optional_attribute(
                        element,
                        ax.kAXDescriptionAttribute,
                    )
                )

        semantic_state = (
            self._semantic_state(
                selector=selector,
                role=result[
                    "role"
                ],
                subrole=result[
                    "subrole"
                ],
                title=result[
                    "title"
                ],
                description=result[
                    "description"
                ],
            )
        )

        if semantic_state is not True:
            return result

        if selector.require_enabled:
            result[
                "enabled"
            ] = self._boolean(
                self._copy_optional_attribute(
                    element,
                    ax.kAXEnabledAttribute,
                )
            )

        if selector.require_positive_area:
            geometry = (
                self.read_geometry(
                    element
                )
            )

            if type(
                geometry
            ) is not dict:
                raise RuntimeError(
                    "Invalid native target geometry contract."
                )

            for name in (
                "position_x",
                "position_y",
                "width",
                "height",
            ):
                result[
                    name
                ] = geometry.get(
                    name
                )

        return result
