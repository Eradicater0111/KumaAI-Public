import threading

from PySide6.QtCore import Qt, QThread, Signal, Slot, QTimer
from PySide6.QtGui import (
    QColor,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import (
    QWidget,
    QLabel,
    QVBoxLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QMessageBox,
)

from app.ui.avatar import KumaAvatar
from app.ui.floating_body import KumaMiniBody
from app.ui.body_controller import KumaBodyController
from app.ui.avatar_runtime import (
    AvatarExpression,
    AvatarGaze,
    AvatarMode,
    AvatarSnapshot,
)
from app.emotion import (
    KumaEmotion,
    LanguageEmotionAnalyzer,
    KumaExpressionMapper,
)

from app.agent.gui_runtime import KumaGUIRuntime
from app.agent.model_warmup import start_model_prewarm
from app.memory.memory import initialize_memory
from app.voice.speech_controller import KumaSpeechController


# =========================================================
# KUMA-AVATAR-1C LIVE SEMANTIC LIFECYCLE
# =========================================================
#
# UI EVENT != COGNITION
# VOICE EVENT != AUTHORITY
# SUCCESS PRESENTATION != VERIFIED GOAL COMPLETION
# ERROR PRESENTATION != TASK FAILURE AUTHORITY
# AVATAR TRANSITION != CONTROL FLOW
# RENDERER STATE != MODEL CONTEXT
#
# Window lifecycle events may publish immutable AvatarSnapshot
# presentation state through KumaBodyController. The controller
# remains the only semantic-to-renderer sink.
# =========================================================


class KumaWorker(QThread):
    """
    Runs the production KUMA runtime outside the Qt GUI thread.

    IMPORTANT:
    - No Qt widgets are touched here.
    - Status updates cross into the GUI using Qt signals.
    - Dangerous-action confirmation is handled by KumaWindow.
    """

    response_finished = Signal(str)
    status_changed = Signal(str)
    error = Signal(str)

    def __init__(self, runtime, message):
        super().__init__()

        self.runtime = runtime
        self.message = message

    def report_status(self, status):
        """
        Thread-safe status bridge.

        This method executes inside the worker thread and emits a
        Qt signal. The connected GUI slot executes on the GUI thread.
        """
        self.status_changed.emit(str(status))

    def run(self):
        try:
            # The production agent reports status through this worker.
            self.runtime.kuma.status_callback = self.report_status

            response = self.runtime.run(self.message)

            self.response_finished.emit(str(response))

        except Exception as error:
            self.error.emit(str(error))


class KumaWindow(QWidget):
    """
    Main KUMA desktop window.

    Architecture:

        GUI thread
             |
             v
        KumaWorker
             |
             v
        Production KUMA Runtime
             |
             +---- status ---> Qt Signal ---> GUI
             |
             +---- dangerous action
                       |
                       v
              confirmation signal
                       |
                       v
                   GUI dialog
                       |
                       v
                  Event result
                       |
                       v
                  Worker continues
    """

    # =========================================================
    # SIGNALS
    # =========================================================

    # Worker -> GUI confirmation bridge.
    #
    # tool_name : str
    # arguments : object
    # event     : threading.Event
    # result    : mutable dict
    confirmation_requested = Signal(
        str,
        object,
        object,
        object,
    )

    # =========================================================
    # INITIALIZATION
    # =========================================================

    def __init__(self):
        super().__init__()

        initialize_memory()

        self.runtime = None
        self.worker = None

        self.current_response = ""
        self._closing = False

        # Floating-body terminal-state lifecycle.
        #
        # Generation prevents an old delayed IDLE reset from
        # overwriting the state of a newer KUMA request.
        self._body_idle_generation = 0

        # -----------------------------------------------------
        # Confirmation bridge
        # -----------------------------------------------------

        self.confirmation_requested.connect(
            self.show_confirmation_dialog
        )

        # -----------------------------------------------------
        # Production runtime
        # -----------------------------------------------------

        self.runtime = KumaGUIRuntime(
            confirmation_callback=self.request_confirmation,
            status_callback=None,
        )

        # =================================================
        # KUMA PERF-3D — BACKGROUND DUAL-BRAIN PREWARM
        # =================================================
        # Warm the local synthesis + main Qwen models without blocking
        # GUI construction. No user data or tool authority enters this path.
        try:
            start_model_prewarm(
                getattr(
                    self.runtime,
                    "kuma",
                    None,
                )
            )
        except Exception as error:
            print(
                "KUMA PREWARM → "
                f"background startup skipped non-fatally: {error}"
            )


        # -----------------------------------------------------
        # KUMA VOICE
        # -----------------------------------------------------
        #
        # One presentation-level speech controller attached to
        # the same production KUMA runtime.
        #
        # No additional agent/model/runtime is created.
        # -----------------------------------------------------

        self.speech = KumaSpeechController(
            self
        )

        self.speech.voice_ready.connect(
            self._on_kuma_voice_ready
        )

        self.speech.speech_started.connect(
            self._on_kuma_speech_started
        )

        self.speech.speech_finished.connect(
            self._on_kuma_speech_finished
        )

        self.speech.speech_error.connect(
            self._on_kuma_speech_error
        )

        # -----------------------------------------------------
        # KUMA MINI FLOATING BODY
        # -----------------------------------------------------
        #
        # Presentation only.
        #
        # This does NOT create:
        # - another KUMA runtime
        # - another agent
        # - another planner
        # - another model-facing capability
        #
        # KumaMiniBody visualizes the state of THIS exact
        # production runtime.
        # -----------------------------------------------------

        self.floating_body = KumaMiniBody()

        self.body_controller = KumaBodyController(
            self.floating_body
        )

        # -----------------------------------------------------
        # COMPANION-FIRST INTERACTION
        # -----------------------------------------------------
        #
        # KUMA's floating body is the primary interface.
        # The conversation window is summoned only when the
        # user explicitly interacts with KUMA.
        # -----------------------------------------------------

        self.floating_body.interaction_requested.connect(
            self.toggle_companion_panel
        )

        self.floating_body.position_changed.connect(
            self._follow_body_if_panel_visible
        )

        self.floating_body.show()

        # -----------------------------------------------------
        # Window
        # -----------------------------------------------------

        self.setWindowTitle("KUMA")

        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
        )

        # -----------------------------------------------------
        # COMPANION-2 SPEECH BUBBLE GEOMETRY
        # -----------------------------------------------------

        self.resize(
            340,
            160,
        )

        self.setMinimumSize(
            320,
            145,
        )

        self.setMaximumSize(
            420,
            310,
        )

        self.setAttribute(
            Qt.WA_TranslucentBackground,
            True,
        )

        # The bubble tail points toward KUMA.
        self._bubble_tail_side = "right"

        # -----------------------------------------------------
        # COMPANION-FIRST BOOT
        # -----------------------------------------------------
        #
        # The legacy assistant panel is runtime infrastructure,
        # not KUMA's primary desktop presence.
        #
        # Existing startup code may still call show(), so keep
        # the window transparent until the first event-loop tick,
        # then hide it completely.
        # -----------------------------------------------------

        self.setWindowOpacity(
            0.0
        )

        QTimer.singleShot(
            0,
            self._finish_companion_boot
        )

        # =====================================================
        # MAIN LAYOUT
        # =====================================================

        layout = QVBoxLayout()

        layout.setContentsMargins(
            24,
            18,
            24,
            18,
        )

        layout.setSpacing(8)

        # -----------------------------------------------------
        # Avatar
        # -----------------------------------------------------

        self.character = KumaAvatar()

        layout.addWidget(
            self.character
        )

        # KUMA's 3D body is now the avatar.
        self.character.hide()

        # -----------------------------------------------------
        # Name
        # -----------------------------------------------------

        self.name = QLabel("KUMA")

        self.name.setAlignment(
            Qt.AlignCenter
        )

        layout.addWidget(
            self.name
        )

        self.name.hide()

        # -----------------------------------------------------
        # Status
        # -----------------------------------------------------

        self.status = QLabel("Online")

        self.status.setAlignment(
            Qt.AlignCenter
        )

        layout.addWidget(
            self.status
        )

        # Keep status alive for runtime/failure logic,
        # but KUMA's body communicates state visually.
        self.status.hide()

        # -----------------------------------------------------
        # Response
        # -----------------------------------------------------

        self.response = QLabel(
            "Hey. I'm here."
        )

        self.response.setAlignment(
            Qt.AlignLeft
            | Qt.AlignTop
        )

        self.response.setWordWrap(True)

        self.response.setMinimumHeight(
            34
        )

        self.response.setTextInteractionFlags(
            Qt.TextSelectableByMouse
        )

        layout.addWidget(
            self.response
        )

        layout.addStretch()

        # =====================================================
        # INPUT
        # =====================================================

        input_row = QHBoxLayout()

        self.input = QLineEdit()

        self.input.setPlaceholderText(
            "Talk to me..."
        )

        # KUMA VOICE READINESS GATE
        if getattr(
            self.speech,
            "neural_ready",
            False,
        ):
            self.input.setEnabled(
                True
            )
            self.input.setPlaceholderText(
                "Talk to me..."
            )
        else:
            self.input.setEnabled(
                False
            )
            self.input.setPlaceholderText(
                "Kuma is waking up..."
            )
        # END KUMA VOICE READINESS GATE

        self.input.returnPressed.connect(
            self.send_message
        )

        self.send_button = QPushButton(
            "➜"
        )

        self.send_button.setFixedSize(
            42,
            40,
        )

        self.input.setMinimumHeight(
            40
        )

        self.send_button.clicked.connect(
            self.send_message
        )

        input_row.addWidget(
            self.input
        )

        input_row.addWidget(
            self.send_button
        )

        layout.addLayout(
            input_row
        )

        self.setLayout(
            layout
        )

        # =====================================================
        # STYLE
        # =====================================================

        self.setStyleSheet(
            """
            KumaWindow {
                background: transparent;
            }

            QLabel {
                background: transparent;
                color: #f4f6fb;
                font-size: 14px;
            }

            QLineEdit {
                background-color: rgba(25, 28, 36, 235);
                border: 1px solid rgba(115, 130, 160, 150);
                border-radius: 14px;
                padding: 8px 12px;
                color: white;
                selection-background-color: #54A9FF;
            }

            QLineEdit:focus {
                border: 1px solid #54A9FF;
            }

            QPushButton {
                background-color: rgba(55, 66, 86, 235);
                border: 1px solid rgba(110, 130, 170, 130);
                border-radius: 14px;
                color: white;
                font-size: 18px;
                font-weight: 600;
                padding: 0px;
            }

            QPushButton:hover {
                background-color: rgba(75, 98, 135, 245);
            }

            QPushButton:pressed {
                background-color: rgba(44, 85, 135, 245);
            }

            QPushButton:disabled {
                background-color: rgba(35, 38, 46, 210);
                color: #777b84;
            }
            """
        )

    # =========================================================
    # COMPANION-FIRST PANEL LIFECYCLE
    # =========================================================
    # =========================================================
    # COMPANION-2 SPEECH BUBBLE
    # =========================================================

    def paintEvent(
        self,
        event,
    ):
        """
        Draw KUMA's communication surface as a speech bubble.

        The floating 3D body is the character. This window exists
        only as a temporary communication surface.
        """

        del event

        painter = QPainter(
            self
        )

        painter.setRenderHint(
            QPainter.Antialiasing,
            True,
        )

        width = self.width()
        height = self.height()

        tail_width = 16.0
        outer_margin = 7.0

        if self._bubble_tail_side == "right":
            left = outer_margin
            right = width - tail_width - outer_margin
        else:
            left = tail_width + outer_margin
            right = width - outer_margin

        top = outer_margin
        bottom = height - outer_margin

        bubble = QPainterPath()

        bubble.addRoundedRect(
            left,
            top,
            right - left,
            bottom - top,
            20.0,
            20.0,
        )

        tail_y = (
            height * 0.61
        )

        tail = QPainterPath()

        if self._bubble_tail_side == "right":
            tail.moveTo(
                right - 1,
                tail_y - 10,
            )

            tail.lineTo(
                width - 2,
                tail_y,
            )

            tail.lineTo(
                right - 1,
                tail_y + 10,
            )

        else:
            tail.moveTo(
                left + 1,
                tail_y - 10,
            )

            tail.lineTo(
                2,
                tail_y,
            )

            tail.lineTo(
                left + 1,
                tail_y + 10,
            )

        tail.closeSubpath()

        painter.setPen(
            QPen(
                QColor(
                    92,
                    106,
                    135,
                    185,
                ),
                1.0,
            )
        )

        painter.setBrush(
            QColor(
                18,
                21,
                29,
                244,
            )
        )

        painter.drawPath(
            bubble
        )

        painter.setPen(
            Qt.NoPen
        )

        painter.drawPath(
            tail
        )

        # Subtle KUMA-blue upper highlight.
        painter.setPen(
            QPen(
                QColor(
                    84,
                    169,
                    255,
                    90,
                ),
                1.2,
            )
        )

        painter.drawLine(
            int(left + 20),
            int(top + 1),
            int(right - 20),
            int(top + 1),
        )

        painter.end()


    def _resize_companion_panel_for_response(
        self,
    ):
        """
        Keep short exchanges small while allowing longer KUMA
        responses to grow the bubble vertically.
        """

        text = (
            self.response.text()
            .strip()
        )

        estimated_lines = max(
            1,
            (
                len(text)
                + 41
            )
            // 42,
        )

        estimated_lines = min(
            estimated_lines,
            9,
        )

        target_height = (
            125
            + estimated_lines * 20
        )

        target_height = max(
            150,
            min(
                target_height,
                310,
            ),
        )

        self.resize(
            340,
            target_height,
        )


    @Slot()
    def _follow_body_if_panel_visible(
        self,
    ):
        """
        Keep the bubble physically attached to KUMA while the user
        drags the companion around the desktop.
        """

        if not self.isVisible():
            return

        self._position_panel_near_body()



    def _finish_companion_boot(
        self,
    ):
        """
        Hide the legacy assistant shell after startup.

        KumaMiniBody remains visible and owns the desktop presence.
        The production runtime remains alive inside this window
        object even while the panel itself is hidden.
        """

        self.hide()

        self.setWindowOpacity(
            1.0
        )


    @Slot()
    def toggle_companion_panel(
        self,
    ):
        """
        Toggle KUMA's conversation surface from the embodied
        floating companion.
        """

        if self.isVisible():
            self.hide()
            return

        self.show_companion_panel()


    def show_companion_panel(
        self,
    ):
        """
        Show the existing conversation/runtime panel beside KUMA.

        This changes presentation only. It does not create another
        runtime, agent, worker, planner, or tool boundary.
        """

        self._resize_companion_panel_for_response()

        self._position_panel_near_body()

        self.setWindowOpacity(
            1.0
        )

        self.show()
        self.raise_()
        self.activateWindow()

        self.input.setFocus()


    def _position_panel_near_body(
        self,
    ):
        """
        Attach the speech bubble beside KUMA and point its tail
        toward the floating body.
        """

        body_geometry = (
            self.floating_body
            .frameGeometry()
        )

        gap = 8

        # Prefer the left side because KUMA normally lives near
        # the right edge of the desktop.
        x = (
            body_geometry.left()
            - self.width()
            - gap
        )

        y = (
            body_geometry.center().y()
            - self.height() // 2
        )

        self._bubble_tail_side = "right"

        screen = (
            self.floating_body
            .screen()
        )

        if screen is not None:

            area = (
                screen.availableGeometry()
            )

            # If KUMA is too close to the left edge,
            # move the bubble to his right.
            if x < area.left():

                x = (
                    body_geometry.right()
                    + gap
                )

                self._bubble_tail_side = "left"

            max_x = (
                area.right()
                - self.width()
                + 1
            )

            max_y = (
                area.bottom()
                - self.height()
                + 1
            )

            x = max(
                area.left(),
                min(
                    x,
                    max_x,
                ),
            )

            y = max(
                area.top(),
                min(
                    y,
                    max_y,
                ),
            )

        self.move(
            x,
            y,
        )

        self.update()


    def keyPressEvent(
        self,
        event,
    ):
        """
        Escape dismisses the conversation surface without
        terminating KUMA.
        """

        if (
            event.key()
            == Qt.Key_Escape
        ):
            self.hide()
            event.accept()
            return

        super().keyPressEvent(
            event
        )


    # =========================================================
    # DANGEROUS ACTION CONFIRMATION
    # =========================================================
    def request_confirmation(
        self,
        tool_name,
        arguments,
    ):
        """
        Request approval from the GUI thread.

        The agent worker waits while the Qt GUI thread
        displays the confirmation dialog.
        """

        event = threading.Event()

        result = {
            "approved": False
        }

        if self._closing:
            return False

        self.confirmation_requested.emit(
            str(tool_name),
            arguments,
            event,
            result,
        )

        # Wait for GUI response.
        #
        # This blocks the worker thread only.
        event.wait()

        return bool(
            result.get("approved", False)
        )

    @Slot(
            str,
            object,
            object,
            object,
        )
    def show_confirmation_dialog(
            self,
            tool_name,
            arguments,
            event,
            result,
        ):
            """
            Display dangerous-action confirmation on the GUI thread.
            """

            approved = False

            try:
                command = ""

                if isinstance(
                    arguments,
                    dict,
                ):
                    command = str(
                        arguments.get(
                            "command",
                            "",
                        )
                    )

                # -------------------------------------------------
                # Build readable details
                # -------------------------------------------------

                if command:
                    details = (
                        f"Tool: {tool_name}\n\n"
                        f"Command:\n{command}"
                    )

                else:
                    details = (
                        f"Tool: {tool_name}\n\n"
                        f"Arguments: {arguments}"
                    )

                # -------------------------------------------------
                # Dialog
                # -------------------------------------------------

                dialog = QMessageBox(
                    self
                )

                dialog.setWindowTitle(
                    "KUMA — Action Confirmation"
                )

                dialog.setIcon(
                    QMessageBox.Warning
                )

                dialog.setText(
                    "KUMA wants to perform a potentially dangerous action."
                )

                dialog.setInformativeText(
                    details
                    + "\n\n"
                    + "Do you want to allow this action?"
                )

                approve_button = dialog.addButton(
                    "Allow",
                    QMessageBox.AcceptRole,
                )

                deny_button = dialog.addButton(
                    "Deny",
                    QMessageBox.RejectRole,
                )

                # Fail closed.
                dialog.setDefaultButton(
                    deny_button
                )

                dialog.exec()

                approved = (
                    dialog.clickedButton()
                    is approve_button
                )

            except Exception as error:
                print(
                    "KUMA GUI → "
                    f"Confirmation dialog failed: {error}"
                )

                # NEVER approve on failure.
                approved = False

            finally:
                result["approved"] = approved

                # Wake worker regardless of outcome.
                event.set()
    # =========================================================
    # KUMA EMOTIONAL PRESENCE
    # =========================================================

    def _capture_user_emotion(
        self,
        message,
    ):
        """
        Infer conversational affect expressed in the current
        user message and retain the corresponding presentation
        directive for KUMA's response lifecycle.

        This does not infer a medical or psychological state.
        It does not affect tool authority or execution.
        """

        text = str(
            message
            or ""
        ).strip()

        if not text:
            self._pending_emotion_directive = None
            return

        signal = (
            LanguageEmotionAnalyzer()
            .analyze(
                text
            )
        )

        directive = (
            KumaExpressionMapper()
            .map(
                signal
            )
        )

        print(
            "KUMA EMOTION → "
            f"primary={signal.primary.value} "
            f"tone={signal.tone.value} "
            f"intensity={signal.intensity:.2f} "
            f"confidence={signal.confidence:.2f}"
        )

        print(
            "KUMA EXPRESSION → "
            f"mode={directive.mode.value} "
            f"gesture={directive.gesture.value} "
            f"hold={directive.hold_ms}ms"
        )

        # Neutral conversation retains KUMA's normal speech
        # completion behavior instead of forcing an IDLE state.
        if signal.primary == KumaEmotion.NEUTRAL:
            self._pending_emotion_directive = None
            return

        self._pending_emotion_directive = (
            directive
        )


    def _present_pending_emotion(
        self,
    ) -> bool:
        """
        Present the conversational expression after KUMA finishes
        speaking.

        Runtime THINKING/WORKING/SPEAKING states remain higher
        priority while the task is active.
        """

        directive = getattr(
            self,
            "_pending_emotion_directive",
            None,
        )

        if directive is None:
            return False

        self._pending_emotion_directive = None

        self.body_controller.present_expression(
            directive
        )

        self._schedule_body_idle_reset(
            directive.hold_ms
        )

        return True


    # =========================================================
    # KUMA SPEECH / BODY LIFECYCLE
    # =========================================================

    @Slot()
    def _on_kuma_voice_ready(
        self,
    ):
        # Enable input only after Nova finishes one-time warm-up.

        # KUMA VOICE READY INPUT GUARD
        if not hasattr(
            self,
            "input",
        ):
            return
        self.input.setEnabled(
            True
        )

        self.input.setPlaceholderText(
            "Talk to me..."
        )

        print(
            "KUMA STARTUP → "
            "companion voice ready."
        )


    @Slot()
    def _on_kuma_speech_started(
        self,
    ):
        """
        KUMA's body visibly enters speech mode while audio is
        actually playing.
        """

        self._cancel_body_idle_reset()

        self.body_controller.present_avatar_snapshot(
            AvatarSnapshot(
                mode=AvatarMode.SPEAKING,
                expression=AvatarExpression.GENTLE,
                expression_intensity=0.35,
                gaze=AvatarGaze.USER,
                motion_energy=0.55,
                speech_active=True,
                reason="speech playback started",
            )
        )


    @Slot()
    def _on_kuma_speech_finished(
        self,
    ):
        """
        Celebrate completion briefly after KUMA finishes talking.
        """

        if self._present_pending_emotion():
            return

        self.body_controller.present_avatar_snapshot(
            AvatarSnapshot(
                mode=AvatarMode.SUCCESS,
                expression=AvatarExpression.HAPPY,
                expression_intensity=0.75,
                gaze=AvatarGaze.USER,
                motion_energy=0.45,
                reason="speech playback completed",
            )
        )

        self._schedule_body_idle_reset(
            1400
        )


    @Slot(str)
    def _on_kuma_speech_error(
        self,
        error,
    ):
        """
        Speech failure must never affect the underlying KUMA task.
        """

        print(
            "KUMA VOICE → "
            f"speech error: {error}"
        )

        self.body_controller.present_avatar_snapshot(
            AvatarSnapshot(
                mode=AvatarMode.ERROR,
                expression=AvatarExpression.ALERT,
                expression_intensity=0.70,
                gaze=AvatarGaze.USER,
                motion_energy=0.30,
                reason="speech playback failed",
            )
        )

        self._schedule_body_idle_reset(
            1400
        )


    # =========================================================
    # SEND MESSAGE
    # =========================================================

    def submit_user_turn_text(
        self,
        message,
        *,
        clear_input=False,
    ):
        """
        Schedule one ordinary textual KUMA user turn.

        This is the shared GUI scheduling seam for already-admitted text.
        It owns GUI presentation and KumaWorker creation, not speech
        recognition, transcript authority, tool permission, or runtime
        execution authority.

        True means exactly one KumaWorker was scheduled.
        False means no user turn was scheduled.

        TEXT SOURCE != EXECUTION AUTHORITY
        TEXT TURN SCHEDULING != TOOL PERMISSION
        GUI SCHEDULER != RUNTIME OWNER
        AUTHORITY = NONE
        """

        if type(
            message
        ) is not str:
            raise TypeError(
                "message must be str."
            )

        if type(
            clear_input
        ) is not bool:
            raise TypeError(
                "clear_input must be bool."
            )

        message = (
            message.strip()
        )

        if not message:
            return False

        # Prevent overlapping requests before any accepted-turn
        # presentation or emotion side effect occurs.
        if (
            self.worker is not None
            and self.worker.isRunning()
        ):
            return False

        # From this point onward the textual turn has been accepted
        # for ordinary GUI scheduling.
        self._capture_user_emotion(
            message
        )

        # A new request interrupts any previous spoken reply.
        self.speech.stop()

        # Keyboard submission owns its input-widget clear.
        # Voice-admitted text must not erase unrelated text that the
        # user may already be typing.
        if clear_input:
            self.input.clear()

        # -----------------------------------------------------
        # UI state
        # -----------------------------------------------------

        self.response.setText("")

        self._resize_companion_panel_for_response()

        self.status.setText(
            "Thinking..."
        )

        self.character.set_state(
            "thinking"
        )

        self.input.setEnabled(
            False
        )

        self.send_button.setEnabled(
            False
        )

        # Conversation persistence is owned by KumaAgent.

        self.current_response = ""

        # -----------------------------------------------------
        # Runtime
        # -----------------------------------------------------

        runtime = self.runtime

        if runtime is None:
            try:
                runtime = KumaGUIRuntime(
                    confirmation_callback=(
                        self.request_confirmation
                    ),
                    status_callback=None,
                )

                self.runtime = runtime

            except Exception as error:
                self.on_error(
                    str(
                        error
                    )
                )

                return False

        # -----------------------------------------------------
        # Worker
        # -----------------------------------------------------

        worker = KumaWorker(
            runtime,
            message,
        )

        self.worker = worker

        # -----------------------------------------------------
        # Signals
        # -----------------------------------------------------

        worker.status_changed.connect(
            self.on_status_changed
        )

        worker.status_changed.connect(
            self.body_controller.handle_runtime_status
        )

        worker.response_finished.connect(
            self.on_response
        )

        worker.error.connect(
            self.on_error
        )

        # IMPORTANT:
        # Cleanup only after QThread actually finishes.
        worker.finished.connect(
            self.on_worker_finished
        )

        # -----------------------------------------------------
        # Start
        # -----------------------------------------------------

        self._cancel_body_idle_reset()

        self.body_controller.present_avatar_snapshot(
            AvatarSnapshot(
                mode=AvatarMode.THINKING,
                expression=AvatarExpression.FOCUSED,
                expression_intensity=0.65,
                gaze=AvatarGaze.USER,
                motion_energy=0.45,
                reason="request started",
            )
        )

        worker.start()

        return True

    def send_message(self):
        """
        Read keyboard text and schedule it through the canonical
        ordinary textual user-turn seam.

        Only one worker may run at a time.
        """

        message = (
            self.input
            .text()
            .strip()
        )

        self.submit_user_turn_text(
            message,
            clear_input=True,
        )

    # =========================================================
    # FLOATING BODY LIFECYCLE
    # =========================================================

    def _cancel_body_idle_reset(
        self,
    ):
        """
        Invalidate any previously scheduled terminal-state reset.
        """

        self._body_idle_generation += 1

    def _schedule_body_idle_reset(
        self,
        delay_ms=1800,
    ):
        """
        Preserve HAPPY / ALERT briefly, then return KUMA to IDLE.

        A generation token prevents a delayed callback from an
        older request from overwriting a newer live body state.
        """

        self._body_idle_generation += 1

        generation = (
            self._body_idle_generation
        )

        QTimer.singleShot(
            delay_ms,
            lambda:
            self._restore_body_idle_if_current(
                generation
            ),
        )

    def _restore_body_idle_if_current(
        self,
        generation,
    ):
        if (
            generation
            != self._body_idle_generation
        ):
            return

        self.body_controller.present_avatar_snapshot(
            AvatarSnapshot(
                mode=AvatarMode.IDLE,
                expression=AvatarExpression.NEUTRAL,
                expression_intensity=0.0,
                gaze=AvatarGaze.FORWARD,
                motion_energy=0.0,
                reason="terminal presentation expired",
            )
        )

    def _response_indicates_failure(
        self,
        response,
    ):
        """
        Presentation-only failure classification.

        This grants no execution authority and changes no mission
        result. It exists only so KUMA Mini can visually distinguish
        a successful completion from a failed/blocked completion.
        """

        text = str(
            response
        ).strip().lower()

        status_text = (
            self.status.text()
            .strip()
            .lower()
        )

        status_failure_markers = (
            "error",
            "failed",
            "blocked",
            "failure",
        )

        if any(
            marker in status_text
            for marker in status_failure_markers
        ):
            return True

        response_failure_markers = (
            "could not complete",
            "couldn't complete",
            "could not safely",
            "cannot reliably",
            "unable to complete",
            "was blocked",
            "is blocked",
            "failed due to",
            "analysis failed",
            "execution failed",
            "evidence_expired",
        )

        return any(
            marker in text
            for marker in response_failure_markers
        )

    # =========================================================
    # STATUS UPDATE
    # =========================================================

    @Slot(str)
    def on_status_changed(
        self,
        status,
    ):
        """
        Handle worker status updates safely on the GUI thread.
        """

        status = str(
            status
        )

        self.status.setText(
            status
        )

        normalized = (
            status.lower()
        )

        # -----------------------------------------------------
        # Thinking / execution states
        # -----------------------------------------------------

        if (
            "thinking" in normalized
            or "executing" in normalized
            or "verifying" in normalized
            or "waiting" in normalized
            or "approval" in normalized
            or "calling" in normalized
        ):
            self.character.set_state(
                "thinking"
            )

        # -----------------------------------------------------
        # Error
        # -----------------------------------------------------

        elif "error" in normalized:
            self.character.set_state(
                "idle"
            )

    # =========================================================
    # RESPONSE COMPLETE
    # =========================================================

    @Slot(str)
    def on_response(
        self,
        response,
    ):
        """
        Display the final KUMA response.

        Note:
        The QThread may still be in the final few milliseconds of
        its run() method. Actual worker cleanup happens through
        on_worker_finished().
        """

        self.current_response = str(
            response
        )

        self.response.setText(
            self.current_response
        )

        self._resize_companion_panel_for_response()

        if self.isVisible():
            self._position_panel_near_body()

        # Response persistence is owned by KumaAgent.

        # -----------------------------------------------------
        # KUMA VOICE
        # -----------------------------------------------------

        if self.current_response:
            self.speech.speak(
                self.current_response
            )

        # -----------------------------------------------------
        # Floating-body terminal state
        # -----------------------------------------------------

        speech_active = bool(
            self.current_response
            and self.speech.enabled
        )

        if self._response_indicates_failure(
            self.current_response
        ):
            self.body_controller.present_avatar_snapshot(
                AvatarSnapshot(
                    mode=AvatarMode.ERROR,
                    expression=AvatarExpression.ALERT,
                    expression_intensity=0.90,
                    gaze=AvatarGaze.USER,
                    motion_energy=0.55,
                    reason="response classified as failure",
                )
            )

            self._schedule_body_idle_reset()

        elif not speech_active:
            self.body_controller.present_avatar_snapshot(
                AvatarSnapshot(
                    mode=AvatarMode.SUCCESS,
                    expression=AvatarExpression.HAPPY,
                    expression_intensity=0.80,
                    gaze=AvatarGaze.USER,
                    motion_energy=0.50,
                    reason="response completed without speech",
                )
            )

            self._schedule_body_idle_reset()

        # -----------------------------------------------------
        # Restore UI
        # -----------------------------------------------------

        self.current_response = ""

        self.character.set_state(
            "idle"
        )

        self.status.setText(
            "Online"
        )

        self.input.setEnabled(
            True
        )

        self.send_button.setEnabled(
            True
        )

        self.input.setFocus()

    # =========================================================
    # ERROR
    # =========================================================

    @Slot(str)
    def on_error(
        self,
        error,
    ):
        """
        Handle worker/runtime errors.
        """

        self.current_response = ""

        self.response.setText(
            f"KUMA ERROR: {error}"
        )

        self._resize_companion_panel_for_response()

        if self.isVisible():
            self._position_panel_near_body()

        self.character.set_state(
            "idle"
        )

        self.body_controller.present_avatar_snapshot(
            AvatarSnapshot(
                mode=AvatarMode.ERROR,
                expression=AvatarExpression.ALERT,
                expression_intensity=1.0,
                gaze=AvatarGaze.USER,
                motion_energy=0.60,
                reason="worker or runtime error",
            )
        )

        self._schedule_body_idle_reset()

        self.status.setText(
            "Error"
        )

        self.input.setEnabled(
            True
        )

        self.send_button.setEnabled(
            True
        )

        self.input.setFocus()

    # =========================================================
    # WORKER FINISHED
    # =========================================================

    @Slot()
    def on_worker_finished(self):
        """
        Called when the QThread has actually finished.

        This fixes the old cleanup race where on_response()
        could execute while worker.isRunning() was still True.
        """

        worker = self.sender()

        if worker is None:
            return

        if worker is self.worker:
            self.worker = None

        worker.deleteLater()

    # =========================================================
    # WINDOW CLOSE
    # =========================================================

    def closeEvent(
        self,
        event,
    ):
        """
        Safely close KUMA.

        We do NOT force-kill the worker because the worker may be:

        - running Ollama
        - executing a tool
        - waiting for confirmation

        Killing it abruptly can leave resources or state inconsistent.
        """

        self._closing = True

        worker = self.worker

        if (
            worker is not None
            and worker.isRunning()
        ):
            # Ask the worker to stop if its implementation supports
            # interruption checks.
            worker.requestInterruption()

            # Do not block the GUI thread indefinitely.
            #
            # If the worker cannot stop immediately, prevent closing
            # rather than leaving a live QThread behind.
            if not worker.wait(1000):
                self._closing = False

                QMessageBox.warning(
                    self,
                    "KUMA",
                    (
                        "KUMA is still finishing "
                        "an operation.\n\n"
                        "Please wait a moment and close again."
                    ),
                )

                event.ignore()
                return

        # The worker is now quiescent. Remove it from the
        # executable GUI lifecycle before physical cleanup.
        self.worker = None

        # -------------------------------------------------
        # NORMAL-SHUTDOWN FINGER CLEANUP
        # -------------------------------------------------
        #
        # Never silently abandon a KUMA-owned HELD or UNKNOWN
        # mouse-button state. This runs only after the worker
        # has stopped, so no new KUMA body action can race
        # with the shutdown release.
        # -------------------------------------------------

        cleanup_error = ""


        # Stop KUMA speech before runtime teardown.
        self.speech.shutdown()

        runtime = self.runtime

        if runtime is not None:

            try:

                cleanup_result = (
                    runtime.shutdown()
                )

                if (
                    cleanup_result is None
                    or not getattr(
                        cleanup_result,
                        "success",
                        False,
                    )
                ):

                    cleanup_error = str(
                        getattr(
                            cleanup_result,
                            "error",
                            "",
                        )
                        or (
                            "KUMA returned an invalid "
                            "shutdown-cleanup result."
                        )
                    )

            except BaseException as error:

                cleanup_error = (
                    "KUMA shutdown cleanup raised "
                    f"{type(error).__name__}: "
                    f"{error}"
                )

        if cleanup_error:

            self._closing = False

            QMessageBox.warning(
                self,
                "KUMA Safety",
                (
                    "KUMA could not safely release its "
                    "mouse button before shutdown.\n\n"
                    f"{cleanup_error}\n\n"
                    "The window will remain open so you "
                    "can retry or release the button manually."
                ),
            )

            event.ignore()
            return

        event.accept()

        # =========================================================
# APPLICATION ENTRY POINT
# =========================================================

if __name__ == "__main__":

    from PySide6.QtWidgets import QApplication
    import sys

    app = QApplication(sys.argv)

    window = KumaWindow()
    window.show()

    sys.exit(
        app.exec()
    )
