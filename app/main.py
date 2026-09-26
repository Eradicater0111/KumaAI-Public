import sys

from PySide6.QtWidgets import QApplication

from app.ui.window import KumaWindow
from app.voice.voice_live_runtime import (
    attach_kuma_voice_runtime,
)
from app.voice.stt_live_turn_binding import (
    attach_kuma_stt_turn_admission,
)



def main():
    app = QApplication(sys.argv)

    window = KumaWindow()

    voice_runtime = attach_kuma_voice_runtime(
        window
    )

    stt_turn_binding = (
        attach_kuma_stt_turn_admission(
            window
        )
    )

    app.aboutToQuit.connect(
        stt_turn_binding.close
    )

    app.aboutToQuit.connect(
        voice_runtime.close
    )
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
