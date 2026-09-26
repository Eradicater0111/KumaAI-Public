"""Explicit local diagnostic: python -m app.desktop.diagnostic."""

import argparse
import json

from app.desktop.runtime import collect_desktop_context


def main(argv=None):
    parser = argparse.ArgumentParser(description="Read KUMA desktop context once.")
    parser.add_argument("--include-titles", action="store_true",
                        help="Include potentially private window titles in stdout.")
    parser.add_argument("--timeout", type=float, default=3.0)
    parser.add_argument("--max-windows", type=int, default=32)
    args = parser.parse_args(argv)
    try:
        result = collect_desktop_context(
            timeout_seconds=args.timeout, max_windows=args.max_windows,
        )
    except ValueError as error:
        parser.error(str(error))
    payload = result.to_dict(include_titles=args.include_titles)
    payload["titles_included"] = args.include_titles
    print(json.dumps(payload, indent=2, ensure_ascii=True, allow_nan=False))
    return {"available": 0, "partial": 2, "unavailable": 3}[result.status]


if __name__ == "__main__":
    raise SystemExit(main())
