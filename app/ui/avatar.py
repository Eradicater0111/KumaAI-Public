from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPainter, QPen, QBrush
from PySide6.QtWidgets import QWidget


class KumaAvatar(QWidget):

    STATES = {
        "idle",
        "listening",
        "thinking",
        "speaking",
        "working",
        "success",
        "warning",
        "error",
    }

    def __init__(self, parent=None):

        super().__init__(parent)

        self.state = "idle"

        self.animation_frame = 0

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.animate)
        self.timer.start(120)

        self.setMinimumHeight(90)

    # =====================================================
    # STATE
    # =====================================================

    def set_state(self, state: str):

        if state not in self.STATES:
            state = "idle"

        self.state = state

        self.update()

    # =====================================================
    # ANIMATION
    # =====================================================

    def animate(self):

        self.animation_frame += 1

        self.update()

    # =====================================================
    # DRAW
    # =====================================================

    def paintEvent(self, event):

        painter = QPainter(self)

        painter.setRenderHint(
            QPainter.Antialiasing
        )

        width = self.width()
        height = self.height()

        center_x = width // 2
        center_y = height // 2

        # -------------------------------------------------
        # FACE
        # -------------------------------------------------

        face_radius = 30

        painter.setPen(
            QPen(
                Qt.white,
                2
            )
        )

        painter.setBrush(
            QBrush(
                Qt.transparent
            )
        )

        painter.drawEllipse(
            center_x - face_radius,
            center_y - face_radius,
            face_radius * 2,
            face_radius * 2,
        )

        # -------------------------------------------------
        # EYES
        # -------------------------------------------------

        eye_y = center_y - 7

        left_eye_x = center_x - 11
        right_eye_x = center_x + 11

        eye_size = 5

        # Thinking animation
        if self.state == "thinking":

            offset = (
                self.animation_frame % 3
            ) - 1

        else:

            offset = 0

        painter.setBrush(
            QBrush(Qt.white)
        )

        painter.drawEllipse(
            left_eye_x - eye_size // 2 + offset,
            eye_y - eye_size // 2,
            eye_size,
            eye_size,
        )

        painter.drawEllipse(
            right_eye_x - eye_size // 2 + offset,
            eye_y - eye_size // 2,
            eye_size,
            eye_size,
        )

        # -------------------------------------------------
        # MOUTH
        # -------------------------------------------------

        mouth_y = center_y + 10

        pen = QPen(
            Qt.white,
            2
        )

        painter.setPen(pen)

        if self.state == "speaking":

            # Animated speaking mouth
            mouth_height = (
                self.animation_frame % 4
            ) + 2

            painter.drawEllipse(
                center_x - 7,
                mouth_y - mouth_height // 2,
                14,
                mouth_height,
            )

        elif self.state == "success":

            painter.drawArc(
                center_x - 8,
                mouth_y - 5,
                16,
                12,
                200 * 16,
                140 * 16,
            )

        elif self.state == "warning":

            painter.drawLine(
                center_x - 6,
                mouth_y,
                center_x + 6,
                mouth_y,
            )

        elif self.state == "error":

            painter.drawLine(
                center_x - 7,
                mouth_y - 4,
                center_x + 7,
                mouth_y + 4,
            )

            painter.drawLine(
                center_x + 7,
                mouth_y - 4,
                center_x - 7,
                mouth_y + 4,
            )

        else:

            # Normal expression
            painter.drawArc(
                center_x - 7,
                mouth_y - 3,
                14,
                8,
                200 * 16,
                140 * 16,
            )