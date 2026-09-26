"""Private fixed-purpose subprocess entry point. No model-selected code."""

import json
from pathlib import Path
import sys
import time

# -I ignores PYTHONPATH and the working directory. Import only this checkout.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.desktop.collector import assemble_snapshot
from app.desktop.contracts import unavailable


def main():
    captured_at = time.monotonic()
    if sys.platform != "darwin":
        result = unavailable("unsupported_platform", captured_at)
    else:
        try:
            from app.desktop.macos import MacOSDesktopProvider
            provider = MacOSDesktopProvider()
        except ImportError:
            result = unavailable("native_api_unavailable", captured_at)
        except Exception:
            result = unavailable("collection_failed", captured_at)
        else:
            try:
                result = assemble_snapshot(provider, max_windows=int(sys.argv[1]))
            except Exception:
                result = unavailable("collection_failed", captured_at)
    # Private IPC only. Presentation separately redacts titles by default.
    print(json.dumps(result.to_dict(include_titles=True), allow_nan=False))


if __name__ == "__main__":
    main()
