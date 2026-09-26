"""Offline test policy. No changes to production source or containment checks."""
import socket
import sys

import pytest


def pytest_addoption(parser):
    parser.addoption('--run-live-model', action='store_true', default=False,
                     help='Enable marked tests that contact a real model.')
    parser.addoption('--run-native-sandbox', action='store_true', default=False,
                     help='Enable real macOS containment checks; unavailable facilities fail.')


def pytest_collection_modifyitems(config, items):
    for item in items:
        for marker, option in (('live_model', '--run-live-model'),
                               ('native_sandbox', '--run-native-sandbox')):
            if item.get_closest_marker(marker) and not config.getoption(option):
                item.add_marker(pytest.mark.skip(reason=f'Explicit opt-in required: {option}'))


def _blocked_effect(*args, **kwargs):
    # pytest.fail is not swallowed by production except-Exception handlers.
    pytest.fail('Unmocked external effect in an offline test; inject a fake dependency.',
                pytrace=False)


@pytest.fixture(autouse=True)
def offline_effects(request, monkeypatch):
    live_model = (request.node.get_closest_marker('live_model') is not None
                  and request.config.getoption('--run-live-model'))
    if not live_model:
        monkeypatch.setattr(socket.socket, 'connect', _blocked_effect)
        monkeypatch.setattr(socket.socket, 'connect_ex', _blocked_effect)
        monkeypatch.setattr(socket.socket, 'sendto', _blocked_effect)
        monkeypatch.setattr(socket, 'getaddrinfo', _blocked_effect)
        # Collection imports the project's model classes before fixtures run.
        # Patch the class initializer as well as network access so cached local
        # embeddings cannot accidentally make an offline test model-dependent.
        module = sys.modules.get('sentence_transformers')
        if module is not None:
            monkeypatch.setattr(module.SentenceTransformer, '__init__', _blocked_effect)
        module = sys.modules.get('ollama')
        if module is not None:
            monkeypatch.setattr(module, 'chat', _blocked_effect)
            monkeypatch.setattr(module.Client, 'chat', _blocked_effect)
            monkeypatch.setattr(module.AsyncClient, 'chat', _blocked_effect)

    # A model opt-in never authorizes real desktop input or screenshots.
    module = sys.modules.get('pyautogui')
    if module is not None:
        for name in ('click', 'doubleClick', 'rightClick', 'moveTo', 'moveRel',
                     'dragTo', 'dragRel', 'write', 'typewrite', 'press', 'hotkey',
                     'keyDown', 'keyUp', 'scroll', 'hscroll', 'screenshot',
                     'mouseDown', 'mouseUp'):
            monkeypatch.setattr(module, name, _blocked_effect)


@pytest.fixture(autouse=True)
def isolated_conversation_database(monkeypatch, tmp_path):
    module = sys.modules.get('app.memory.memory')
    if module is not None:
        monkeypatch.setattr(module, 'DB_PATH', tmp_path / 'conversation.sqlite3')
        monkeypatch.setattr(module, '_embedding_model', None)
