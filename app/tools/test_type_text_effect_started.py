from app.tools.computer_tools import (
    type_text,
)


def test_validation_failure_has_not_started_effect(
    monkeypatch,
):
    calls = []

    monkeypatch.setattr(
        "app.tools.computer_tools.pyautogui.write",
        lambda *args, **kwargs: calls.append(
            (
                args,
                kwargs,
            )
        ),
    )

    result = type_text(
        ""
    )

    assert not result.success
    assert result.effect_started is False
    assert calls == []


def test_successful_write_marks_effect_started(
    monkeypatch,
):
    calls = []

    def write(
        text,
        *,
        interval,
    ):
        calls.append(
            (
                text,
                interval,
            )
        )

    monkeypatch.setattr(
        "app.tools.computer_tools.pyautogui.write",
        write,
    )

    result = type_text(
        "hello",
        interval=0.01,
    )

    assert result.success
    assert result.effect_started is True
    assert calls == [
        (
            "hello",
            0.01,
        )
    ]


def test_write_exception_still_marks_effect_started(
    monkeypatch,
):
    def write(
        _text,
        *,
        interval,
    ):
        assert interval == 0.01

        raise RuntimeError(
            "synthetic write failure"
        )

    monkeypatch.setattr(
        "app.tools.computer_tools.pyautogui.write",
        write,
    )

    result = type_text(
        "hello",
        interval=0.01,
    )

    assert not result.success
    assert result.effect_started is True
    assert (
        "synthetic write failure"
        in str(
            result.error
        )
    )


def test_exact_whitespace_still_reaches_emitter(
    monkeypatch,
):
    seen = []

    monkeypatch.setattr(
        "app.tools.computer_tools.pyautogui.write",
        lambda text, *, interval: (
            seen.append(
                (
                    text,
                    interval,
                )
            )
        ),
    )

    payload = (
        "hello   world"
    )

    result = type_text(
        payload,
        interval=0.01,
    )

    assert result.success
    assert result.effect_started is True
    assert seen[0][0] == payload
