"""Bounded entry point for a single local desktop observation."""

import json
import math
import os
from pathlib import Path
import selectors
import subprocess
import sys
import threading
import time

from app.desktop.collector import validate_window_limit
from app.desktop.contracts import DesktopContextObservation, unavailable


# 64 titles × 1024 code points × 12 JSON bytes (astral Unicode),
# plus bounded app metadata, geometry, and diagnostics.
MAX_OUTPUT_BYTES = 1024 * 1024
_COLLECTION_LOCK = threading.Lock()
_WORKER = Path(__file__).with_name("_worker.py").resolve()


def _run_worker(command, timeout_seconds):
    """Drain bounded IPC and always kill/reap a worker before returning.

    There are no background threads, pending futures, or late-result queues.
    The worker contains only read calls and never launches child processes.
    """
    deadline = time.monotonic() + timeout_seconds
    process = subprocess.Popen(
        command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, cwd=str(_WORKER.parents[2]),
        shell=False, close_fds=True,
    )
    output = bytearray()
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError
                for key, _events in selector.select(remaining):
                    chunk = os.read(key.fileobj.fileno(), 65536)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        break
                    output.extend(chunk)
                    if len(output) > MAX_OUTPUT_BYTES:
                        raise ValueError("Worker output limit exceeded.")
            process.wait(timeout=max(0, deadline - time.monotonic()))
        if process.returncode != 0:
            raise OSError("Desktop worker failed.")
        return bytes(output)
    finally:
        if process.poll() is None:
            process.kill()
        process.wait()
        process.stdout.close()


def collect_desktop_context(*, timeout_seconds=3.0, max_windows=32):
    """Read once, with no persistence, automatic permission prompts, or LLMs.

    The deadline includes worker startup/imports and native calls. OS process
    creation/reaping can add scheduling latency; this is not a real-time API.
    """
    validate_window_limit(max_windows)
    if (type(timeout_seconds) not in (int, float)
            or not math.isfinite(timeout_seconds) or not 0.05 <= timeout_seconds <= 10):
        raise ValueError("timeout_seconds must be finite and between 0.05 and 10.")
    started = time.monotonic()
    if sys.platform != "darwin":
        return unavailable("unsupported_platform", started)
    if not _COLLECTION_LOCK.acquire(blocking=False):
        return unavailable("collection_busy", started)
    try:
        try:
            payload = _run_worker(
                [sys.executable, "-I", "-B", str(_WORKER), str(max_windows)],
                float(timeout_seconds),
            )
        except (TimeoutError, subprocess.TimeoutExpired):
            return unavailable("collection_timeout", started)
        except ValueError:
            return unavailable("worker_output_invalid", started)
        except Exception:
            return unavailable("worker_failed", started)
        finished = time.monotonic()
        if finished - started > timeout_seconds:
            return unavailable("collection_timeout", started)
        try:
            if len(payload) > MAX_OUTPUT_BYTES:
                raise ValueError("Oversized result.")
            result = DesktopContextObservation.from_dict(json.loads(payload))
            if (not started <= result.captured_at_monotonic <= finished
                    or len(result.windows) > max_windows):
                raise ValueError("Result is outside this collection's bounds.")
            return result
        except Exception:
            return unavailable("worker_output_invalid", started)
    finally:
        _COLLECTION_LOCK.release()
