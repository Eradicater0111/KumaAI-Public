import base64
import json
from pathlib import Path

from app.ui_observation import (
    _focus_target_worker as worker,
)
from app.ui_observation.focus_target_correlation import (
    focus_target_correlation_from_dict,
    focus_target_selector_to_dict,
)
from app.ui_observation.target_resolution import (
    StructuredUITargetSelector,
)


def selector_token():
    payload = json.dumps(
        focus_target_selector_to_dict(
            StructuredUITargetSelector(
                role="AXTextField",
                text="Search",
            )
        ),
        allow_nan=False,
        separators=(
            ",",
            ":",
        ),
    ).encode(
        "utf-8"
    )

    return base64.b64encode(
        payload
    ).decode(
        "ascii"
    )


def test_worker_non_darwin_emits_strict_unknown(
    monkeypatch,
    capsys,
):
    monkeypatch.setattr(
        worker.sys,
        "platform",
        "linux",
    )

    monkeypatch.setattr(
        worker.sys,
        "argv",
        [
            str(
                worker.__file__
            ),
            "123",
            "test.app",
            selector_token(),
            "1024",
            "16",
            "128",
        ],
    )

    worker.main()

    output = (
        capsys.readouterr()
        .out
        .strip()
    )

    payload = json.loads(
        output
    )

    result = (
        focus_target_correlation_from_dict(
            payload
        )
    )

    assert result.diagnostics == (
        "unsupported_platform",
    )

    assert (
        result.expected_application.pid
        == 123
    )

    assert (
        result.expected_application.bundle_id
        == "test.app"
    )


def test_worker_requires_exact_argument_count(
    monkeypatch,
):
    monkeypatch.setattr(
        worker.sys,
        "argv",
        [
            "worker",
        ],
    )

    try:
        worker.main()
    except SystemExit as error:
        assert error.code == 2
    else:
        raise AssertionError(
            "Worker accepted invalid argv."
        )


def test_worker_rejects_malformed_selector_token():
    try:
        worker._decode_selector(
            "***not-base64***"
        )
    except Exception:
        pass
    else:
        raise AssertionError(
            "Malformed selector token was accepted."
        )


def test_worker_source_is_fixed_purpose_and_read_only():
    text = Path(
        worker.__file__
    ).read_text(
        encoding="utf-8"
    )

    forbidden = (
        "input(",
        "eval(",
        "exec(",
        "AXUIElementSetAttributeValue",
        "AXUIElementPerformAction",
        "pyautogui",
        "computer_tools",
        "mission_service",
    )

    for marker in forbidden:
        assert marker not in text
