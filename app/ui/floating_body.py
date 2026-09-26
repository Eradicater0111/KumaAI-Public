from __future__ import annotations

import math
import sys

from PySide6.QtCore import (
    QPoint,
    QPointF,
    QRectF,
    QSettings,
    QSize,
    QTimer,
    Qt,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QPainter,
    QPainterPath,
    QPen,
    QLinearGradient,
    QRadialGradient,
)
from PySide6.QtWidgets import (
    QApplication,
    QMenu,
    QWidget,
)

from app.ui.body_state import (
    KUMA_BODY_STATES,
    KumaBodyState,
    normalize_body_state,
)
from app.ui.avatar_visual_mechanics import (
    AvatarVisualParameters,
)


class KumaMiniBody(QWidget):
    """
    KUMA's persistent floating desktop body.

    Presentation only.

    It does not:
    - create another KUMA runtime
    - create another AI
    - expose model-facing tools
    - grant execution authority
    - perform GUI actions

    It visualizes the state of the existing KUMA brain.
    """

    state_changed = Signal(str)

    # User interaction request from KUMA's physical body.
    #
    # Presentation only.
    # This signal grants no agent/tool authority.
    interaction_requested = Signal()

    # Emitted while KUMA is moved so any attached companion
    # surface can follow the physical body.
    position_changed = Signal()

    # Main KumaWindow is 380 x 340.
    # Floating KUMA Mini occupies exactly half that footprint.
    BODY_WIDTH = 190
    BODY_HEIGHT = 170

    def __init__(
        self,
        parent=None,
    ):
        super().__init__(
            parent
        )

        self._state = (
            KumaBodyState.IDLE
        )

        self._phase = 0.0

        self._dragging = False
        self._drag_offset = QPoint()

        self._settings = QSettings(
            "KumaAI",
            "KumaMiniBody",
        )

        # -------------------------------------------------
        # WINDOW CONTRACT
        # -------------------------------------------------

        self.setWindowTitle(
            "KUMA Mini"
        )

        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.WindowDoesNotAcceptFocus
        )

        self.setAttribute(
            Qt.WA_TranslucentBackground,
            True,
        )

        self.setAttribute(
            Qt.WA_ShowWithoutActivating,
            True,
        )

        # -------------------------------------------------
        # MACOS PERSISTENT COMPANION PRESENCE
        # -------------------------------------------------
        #
        # Qt.Tool windows normally disappear when the
        # application becomes inactive on macOS.
        #
        # KUMA is a persistent desktop companion, so he must
        # remain visible while the user works in other apps.
        # -------------------------------------------------

        if sys.platform == "darwin":
            self.setAttribute(
                Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow,
                True,
            )

        self.setFocusPolicy(
            Qt.NoFocus
        )

        self.setMouseTracking(
            True
        )

        self.setFixedSize(
            self.BODY_WIDTH,
            self.BODY_HEIGHT,
        )

        # -------------------------------------------------
        # REAL-TIME 3D BODY
        # -------------------------------------------------
        #
        # BODY-2A QPainter rendering remains available as a
        # fail-safe fallback. Failure to load Qt Quick 3D must
        # never make KUMA disappear from the desktop.
        # -------------------------------------------------

        self._use_3d = False
        self._three_d_view = None

        try:
            from app.ui.kuma_3d_view import (
                Kuma3DView,
            )

            self._three_d_view = Kuma3DView(
                self
            )

            self._three_d_view.setGeometry(
                self.rect()
            )

            self._three_d_view.set_body_state(
                self._state.value
            )

            self._three_d_view.show()

            self._use_3d = True

        except Exception as error:
            print(
                "KUMA BODY → 3D renderer unavailable; "
                "using BODY-2A fallback: "
                f"{error}"
            )

            self._three_d_view = None
            self._use_3d = False

        # -------------------------------------------------
        # ANIMATION
        # -------------------------------------------------

        self._animation_timer = QTimer(
            self
        )

        self._animation_timer.setInterval(
            33
        )

        self._animation_timer.timeout.connect(
            self._animate
        )

        self._animation_timer.start()

        self._restore_position()

    # =====================================================
    # PUBLIC VISUAL STATE
    # =====================================================

    @property
    def state(
        self,
    ):
        return self._state

    def set_state(
        self,
        state,
    ):
        normalized = (
            normalize_body_state(
                state
            )
        )

        if normalized == self._state:
            return

        self._state = normalized

        self._phase = 0.0

        self.state_changed.emit(
            normalized.value
        )

        if (
            self._three_d_view
            is not None
        ):
            self._three_d_view.set_body_state(
                normalized.value
            )

        self.update()

    # =====================================================
    # KUMA-AVATAR-1D EXPRESSIVE 3D PARAMETERS
    # =====================================================

    def set_avatar_visual_parameters(
        self,
        parameters,
    ):
        """
        Forward bounded presentation mechanics to the optional 3D renderer.

        QPainter fallback remains functional without these extra mechanics.
        Presentation failure never affects KUMA task execution.
        """

        if not isinstance(
            parameters,
            AvatarVisualParameters,
        ):
            return False

        if (
            self._three_d_view
            is None
        ):
            return False

        try:
            return bool(
                self._three_d_view
                .set_avatar_visual_parameters(
                    parameters
                )
            )

        except Exception as error:
            print(
                "KUMA BODY → expressive parameters unavailable: "
                f"{error}"
            )
            return False

    # =====================================================
    # POSITION
    # =====================================================

    def _restore_position(
        self,
    ):
        x = self._settings.value(
            "x"
        )

        y = self._settings.value(
            "y"
        )

        if (
            x is not None
            and y is not None
        ):
            try:
                self.move(
                    int(x),
                    int(y),
                )
                return
            except Exception:
                pass

        app = QApplication.instance()

        if app is None:
            return

        screen = app.primaryScreen()

        if screen is None:
            return

        area = (
            screen.availableGeometry()
        )

        self.move(
            area.right()
            - self.width()
            - 30,
            area.bottom()
            - self.height()
            - 40,
        )

    def _save_position(
        self,
    ):
        position = self.pos()

        self._settings.setValue(
            "x",
            position.x(),
        )

        self._settings.setValue(
            "y",
            position.y(),
        )

        self._settings.sync()

    # =====================================================
    # ANIMATION
    # =====================================================

    def _animate(
        self,
    ):
        speed = {
            KumaBodyState.IDLE: 0.055,
            KumaBodyState.LISTENING: 0.07,
            KumaBodyState.SPEAKING: 0.11,
            KumaBodyState.THINKING: 0.09,
            KumaBodyState.OBSERVING: 0.08,
            KumaBodyState.WORKING: 0.10,
            KumaBodyState.FOCUSED: 0.06,
            KumaBodyState.HAPPY: 0.14,
            KumaBodyState.ALERT: 0.12,
            KumaBodyState.SLEEP: 0.025,
        }[
            self._state
        ]

        self._phase += speed

        self.update()

    def _bob_offset(
        self,
    ):
        amplitude = {
            KumaBodyState.IDLE: 3.0,
            KumaBodyState.LISTENING: 2.0,
            KumaBodyState.SPEAKING: 2.5,
            KumaBodyState.THINKING: 2.0,
            KumaBodyState.OBSERVING: 2.0,
            KumaBodyState.WORKING: 1.5,
            KumaBodyState.FOCUSED: 1.0,
            KumaBodyState.HAPPY: 5.0,
            KumaBodyState.ALERT: 1.0,
            KumaBodyState.SLEEP: 1.5,
        }[
            self._state
        ]

        return (
            math.sin(
                self._phase
            )
            * amplitude
        )

    # =====================================================
    # PAINT
    # =====================================================

    def paintEvent(
        self,
        event,
    ):
        del event

        if self._use_3d:
            return

        painter = QPainter(
            self
        )

        painter.setRenderHint(
            QPainter.Antialiasing,
            True,
        )

        painter.translate(
            0,
            self._bob_offset(),
        )

        self._draw_shadow(
            painter
        )

        self._draw_body(
            painter
        )

        self._draw_head(
            painter
        )

        self._draw_ears(
            painter
        )

        self._draw_face(
            painter
        )

        self._draw_state_effect(
            painter
        )

        painter.end()


    def _draw_shadow(
        self,
        painter,
    ):
        painter.setPen(
            Qt.NoPen
        )

        # Wide soft floor shadow.
        for index in range(
            5
        ):
            alpha = max(
                0,
                38 - index * 7,
            )

            painter.setBrush(
                QColor(
                    0,
                    0,
                    0,
                    alpha,
                )
            )

            painter.drawEllipse(
                QRectF(
                    49 - index * 2,
                    164 - index,
                    82 + index * 4,
                    12 + index * 2,
                )
            )


    def _draw_body(
        self,
        painter,
    ):
        # -------------------------------------------------
        # TORSO — compact KUMA Mini proportions
        # -------------------------------------------------

        torso_gradient = QLinearGradient(
            0,
            111,
            0,
            162,
        )

        torso_gradient.setColorAt(
            0.0,
            QColor(
                244,
                245,
                247,
            ),
        )

        torso_gradient.setColorAt(
            0.55,
            QColor(
                195,
                198,
                204,
            ),
        )

        torso_gradient.setColorAt(
            1.0,
            QColor(
                136,
                140,
                149,
            ),
        )

        painter.setPen(
            QPen(
                QColor(
                    78,
                    82,
                    91,
                    225,
                ),
                1.4,
            )
        )

        painter.setBrush(
            torso_gradient
        )

        painter.drawRoundedRect(
            QRectF(
                62,
                111,
                56,
                47,
            ),
            19,
            19,
        )

        # -------------------------------------------------
        # SHOULDER / ARM CAPS
        # -------------------------------------------------

        arm_gradient = QLinearGradient(
            0,
            116,
            0,
            154,
        )

        arm_gradient.setColorAt(
            0.0,
            QColor(
                224,
                226,
                230,
            ),
        )

        arm_gradient.setColorAt(
            1.0,
            QColor(
                126,
                130,
                140,
            ),
        )

        painter.setPen(
            QPen(
                QColor(
                    72,
                    75,
                    84,
                    220,
                ),
                1.2,
            )
        )

        painter.setBrush(
            arm_gradient
        )

        painter.drawEllipse(
            QRectF(
                48,
                118,
                18,
                34,
            )
        )

        painter.drawEllipse(
            QRectF(
                114,
                118,
                18,
                34,
            )
        )

        # -------------------------------------------------
        # CHEST PLATE
        # -------------------------------------------------

        chest_gradient = QLinearGradient(
            0,
            127,
            0,
            151,
        )

        chest_gradient.setColorAt(
            0.0,
            QColor(
                35,
                39,
                47,
            ),
        )

        chest_gradient.setColorAt(
            1.0,
            QColor(
                9,
                12,
                18,
            ),
        )

        painter.setPen(
            QPen(
                QColor(
                    104,
                    116,
                    138,
                    200,
                ),
                1.0,
            )
        )

        painter.setBrush(
            chest_gradient
        )

        painter.drawRoundedRect(
            QRectF(
                79,
                128,
                22,
                22,
            ),
            7,
            7,
        )

        painter.setPen(
            QColor(
                220,
                232,
                255,
            )
        )

        font = QFont()
        font.setBold(
            True
        )
        font.setPointSize(
            9
        )

        painter.setFont(
            font
        )

        painter.drawText(
            QRectF(
                79,
                127,
                22,
                22,
            ),
            Qt.AlignCenter,
            "K",
        )


    def _draw_head(
        self,
        painter,
    ):
        # -------------------------------------------------
        # HEADPHONE SIDE PODS
        # -------------------------------------------------

        pod_gradient = QLinearGradient(
            0,
            68,
            0,
            111,
        )

        pod_gradient.setColorAt(
            0.0,
            QColor(
                209,
                211,
                216,
            ),
        )

        pod_gradient.setColorAt(
            1.0,
            QColor(
                92,
                96,
                105,
            ),
        )

        painter.setPen(
            QPen(
                QColor(
                    54,
                    58,
                    67,
                    230,
                ),
                1.5,
            )
        )

        painter.setBrush(
            pod_gradient
        )

        painter.drawEllipse(
            QRectF(
                25,
                69,
                24,
                42,
            )
        )

        painter.drawEllipse(
            QRectF(
                131,
                69,
                24,
                42,
            )
        )

        # Warm inner pod rings from the reference design.
        painter.setBrush(
            QColor(
                19,
                22,
                29,
            )
        )

        painter.drawEllipse(
            QRectF(
                31,
                76,
                13,
                28,
            )
        )

        painter.drawEllipse(
            QRectF(
                136,
                76,
                13,
                28,
            )
        )

        painter.setPen(
            QPen(
                QColor(
                    245,
                    226,
                    196,
                    210,
                ),
                2.1,
            )
        )

        painter.setBrush(
            Qt.NoBrush
        )

        painter.drawEllipse(
            QRectF(
                32,
                78,
                11,
                24,
            )
        )

        painter.drawEllipse(
            QRectF(
                137,
                78,
                11,
                24,
            )
        )

        # -------------------------------------------------
        # OUTER HEAD SHELL
        # -------------------------------------------------

        shell_gradient = QLinearGradient(
            0,
            47,
            0,
            130,
        )

        shell_gradient.setColorAt(
            0.0,
            QColor(
                247,
                248,
                250,
            ),
        )

        shell_gradient.setColorAt(
            0.45,
            QColor(
                211,
                213,
                218,
            ),
        )

        shell_gradient.setColorAt(
            1.0,
            QColor(
                125,
                129,
                138,
            ),
        )

        painter.setPen(
            QPen(
                QColor(
                    74,
                    78,
                    87,
                    240,
                ),
                1.6,
            )
        )

        painter.setBrush(
            shell_gradient
        )

        painter.drawRoundedRect(
            QRectF(
                34,
                47,
                112,
                83,
            ),
            35,
            35,
        )

        # -------------------------------------------------
        # FACE GLASS
        # -------------------------------------------------

        glass_gradient = QLinearGradient(
            0,
            56,
            0,
            121,
        )

        glass_gradient.setColorAt(
            0.0,
            QColor(
                20,
                26,
                38,
            ),
        )

        glass_gradient.setColorAt(
            0.35,
            QColor(
                6,
                11,
                20,
            ),
        )

        glass_gradient.setColorAt(
            1.0,
            QColor(
                2,
                5,
                10,
            ),
        )

        painter.setPen(
            QPen(
                QColor(
                    65,
                    78,
                    99,
                    220,
                ),
                1.4,
            )
        )

        painter.setBrush(
            glass_gradient
        )

        painter.drawRoundedRect(
            QRectF(
                43,
                56,
                94,
                65,
            ),
            27,
            27,
        )

        # -------------------------------------------------
        # GLASS REFLECTION
        # -------------------------------------------------

        reflection = QLinearGradient(
            0,
            58,
            0,
            87,
        )

        reflection.setColorAt(
            0.0,
            QColor(
                255,
                255,
                255,
                38,
            ),
        )

        reflection.setColorAt(
            1.0,
            QColor(
                255,
                255,
                255,
                0,
            ),
        )

        painter.setPen(
            Qt.NoPen
        )

        painter.setBrush(
            reflection
        )

        painter.drawRoundedRect(
            QRectF(
                49,
                60,
                82,
                25,
            ),
            18,
            18,
        )


    def _draw_ears(
        self,
        painter,
    ):
        # Metallic outer ears.
        ear_gradient = QLinearGradient(
            0,
            17,
            0,
            57,
        )

        ear_gradient.setColorAt(
            0.0,
            QColor(
                226,
                228,
                232,
            ),
        )

        ear_gradient.setColorAt(
            1.0,
            QColor(
                88,
                92,
                102,
            ),
        )

        painter.setPen(
            QPen(
                QColor(
                    64,
                    68,
                    78,
                    230,
                ),
                1.3,
            )
        )

        painter.setBrush(
            ear_gradient
        )

        left = QPainterPath()

        left.moveTo(
            47,
            56,
        )

        left.lineTo(
            31,
            18,
        )

        left.quadTo(
            27,
            10,
            31,
            43,
        )

        left.quadTo(
            36,
            50,
            47,
            56,
        )

        left.closeSubpath()

        right = QPainterPath()

        right.moveTo(
            133,
            56,
        )

        right.lineTo(
            149,
            18,
        )

        right.quadTo(
            153,
            10,
            149,
            43,
        )

        right.quadTo(
            144,
            50,
            133,
            56,
        )

        right.closeSubpath()

        painter.drawPath(
            left
        )

        painter.drawPath(
            right
        )

        # Warm-white illuminated inner strips.
        painter.setPen(
            QPen(
                QColor(
                    255,
                    232,
                    200,
                    220,
                ),
                2.8,
                Qt.SolidLine,
                Qt.RoundCap,
            )
        )

        painter.drawLine(
            QPointF(
                32,
                27,
            ),
            QPointF(
                39,
                49,
            ),
        )

        painter.drawLine(
            QPointF(
                148,
                27,
            ),
            QPointF(
                141,
                49,
            ),
        )


    def _eye_pen(
        self,
    ):
        if (
            self._state
            == KumaBodyState.ALERT
        ):
            return QPen(
                QColor(
                    255,
                    102,
                    108,
                ),
                4.4,
                Qt.SolidLine,
                Qt.RoundCap,
            )

        return QPen(
            QColor(
                112,
                177,
                255,
            ),
            4.4,
            Qt.SolidLine,
            Qt.RoundCap,
        )


    def _draw_face(
        self,
        painter,
    ):
        # -------------------------------------------------
        # SOFT BLUE EYE GLOW
        # -------------------------------------------------

        if (
            self._state
            != KumaBodyState.ALERT
        ):
            glow_color = QColor(
                72,
                145,
                255,
                46,
            )

            painter.setPen(
                Qt.NoPen
            )

            painter.setBrush(
                glow_color
            )

            painter.drawEllipse(
                QRectF(
                    55,
                    72,
                    32,
                    31,
                )
            )

            painter.drawEllipse(
                QRectF(
                    93,
                    72,
                    32,
                    31,
                )
            )

        painter.setBrush(
            Qt.NoBrush
        )

        painter.setPen(
            self._eye_pen()
        )

        # -------------------------------------------------
        # HAPPY / IDLE
        # -------------------------------------------------

        if (
            self._state
            in (
                KumaBodyState.HAPPY,
                KumaBodyState.IDLE,
            )
        ):
            painter.drawArc(
                QRectF(
                    59,
                    78,
                    23,
                    18,
                ),
                20 * 16,
                140 * 16,
            )

            painter.drawArc(
                QRectF(
                    98,
                    78,
                    23,
                    18,
                ),
                20 * 16,
                140 * 16,
            )

        # -------------------------------------------------
        # SLEEP
        # -------------------------------------------------

        elif (
            self._state
            == KumaBodyState.SLEEP
        ):
            painter.drawArc(
                QRectF(
                    59,
                    84,
                    23,
                    11,
                ),
                200 * 16,
                140 * 16,
            )

            painter.drawArc(
                QRectF(
                    98,
                    84,
                    23,
                    11,
                ),
                200 * 16,
                140 * 16,
            )

        # -------------------------------------------------
        # FOCUSED
        # -------------------------------------------------

        elif (
            self._state
            == KumaBodyState.FOCUSED
        ):
            painter.drawLine(
                QPointF(
                    60,
                    84,
                ),
                QPointF(
                    80,
                    88,
                ),
            )

            painter.drawLine(
                QPointF(
                    100,
                    88,
                ),
                QPointF(
                    120,
                    84,
                ),
            )

        # -------------------------------------------------
        # THINKING
        # -------------------------------------------------

        elif (
            self._state
            == KumaBodyState.THINKING
        ):
            painter.drawLine(
                QPointF(
                    59,
                    87,
                ),
                QPointF(
                    80,
                    87,
                ),
            )

            painter.drawLine(
                QPointF(
                    100,
                    87,
                ),
                QPointF(
                    121,
                    87,
                ),
            )

        # -------------------------------------------------
        # ALERT
        # -------------------------------------------------

        elif (
            self._state
            == KumaBodyState.ALERT
        ):
            painter.drawLine(
                QPointF(
                    59,
                    82,
                ),
                QPointF(
                    80,
                    89,
                ),
            )

            painter.drawLine(
                QPointF(
                    100,
                    89,
                ),
                QPointF(
                    121,
                    82,
                ),
            )

        # -------------------------------------------------
        # OBSERVING — pupils track subtly
        # -------------------------------------------------

        elif (
            self._state
            == KumaBodyState.OBSERVING
        ):
            offset = (
                math.sin(
                    self._phase * 1.3
                )
                * 3.0
            )

            painter.drawEllipse(
                QPointF(
                    70 + offset,
                    87,
                ),
                4,
                7,
            )

            painter.drawEllipse(
                QPointF(
                    110 + offset,
                    87,
                ),
                4,
                7,
            )

        # -------------------------------------------------
        # LISTENING — wide attentive eyes
        # -------------------------------------------------

        elif (
            self._state
            == KumaBodyState.LISTENING
        ):
            painter.drawEllipse(
                QPointF(
                    70,
                    87,
                ),
                6,
                8,
            )

            painter.drawEllipse(
                QPointF(
                    110,
                    87,
                ),
                6,
                8,
            )

        # -------------------------------------------------
        # WORKING
        # -------------------------------------------------

        else:
            painter.drawEllipse(
                QPointF(
                    70,
                    87,
                ),
                4,
                7,
            )

            painter.drawEllipse(
                QPointF(
                    110,
                    87,
                ),
                4,
                7,
            )


    def _draw_state_effect(
        self,
        painter,
    ):
        if (
            self._state
            == KumaBodyState.THINKING
        ):
            # Floating thought dots.
            for index in range(
                3
            ):
                alpha = (
                    120
                    + index * 35
                )

                painter.setPen(
                    Qt.NoPen
                )

                painter.setBrush(
                    QColor(
                        162,
                        204,
                        255,
                        alpha,
                    )
                )

                painter.drawEllipse(
                    QPointF(
                        143 + index * 7,
                        54 - index * 5,
                    ),
                    2.2,
                    2.2,
                )

        elif (
            self._state
            == KumaBodyState.ALERT
        ):
            painter.setPen(
                QColor(
                    255,
                    105,
                    105,
                )
            )

            font = QFont()
            font.setBold(
                True
            )
            font.setPointSize(
                18
            )

            painter.setFont(
                font
            )

            painter.drawText(
                QRectF(
                    145,
                    35,
                    25,
                    34,
                ),
                Qt.AlignCenter,
                "!",
            )

        elif (
            self._state
            == KumaBodyState.SLEEP
        ):
            painter.setPen(
                QColor(
                    142,
                    188,
                    255,
                )
            )

            font = QFont()
            font.setBold(
                True
            )
            font.setPointSize(
                11
            )

            painter.setFont(
                font
            )

            painter.drawText(
                140,
                51,
                "Z"
            )

            painter.drawText(
                151,
                39,
                "z"
            )

        elif (
            self._state
            == KumaBodyState.HAPPY
        ):
            # Very subtle success aura.
            pulse = (
                1.0
                + (
                    math.sin(
                        self._phase * 2
                    )
                    + 1.0
                )
                * 1.5
            )

            painter.setPen(
                QPen(
                    QColor(
                        100,
                        170,
                        255,
                        70,
                    ),
                    1.5,
                )
            )

            painter.setBrush(
                Qt.NoBrush
            )

            painter.drawRoundedRect(
                QRectF(
                    40 - pulse,
                    53 - pulse,
                    100 + pulse * 2,
                    72 + pulse * 2,
                ),
                29,
                29,
            )

        elif (
            self._state
            == KumaBodyState.LISTENING
        ):
            # Ear activity indicators.
            strength = (
                5
                + math.sin(
                    self._phase * 2
                )
                * 2
            )

            painter.setPen(
                QPen(
                    QColor(
                        113,
                        181,
                        255,
                        150,
                    ),
                    1.8,
                )
            )

            painter.setBrush(
                Qt.NoBrush
            )

            painter.drawArc(
                QRectF(
                    18 - strength,
                    72 - strength,
                    26 + strength,
                    34 + strength,
                ),
                80 * 16,
                180 * 16,
            )

            painter.drawArc(
                QRectF(
                    136,
                    72 - strength,
                    26 + strength,
                    34 + strength,
                ),
                -80 * 16,
                180 * 16,
            )

    # =====================================================
    # INTERACTION
    # =====================================================

    def mousePressEvent(
        self,
        event,
    ):
        if (
            event.button()
            == Qt.LeftButton
        ):
            self._dragging = True

            self._drag_offset = (
                event.globalPosition()
                .toPoint()
                - self.frameGeometry().topLeft()
            )

            event.accept()
            return

        if (
            event.button()
            == Qt.RightButton
        ):
            self._show_context_menu(
                event.globalPosition()
                .toPoint()
            )

            event.accept()
            return

        super().mousePressEvent(
            event
        )

    def mouseMoveEvent(
        self,
        event,
    ):
        if (
            self._dragging
            and event.buttons()
            & Qt.LeftButton
        ):
            self.move(
                event.globalPosition()
                .toPoint()
                - self._drag_offset
            )

            self.position_changed.emit()

            event.accept()
            return

        super().mouseMoveEvent(
            event
        )

    def mouseReleaseEvent(
        self,
        event,
    ):
        if (
            event.button()
            == Qt.LeftButton
            and self._dragging
        ):
            self._dragging = False

            self._save_position()

            self.position_changed.emit()

            event.accept()
            return

        super().mouseReleaseEvent(
            event
        )

    def mouseDoubleClickEvent(
        self,
        event,
    ):
        """
        Open or dismiss KUMA's interaction surface.

        Double-clicking the embodied companion must not mutate
        runtime state merely for visual testing.

        State testing remains available through the developer
        context menu.
        """

        if (
            event.button()
            != Qt.LeftButton
        ):
            super().mouseDoubleClickEvent(
                event
            )
            return

        self.interaction_requested.emit()

        event.accept()

    def _show_context_menu(
        self,
        global_position,
    ):
        menu = QMenu(
            self
        )

        talk_action = menu.addAction(
            "Talk to KUMA"
        )

        talk_action.triggered.connect(
            self.interaction_requested.emit
        )

        menu.addSeparator()

        state_menu = (
            menu.addMenu(
                "KUMA State"
            )
        )

        for state_name in KUMA_BODY_STATES:
            action = (
                state_menu.addAction(
                    state_name.title()
                )
            )

            action.triggered.connect(
                lambda checked=False, value=state_name:
                self.set_state(
                    value
                )
            )

        menu.addSeparator()

        hide_action = menu.addAction(
            "Hide KUMA"
        )

        hide_action.triggered.connect(
            self.hide
        )

        menu.exec(
            global_position
        )

    def closeEvent(
        self,
        event,
    ):
        self._save_position()

        super().closeEvent(
            event
        )

    def sizeHint(
        self,
    ):
        return QSize(
            self.BODY_WIDTH,
            self.BODY_HEIGHT,
        )


def main():
    app = QApplication.instance()

    owns_application = (
        app is None
    )

    if app is None:
        app = QApplication(
            sys.argv
        )

    app.setApplicationName(
        "KUMA"
    )

    body = KumaMiniBody()

    body.show()

    if owns_application:
        raise SystemExit(
            app.exec()
        )

    return body


if __name__ == "__main__":
    main()
