import pytest

from notifiers.telegram import ChatCommand, poll_updates


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class _FakeSession:
    def __init__(self, updates):
        self._updates = updates

    def get(self, url, params=None):
        return _FakeResponse({"result": self._updates})


def _update(update_id, chat_id, text):
    return {
        "update_id": update_id,
        "message": {"chat": {"id": chat_id}, "text": text},
    }


def test_poll_updates_parses_commands_across_multiple_chats():
    session = _FakeSession(
        [
            _update(1, -100, "/setregion c"),
            _update(2, 200, "/setthreshold 25"),
            _update(3, -100, "/today"),
            _update(4, 200, "just chatting, not a command"),
        ]
    )

    commands, next_offset = poll_updates(bot_token="TOKEN", offset=0, session=session)

    assert commands == [
        ChatCommand("-100", "setregion", "C"),
        ChatCommand("200", "setthreshold", 25.0),
        ChatCommand("-100", "today"),
    ]
    assert next_offset == 5


def test_poll_updates_defers_validity_checks_to_the_caller():
    """An unrecognised region/mode still produces a command -- the caller decides
    whether it's valid and how to reply, rather than it silently vanishing here."""
    session = _FakeSession(
        [
            _update(1, 200, "/setregion z"),
            _update(2, 200, "/setmode loud"),
        ]
    )

    commands, _ = poll_updates(bot_token="TOKEN", offset=0, session=session)

    assert commands == [
        ChatCommand("200", "setregion", "Z"),
        ChatCommand("200", "setmode", "loud"),
    ]


def test_poll_updates_advances_offset_even_with_no_recognised_commands():
    session = _FakeSession([_update(41, 200, "hello")])

    commands, next_offset = poll_updates(bot_token="TOKEN", offset=0, session=session)

    assert commands == []
    assert next_offset == 42


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("/start", "start"),
        ("/start@my_bot", "start"),
        ("/today", "today"),
        ("/tomorrow", "tomorrow"),
    ],
)
def test_poll_updates_recognises_literal_commands(text, kind):
    session = _FakeSession([_update(1, 200, text)])

    commands, _ = poll_updates(bot_token="TOKEN", offset=0, session=session)

    assert commands == [ChatCommand("200", kind)]
