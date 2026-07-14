import json

import pytest

from scripts import chat_state


@pytest.fixture(autouse=True)
def isolated_state_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(chat_state, "STATE_PATH", tmp_path / "state_telegram.json")
    monkeypatch.setattr(chat_state, "SHARED_STATE_PATH", tmp_path / "state_default.json")
    monkeypatch.delenv("REGION", raising=False)
    monkeypatch.delenv("THRESHOLD", raising=False)


def test_load_state_returns_empty_shape_when_file_missing():
    state = chat_state.load_state()

    assert state == {"offset": 0, "chats": {}}


def test_load_state_returns_saved_shape_unchanged():
    saved = {"offset": 5, "chats": {"200": {"region": "C", "threshold": 20.0, "mode": "all"}}}
    chat_state.STATE_PATH.write_text(json.dumps(saved))

    assert chat_state.load_state() == saved


def test_default_chat_config_uses_shared_state_region(monkeypatch):
    chat_state.SHARED_STATE_PATH.write_text(json.dumps({"region": "M"}))
    monkeypatch.setenv("THRESHOLD", "42")

    config = chat_state.default_chat_config()

    assert config == {"region": "M", "threshold": 42.0, "mode": "both"}


def test_default_chat_config_falls_back_to_region_env(monkeypatch):
    monkeypatch.setenv("REGION", "K")

    config = chat_state.default_chat_config()

    assert config == {"region": "K", "threshold": 30.0, "mode": "both"}


def test_default_chat_config_raises_without_any_region():
    with pytest.raises(RuntimeError, match="REGION"):
        chat_state.default_chat_config()


def test_save_and_reload_round_trip():
    state = {"offset": 3, "chats": {"1": {"region": "A", "threshold": 10.0, "mode": "off"}}}

    chat_state.save_state(state)

    assert chat_state.load_state() == state
