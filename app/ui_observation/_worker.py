"""Private fixed-purpose worker for one bounded Accessibility-tree read."""

import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.desktop.contracts import ApplicationIdentity
from app.ui_observation.collector import assemble_structured_ui_snapshot
from app.ui_observation.contracts import unavailable


def main():
    captured_at = time.monotonic()
    if sys.platform != "darwin":
        result = unavailable("unsupported_platform", captured_at)
    else:
        try:
            expected = ApplicationIdentity(pid=int(sys.argv[1]), bundle_id=sys.argv[2])
            max_nodes = int(sys.argv[3])
            max_depth = int(sys.argv[4])
            max_children = int(sys.argv[5])
            from app.ui_observation.macos import MacOSAccessibilityProvider
            provider = MacOSAccessibilityProvider()
        except ImportError:
            result = unavailable("native_api_unavailable", captured_at)
        except Exception:
            result = unavailable("collection_failed", captured_at)
        else:
            try:
                result = assemble_structured_ui_snapshot(
                    provider,
                    expected_application=expected,
                    max_nodes=max_nodes,
                    max_depth=max_depth,
                    max_children=max_children,
                )
            except Exception:
                result = unavailable("collection_failed", captured_at)
    print(json.dumps(result.to_dict(include_text=True), allow_nan=False))


if __name__ == "__main__":
    main()
