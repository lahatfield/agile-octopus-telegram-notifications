"""Frequent-poll entry point: handles all Telegram commands.

Runs every few minutes (via GitHub Actions), separately from the once-daily
alert send in `scripts.telegram_alerts`. This is the only job that touches
Telegram's getUpdates offset, registers new chats, applies /setregion,
/setthreshold and /setmode, and answers /start, /today and /tomorrow -- the
latter two are what make an "instant" reply possible without an always-on
server.

Run as a module from the project root: python -m scripts.poll_commands
"""

import os
from pathlib import Path

from dotenv import load_dotenv

from octopus_core import VALID_REGIONS, fetch_agile_rates, get_current_agile_product_code
from notifiers.telegram import (
    VALID_MODES,
    ChatCommand,
    send_all_slots,
    send_help,
    send_text,
    poll_updates,
)
from scripts.chat_state import default_chat_config, load_state, save_state
from scripts.rate_windows import todays_remaining_utc_window, tomorrows_utc_window

PROJECT_ROOT = Path(__file__).parent.parent

load_dotenv(PROJECT_ROOT / ".env")  # no-op locally if .env doesn't exist; harmless in CI too


class _RatesFetcher:
    """Fetches rates lazily, caching by (region, window kind) within one run."""

    def __init__(self) -> None:
        self._product_code: str | None = None
        self._cache: dict[tuple[str, str], list] = {}

    def _get_product_code(self) -> str:
        if self._product_code is None:
            self._product_code = get_current_agile_product_code()
        return self._product_code

    def fetch(self, region: str, kind: str) -> list:
        key = (region, kind)
        if key not in self._cache:
            window = todays_remaining_utc_window() if kind == "today" else tomorrows_utc_window()
            self._cache[key] = fetch_agile_rates(self._get_product_code(), region, *window)
        return self._cache[key]


def _get_or_register_chat(chats: dict, chat_id: str) -> dict:
    if chat_id not in chats:
        chats[chat_id] = default_chat_config()
    return chats[chat_id]


def _handle_command(command: ChatCommand, *, chats: dict, bot_token: str, rates: _RatesFetcher) -> None:
    chat_id = command.chat_id

    if command.kind == "setregion":
        region = command.value
        if region not in VALID_REGIONS:
            send_text(
                f"'{region}' isn't a recognised region letter.",
                bot_token=bot_token,
                chat_id=chat_id,
            )
            return
        config = _get_or_register_chat(chats, chat_id)
        config["region"] = region
        send_text(f"Region updated to {region}.", bot_token=bot_token, chat_id=chat_id)
        return

    if command.kind == "setthreshold":
        config = _get_or_register_chat(chats, chat_id)
        config["threshold"] = command.value
        send_text(f"Threshold updated to {command.value}p.", bot_token=bot_token, chat_id=chat_id)
        return

    if command.kind == "setmode":
        mode = command.value
        if mode not in VALID_MODES:
            send_text(
                f"'{mode}' isn't a valid mode. Choose one of: {', '.join(sorted(VALID_MODES))}.",
                bot_token=bot_token,
                chat_id=chat_id,
            )
            return
        config = _get_or_register_chat(chats, chat_id)
        config["mode"] = mode
        send_text(f"Mode updated to {mode}.", bot_token=bot_token, chat_id=chat_id)
        return

    if command.kind == "start":
        _get_or_register_chat(chats, chat_id)
        send_help(bot_token=bot_token, chat_id=chat_id)
        return

    if command.kind == "today":
        config = _get_or_register_chat(chats, chat_id)
        slots = rates.fetch(config["region"], "today")
        if not slots:
            send_text("No more slots left for today.", bot_token=bot_token, chat_id=chat_id)
            return
        send_all_slots(
            slots, threshold=config["threshold"], bot_token=bot_token, chat_id=chat_id,
            header="Today's remaining Agile prices",
        )
        return

    if command.kind == "tomorrow":
        config = _get_or_register_chat(chats, chat_id)
        slots = rates.fetch(config["region"], "tomorrow")
        if not slots:
            send_text(
                "Tomorrow's rates aren't published yet -- check back after ~4pm UK.",
                bot_token=bot_token,
                chat_id=chat_id,
            )
            return
        send_all_slots(
            slots, threshold=config["threshold"], bot_token=bot_token, chat_id=chat_id,
            header="Tomorrow's Agile prices",
        )
        return


def main() -> None:
    bot_token = os.environ["TELEGRAM_BOT_TOKEN"]
    state = load_state()
    chats = state["chats"]

    commands, next_offset = poll_updates(bot_token=bot_token, offset=state["offset"])
    state["offset"] = next_offset

    rates = _RatesFetcher()
    for command in commands:
        try:
            _handle_command(command, chats=chats, bot_token=bot_token, rates=rates)
        except Exception as exc:  # noqa: BLE001 - one chat's failure shouldn't sink the rest
            print(f"Failed to handle {command.kind} for chat {command.chat_id}: {exc}")

    save_state(state)
    print(f"Processed {len(commands)} command(s) across {len(chats)} chat(s).")


if __name__ == "__main__":
    main()
