import inspect

from app.agent.gui_perception_refresh import (
    BOOTSTRAP_STATUS_AVAILABLE,
    BOOTSTRAP_STATUS_UNKNOWN,
    StructuredUIScreenBootstrapResult,
    bootstrap_structured_ui_screen_context,
)


def test_bootstrap_is_keyword_only_and_has_no_model_target_inputs():
    signature = inspect.signature(
        bootstrap_structured_ui_screen_context
    )

    parameters = signature.parameters

    forbidden = {
        "screen_observation_id",
        "observation_id",
        "x",
        "y",
        "text",
        "target",
        "arguments",
    }

    assert not (
        forbidden
        & set(parameters)
    )

    for parameter in parameters.values():
        assert (
            parameter.kind
            is inspect.Parameter.KEYWORD_ONLY
        )


def test_bootstrap_has_injectable_read_only_collectors():
    parameters = (
        inspect.signature(
            bootstrap_structured_ui_screen_context
        )
        .parameters
    )

    assert (
        "desktop_collector"
        in parameters
    )

    assert (
        "screen_capture"
        in parameters
    )

    assert (
        "structured_ui_collector"
        in parameters
    )

    assert (
        "native_screen_size"
        in parameters
    )

    assert (
        "image_analyzer"
        in parameters
    )


def test_invalid_context_store_fails_closed_before_collection():
    calls = []

    def unexpected(*args, **kwargs):
        calls.append(
            (
                args,
                kwargs,
            )
        )

        raise AssertionError(
            "collector must not run"
        )

    result = (
        bootstrap_structured_ui_screen_context(
            context_store=object(),
            desktop_collector=unexpected,
            screen_capture=unexpected,
            structured_ui_collector=unexpected,
            native_screen_size=unexpected,
            image_analyzer=unexpected,
        )
    )

    assert (
        result.status
        == BOOTSTRAP_STATUS_UNKNOWN
    )

    assert not result.available

    assert result.context is None

    assert result.diagnostics == (
        "invalid_context_store",
    )

    assert calls == []


def test_bootstrap_result_rejects_unknown_with_context():
    try:
        StructuredUIScreenBootstrapResult(
            status=BOOTSTRAP_STATUS_UNKNOWN,
            context=object(),
            diagnostics=(
                "screen_capture_unavailable",
            ),
        )
    except ValueError:
        pass
    else:
        raise AssertionError(
            "unknown bootstrap carried trusted context"
        )


def test_bootstrap_status_constants_are_exact_strings():
    assert (
        BOOTSTRAP_STATUS_AVAILABLE
        == "available"
    )

    assert (
        BOOTSTRAP_STATUS_UNKNOWN
        == "unknown"
    )
