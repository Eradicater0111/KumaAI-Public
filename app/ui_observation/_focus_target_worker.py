"""Private fixed-purpose worker for one KUMA 8D2 native correlation read.

Native AX references and CF identity remain inside this isolated process.
Only strict JSON-safe correlation evidence crosses the process boundary.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
import sys
import time

sys.path.insert(
    0,
    str(
        Path(
            __file__
        ).resolve().parents[2]
    ),
)

from app.desktop.contracts import (
    ApplicationIdentity,
)
from app.ui_observation.focus_target_correlation import (
    collect_focus_target_correlation,
    focus_target_correlation_to_dict,
    focus_target_selector_from_dict,
    unknown_focus_target_correlation,
    validate_focus_target_limits,
)


MAX_SELECTOR_WIRE_BYTES = 16 * 1024


def _decode_selector(
    token,
):
    if (
        type(token) is not str
        or not token
    ):
        raise ValueError(
            "Invalid selector token."
        )

    raw = base64.b64decode(
        token.encode(
            "ascii"
        ),
        validate=True,
    )

    if (
        not raw
        or len(raw)
        > MAX_SELECTOR_WIRE_BYTES
    ):
        raise ValueError(
            "Selector wire payload exceeded bound."
        )

    payload = json.loads(
        raw.decode(
            "utf-8"
        )
    )

    return (
        focus_target_selector_from_dict(
            payload
        )
    )


def main():
    if len(
        sys.argv
    ) != 7:
        raise SystemExit(
            2
        )

    expected = ApplicationIdentity(
        pid=int(
            sys.argv[1]
        ),
        bundle_id=sys.argv[2],
    )

    selector = _decode_selector(
        sys.argv[3]
    )

    max_nodes = int(
        sys.argv[4]
    )

    max_depth = int(
        sys.argv[5]
    )

    max_children = int(
        sys.argv[6]
    )

    validate_focus_target_limits(
        max_nodes,
        max_depth,
        max_children,
    )

    captured_at = (
        time.monotonic()
    )

    if sys.platform != "darwin":
        result = (
            unknown_focus_target_correlation(
                "unsupported_platform",
                expected_application=expected,
                selector=selector,
                captured_at_monotonic=(
                    captured_at
                ),
            )
        )

    else:
        try:
            from app.ui_observation.focus_target_macos import (
                MacOSFocusTargetProvider,
            )

            provider = (
                MacOSFocusTargetProvider()
            )

        except ImportError:
            result = (
                unknown_focus_target_correlation(
                    "native_api_unavailable",
                    expected_application=expected,
                    selector=selector,
                    captured_at_monotonic=(
                        captured_at
                    ),
                )
            )

        except Exception:
            result = (
                unknown_focus_target_correlation(
                    "collection_failed",
                    expected_application=expected,
                    selector=selector,
                    captured_at_monotonic=(
                        captured_at
                    ),
                )
            )

        else:
            try:
                result = (
                    collect_focus_target_correlation(
                        provider,
                        expected_application=expected,
                        selector=selector,
                        max_nodes=max_nodes,
                        max_depth=max_depth,
                        max_children=max_children,
                    )
                )

            except Exception:
                result = (
                    unknown_focus_target_correlation(
                        "collection_failed",
                        expected_application=expected,
                        selector=selector,
                        captured_at_monotonic=(
                            captured_at
                        ),
                    )
                )

    output = json.dumps(
        focus_target_correlation_to_dict(
            result
        ),
        allow_nan=False,
        separators=(
            ",",
            ":",
        ),
    )

    print(
        output
    )


if __name__ == "__main__":
    main()
