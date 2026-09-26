"""Private fixed-purpose worker for one native focused-AX read.

The native AX object and CFEqual identity checks live only inside this isolated
process. Only the immutable FocusedUIObservation JSON contract crosses IPC.
"""

import json
from pathlib import Path
import sys
import time


sys.path.insert(
    0,
    str(
        Path(__file__)
        .resolve()
        .parents[2]
    ),
)


from app.desktop.contracts import (
    ApplicationIdentity,
)
from app.ui_observation.focus_collector import (
    collect_focused_ui,
)
from app.ui_observation.focus_contracts import (
    unavailable_focus,
)


def main():
    captured_at = time.monotonic()

    if sys.platform != "darwin":
        result = unavailable_focus(
            "unsupported_platform",
            captured_at,
        )

    else:
        try:
            expected = ApplicationIdentity(
                pid=int(
                    sys.argv[1]
                ),
                bundle_id=sys.argv[2],
            )

            from app.ui_observation.focus_macos import (
                MacOSFocusProvider,
            )

            provider = (
                MacOSFocusProvider()
            )

        except ImportError:
            result = unavailable_focus(
                "native_api_unavailable",
                captured_at,
            )

        except Exception:
            result = unavailable_focus(
                "collection_failed",
                captured_at,
            )

        else:
            try:
                result = collect_focused_ui(
                    provider,
                    expected_application=expected,
                )

            except Exception:
                result = unavailable_focus(
                    "collection_failed",
                    captured_at,
                )

    print(
        json.dumps(
            result.to_dict(),
            allow_nan=False,
        )
    )


if __name__ == "__main__":
    main()
