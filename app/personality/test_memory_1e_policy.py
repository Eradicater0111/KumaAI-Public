from app.personality.personality import KUMA_PERSONALITY


def test_memory_prompt_requires_explicit_current_request():
    text = KUMA_PERSONALITY.lower()
    assert (
        "only call remember when the current user message explicitly asks kuma"
        in text
    )


def test_memory_prompt_no_longer_allows_implicit_persistence():
    text = KUMA_PERSONALITY.lower()
    assert "you may also use remember" not in text
    assert "the user provides a stable personal preference" not in text
    assert "the user provides a stable project detail" not in text


def test_memory_prompt_distinguishes_candidate_from_persistence():
    text = KUMA_PERSONALITY.lower()
    assert "memory candidate" in text
    assert "do not persist it" in text
