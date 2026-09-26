from __future__ import annotations

import ast
import base64
import importlib.util
from pathlib import Path
import struct

import numpy as np
import pytest


ROOT = (
    Path(__file__)
    .resolve()
    .parents[2]
)

WORKER = (
    ROOT
    / "app"
    / "voice"
    / "stt_recognizer_worker.py"
)


def load_worker():
    spec = (
        importlib.util.spec_from_file_location(
            "kuma_stt_recognizer_worker_test",
            WORKER,
        )
    )

    module = (
        importlib.util.module_from_spec(
            spec
        )
    )

    spec.loader.exec_module(
        module
    )

    return module


@pytest.fixture()
def worker():
    return load_worker()


@pytest.fixture()
def local_model(
    tmp_path,
):
    model = (
        tmp_path
        / "whisper-model"
    )

    model.mkdir()

    (
        model
        / "config.json"
    ).write_text(
        "{}"
    )

    (
        model
        / "weights.npz"
    ).write_bytes(
        b"synthetic"
    )

    return model


def test_worker_import_does_not_require_mlx_whisper(
    worker,
):
    assert callable(
        worker.transcribe_pcm
    )


def test_worker_has_explicit_zero_authority_markers():
    source = (
        WORKER.read_text()
    )

    for marker in (
        "MODEL LOAD != MICROPHONE CONSENT",
        "MODEL DOWNLOAD != APP STARTUP",
        "RECOGNIZER RESULT != USER TURN",
        "RECOGNIZER PROCESS != RUNTIME OWNER",
        "TRANSCRIPT TEXT != TOOL PERMISSION",
        "AUTHORITY = NONE",
    ):
        assert marker in source


def test_worker_has_no_kuma_runtime_or_gui_imports():
    tree = ast.parse(
        WORKER.read_text(),
        filename=str(
            WORKER
        ),
    )

    modules = []

    for node in ast.walk(
        tree
    ):
        if isinstance(
            node,
            ast.Import,
        ):
            modules.extend(
                alias.name
                for alias in node.names
            )

        elif (
            isinstance(
                node,
                ast.ImportFrom,
            )
            and node.module
        ):
            modules.append(
                node.module
            )

    forbidden = (
        "app.agent",
        "app.memory",
        "app.integration",
        "app.realtime",
        "app.ui",
        "PySide6",
    )

    assert all(
        not name.startswith(
            forbidden
        )
        for name in modules
    )


def test_mlx_whisper_import_is_lazy():
    source = (
        WORKER.read_text()
    )

    tree = ast.parse(
        source,
        filename=str(
            WORKER
        ),
    )

    module_level_imports = []

    for node in tree.body:
        if isinstance(
            node,
            ast.Import,
        ):
            module_level_imports.extend(
                alias.name
                for alias in node.names
            )

        elif (
            isinstance(
                node,
                ast.ImportFrom,
            )
            and node.module
        ):
            module_level_imports.append(
                node.module
            )

    assert (
        "mlx_whisper"
        not in module_level_imports
    )


def test_model_path_must_be_absolute_local_directory(
    worker,
    tmp_path,
):
    with pytest.raises(
        ValueError
    ):
        worker._local_model_path(
            "mlx-community/whisper-turbo"
        )

    with pytest.raises(
        ValueError
    ):
        worker._local_model_path(
            "https://example.com/model"
        )

    with pytest.raises(
        ValueError
    ):
        worker._local_model_path(
            tmp_path
            / "missing"
        )


def test_model_path_requires_local_model_files(
    worker,
    tmp_path,
):
    model = (
        tmp_path
        / "model"
    )

    model.mkdir()

    with pytest.raises(
        ValueError
    ):
        worker._local_model_path(
            model
        )


def test_complete_local_model_is_accepted(
    worker,
    local_model,
):
    assert (
        worker._local_model_path(
            local_model
        )
        == local_model.resolve()
    )


def test_weights_safetensors_local_model_is_accepted(
    worker,
    tmp_path,
):
    model = (
        tmp_path
        / "safetensors-model"
    )

    model.mkdir()

    (
        model
        / "config.json"
    ).write_text(
        "{}"
    )

    (
        model
        / "weights.safetensors"
    ).write_bytes(
        b"synthetic"
    )

    assert (
        worker._local_model_path(
            model
        )
        == model.resolve()
    )



def test_model_safetensors_only_is_rejected(
    worker,
    tmp_path,
):
    model = (
        tmp_path
        / "wrong-layout"
    )

    model.mkdir()

    (
        model
        / "config.json"
    ).write_text(
        "{}"
    )

    (
        model
        / "model.safetensors"
    ).write_bytes(
        b"synthetic"
    )

    with pytest.raises(
        ValueError
    ):
        worker._local_model_path(
            model
        )



def test_worker_requires_config_with_valid_weights(
    worker,
    tmp_path,
):
    model = (
        tmp_path
        / "missing-config"
    )

    model.mkdir()

    (
        model
        / "weights.npz"
    ).write_bytes(
        b"synthetic"
    )

    with pytest.raises(
        ValueError
    ):
        worker._local_model_path(
            model
        )



def test_bounded_base64_decode_round_trips(
    worker,
):
    payload = struct.pack(
        "<hhh",
        -32768,
        0,
        32767,
    )

    encoded = (
        base64.b64encode(
            payload
        ).decode(
            "ascii"
        )
    )

    assert (
        worker.decode_pcm_request(
            encoded
        )
        == payload
    )


@pytest.mark.parametrize(
    "encoded",
    (
        "",
        "not-base64!!!",
        base64.b64encode(
            b"\x00"
        ).decode(
            "ascii"
        ),
    ),
)
def test_invalid_pcm_request_rejected(
    worker,
    encoded,
):
    with pytest.raises(
        ValueError
    ):
        worker.decode_pcm_request(
            encoded
        )


def test_pcm_to_float32_is_in_memory_and_scaled(
    worker,
):
    payload = struct.pack(
        "<hhh",
        -32768,
        0,
        32767,
    )

    waveform = (
        worker
        .pcm_s16le_to_float32(
            payload
        )
    )

    assert isinstance(
        waveform,
        np.ndarray,
    )

    assert (
        waveform.dtype
        == np.float32
    )

    assert waveform.tolist() == pytest.approx(
        [
            -1.0,
            0.0,
            32767 / 32768.0,
        ]
    )


def test_transcribe_passes_numpy_waveform_and_local_path(
    worker,
    local_model,
):
    calls = []

    class Provider:
        @staticmethod
        def transcribe(
            audio,
            **kwargs,
        ):
            calls.append(
                (
                    audio,
                    kwargs,
                )
            )

            return {
                "text": "  hello   KUMA  "
            }

    text = (
        worker.transcribe_pcm(
            struct.pack(
                "<hh",
                1000,
                -1000,
            ),
            local_model,
            provider=Provider,
        )
    )

    assert text == "hello KUMA"

    assert len(
        calls
    ) == 1

    audio, kwargs = (
        calls[0]
    )

    assert isinstance(
        audio,
        np.ndarray,
    )

    assert (
        kwargs[
            "path_or_hf_repo"
        ]
        == str(
            local_model.resolve()
        )
    )

    assert (
        kwargs[
            "verbose"
        ]
        is False
    )


def test_transcribe_redirects_provider_stdout_to_stderr(
    worker,
    local_model,
    capsys,
):
    payload = struct.pack(
        "<hhh",
        1000,
        0,
        -1000,
    )

    class NoisyProvider:
        @staticmethod
        def transcribe(
            audio,
            **kwargs,
        ):
            print(
                "PROVIDER STDOUT MUST NOT "
                "ENTER KUMA PROTOCOL"
            )

            return {
                "text": "hello KUMA",
            }

    text = worker.transcribe_pcm(
        payload,
        local_model,
        provider=NoisyProvider(),
    )

    captured = (
        capsys.readouterr()
    )

    assert (
        text
        == "hello KUMA"
    )

    assert (
        "PROVIDER STDOUT MUST NOT "
        "ENTER KUMA PROTOCOL"
        not in captured.out
    )

    assert (
        "PROVIDER STDOUT MUST NOT "
        "ENTER KUMA PROTOCOL"
        in captured.err
    )



def test_transcribe_rejects_empty_text(
    worker,
    local_model,
):
    class Provider:
        @staticmethod
        def transcribe(
            *_args,
            **_kwargs,
        ):
            return {
                "text": "   "
            }

    with pytest.raises(
        ValueError
    ):
        worker.transcribe_pcm(
            struct.pack(
                "<h",
                0,
            ),
            local_model,
            provider=Provider,
        )


def test_worker_uses_no_temp_audio_or_file_write_surface():
    source = (
        WORKER.read_text()
    )

    for forbidden in (
        "tempfile",
        "NamedTemporaryFile",
        "write_bytes",
        "soundfile",
        "sf.write",
        "wave.open",
    ):
        assert (
            forbidden
            not in source
        )


def test_worker_protocol_never_emits_raw_audio_key():
    source = (
        WORKER.read_text()
    )

    assert (
        '"audio_b64":'
        not in source
    )
