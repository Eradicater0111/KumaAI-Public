import ast
from pathlib import Path


WORKER = (
    Path(__file__)
    .with_name(
        "_focus_worker.py"
    )
)


def source():
    return WORKER.read_text()


def test_focus_worker_is_fixed_purpose_contract_bridge():
    text = source()

    assert (
        "collect_focused_ui"
        in text
    )

    assert (
        "MacOSFocusProvider"
        in text
    )

    tree = ast.parse(
        text
    )

    # The contract name may appear in comments/docstrings.
    # What matters is that the worker does not import,
    # construct, or otherwise reference that class in
    # executable syntax.
    assert not any(
        isinstance(
            node,
            ast.Name,
        )
        and node.id
        == "FocusedUIObservation"
        for node in ast.walk(
            tree
        )
    )

    assert not any(
        isinstance(
            node,
            ast.ImportFrom,
        )
        and node.module
        == "app.ui_observation.focus_contracts"
        and any(
            alias.name
            == "FocusedUIObservation"
            for alias in node.names
        )
        for node in ast.walk(
            tree
        )
    )

    assert (
        "result.to_dict()"
        in text
    )

    assert (
        'json.dumps('
        in text
    )


def test_focus_worker_has_no_action_or_authority_surface():
    text = source()

    forbidden = (
        "pyautogui",
        "ollama",
        "google.genai",
        "AXUIElementSetAttributeValue",
        "AXUIElementPerformAction",
        "request_confirmation",
        "semantic_target_verified",
        "register_tool",
        "KUMA_TOOLS",
        "type_text(",
        "press_key(",
        "click(",
        "mouseDown",
        "mouseUp",
    )

    for marker in forbidden:
        assert marker not in text


def test_focus_worker_uses_isolated_expected_application_inputs_only():
    text = source()

    assert (
        "sys.argv[1]"
        in text
    )

    assert (
        "sys.argv[2]"
        in text
    )

    assert (
        "ApplicationIdentity"
        in text
    )

    assert (
        "expected_application=expected"
        in text
    )


def test_focus_worker_sanitizes_native_failures():
    text = source()

    assert (
        '"native_api_unavailable"'
        in text
    )

    assert (
        '"collection_failed"'
        in text
    )

    assert (
        "traceback"
        not in text.lower()
    )
