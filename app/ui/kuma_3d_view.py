from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import (
    QUrl,
    Qt,
)
from PySide6.QtGui import (
    QColor,
)
from PySide6.QtQuickWidgets import (
    QQuickWidget,
)


from app.ui.avatar_visual_mechanics import (
    AvatarVisualParameters,
)


class Kuma3DView(
    QQuickWidget
):
    """
    Real-time Qt Quick 3D renderer for KUMA Mini.

    Presentation only.

    It owns:
    - no agent
    - no runtime
    - no planner
    - no tool authority
    - no personality model

    It merely renders the visual state provided by
    KumaMiniBody / KumaBodyController.
    """

    def __init__(
        self,
        parent=None,
    ):
        super().__init__(
            parent
        )

        self.setResizeMode(
            QQuickWidget.SizeRootObjectToView
        )

        self.setClearColor(
            QColor(
                0,
                0,
                0,
                0,
            )
        )

        self.setAttribute(
            Qt.WA_TranslucentBackground,
            True,
        )

        # KumaMiniBody remains responsible for dragging,
        # right-click menus, and pointer interaction.
        self.setAttribute(
            Qt.WA_TransparentForMouseEvents,
            True,
        )

        # -------------------------------------------------
        # BODY R1 PRODUCTION RIG SELECTION
        # -------------------------------------------------
        #
        # Frozen Floating Body R1 is the normal production body.
        #
        # Optional presentation-only overrides:
        #
        #   KUMA_BODY_PROCEDURAL=1
        #       -> procedural development viewport
        #
        #   KUMA_BODY_REFERENCE=1
        #       -> legacy Avatar V1 reference-rig fallback
        #
        # Override selection changes rendering only.
        # It grants no cognition, permission, or execution authority.
        #
        # PRODUCTION BODY != AUTHORITY
        # RIG SELECTION != INVOCATION
        # VISUAL FALLBACK != CONTROL
        # -------------------------------------------------

        def environment_flag(
            environment_name,
        ):
            value = (
                os.environ
                .get(
                    environment_name,
                    "",
                )
                .strip()
                .lower()
            )

            return (
                value
                in {
                    "1",
                    "true",
                    "yes",
                    "on",
                }
            )

        procedural_enabled = environment_flag(
            "KUMA_BODY_PROCEDURAL"
        )

        reference_fallback_enabled = environment_flag(
            "KUMA_BODY_REFERENCE"
        )

        if procedural_enabled:
            qml_filename = (
                "procedural/KumaMiniViewport.qml"
            )
            rig_label = "procedural rig"

        elif reference_fallback_enabled:
            qml_filename = (
                "KumaMiniReferenceRig.qml"
            )
            rig_label = "reference fallback rig"

        else:
            qml_filename = (
                "KumaMiniBodyR1.qml"
            )
            rig_label = "production Body R1"

        qml_path = (
            Path(__file__)
            .resolve()
            .parent
            / "assets"
            / "kuma_mini"
            / qml_filename
        )

        print(
            "KUMA BODY → "
            f"{rig_label}: {qml_filename}"
        )

        if not qml_path.is_file():
            raise RuntimeError(
                "KUMA Mini 3D scene is missing: "
                f"{qml_path}"
            )

        self.setSource(
            QUrl.fromLocalFile(
                str(qml_path)
            )
        )

        root = self.rootObject()

        if root is None:
            errors = tuple(
                str(error)
                for error in self.errors()
            )

            detail = (
                "; ".join(errors)
                if errors
                else "unknown QML loading error"
            )

            raise RuntimeError(
                "Could not load KUMA Mini 3D scene: "
                f"{detail}"
            )

    def set_avatar_visual_parameters(
        self,
        parameters,
    ):
        """
        Write bounded presentation mechanics into the active QML root.

        This is a one-way renderer sink. It never reads QML state back into
        cognition and never grants authority.
        """

        if not isinstance(
            parameters,
            AvatarVisualParameters,
        ):
            return False

        root = self.rootObject()

        if root is None:
            return False

        values = (
            (
                "avatarMotionEnergy",
                parameters.motion_energy,
            ),
            (
                "avatarExpressionIntensity",
                parameters.expression_intensity,
            ),
            (
                "avatarGazeYaw",
                parameters.gaze_yaw_degrees,
            ),
            (
                "avatarGazePitch",
                parameters.gaze_pitch_degrees,
            ),
        )

        try:
            results = [
                root.setProperty(
                    name,
                    value,
                )
                for (
                    name,
                    value,
                )
                in values
            ]

        except Exception as error:
            print(
                "KUMA BODY → QML expressive parameters unavailable: "
                f"{error}"
            )
            return False

        return all(
            bool(
                result
            )
            for result in results
        )


    def set_body_state(
        self,
        state,
    ):
        root = self.rootObject()

        if root is None:
            return

        root.setProperty(
            "bodyState",
            str(state),
        )
