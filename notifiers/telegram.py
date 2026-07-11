"""Format Agile rate slots and post them to a Telegram chat.

Takes raw slots from octopus_core and a single price threshold.

One bot serves any number of chats. Each chat has its own `mode`, which
governs what the *daily* scheduled push sends it: "all" (every slot),
"alerts" (only plunge/spike slots), "both", or "off" (nothing). On-demand
commands like /today and /tomorrow always send the full slot listing,
regardless of `mode`.
"""

from __future__ import annotations

import dataclasses
import re
from typing import Literal
from zoneinfo import ZoneInfo

import requests

from octopus_core import (
    RateSlot,
    categorize_slot,
    filter_negative_slots,
    filter_spike_slots,
)

TELEGRAM_BASE_URL = "https://api.telegram.org/bot{token}"
LONDON_TZ = ZoneInfo("Europe/London")

VALID_MODES = {"all", "alerts", "both", "off"}

# Slash commands are delivered to bots regardless of group privacy mode,
# unlike plain messages, so no special bot configuration is needed for this.
SET_THRESHOLD_PATTERN = re.compile(r"^/setthreshold(?:@\w+)?\s+(-?\d+(?:\.\d+)?)")
SET_REGION_PATTERN = re.compile(r"^/setregion(?:@\w+)?\s+([A-Za-z])")
SET_MODE_PATTERN = re.compile(r"^/setmode(?:@\w+)?\s+(\w+)")
START_PATTERN = re.compile(r"^/start(?:@\w+)?\b")
TODAY_PATTERN = re.compile(r"^/today(?:@\w+)?\b")
TOMORROW_PATTERN = re.compile(r"^/tomorrow(?:@\w+)?\b")

EMOJI_BY_CATEGORY = {
    "negative": "💰",
    "ok": "✅",
    "spike": "❌",
}

HELP_TEXT = (
    "Agile price alerts for this chat.\n\n"
    "Commands:\n"
    "/setregion X - switch DNO region (e.g. /setregion C)\n"
    "/setthreshold N - prices above N p/kWh count as a spike (e.g. /setthreshold 25)\n"
    "/setmode all|alerts|both|off - which daily messages this chat receives\n"
    "/today - send today's remaining slots right now\n"
    "/tomorrow - send tomorrow's slots right now, if published yet\n"
)

CommandKind = Literal["start", "setregion", "setthreshold", "setmode", "today", "tomorrow"]


@dataclasses.dataclass(frozen=True)
class ChatCommand:
    chat_id: str
    kind: CommandKind
    value: str | float | None = None


def _format_time_range(slot: RateSlot) -> str:
    local_from = slot.valid_from.astimezone(LONDON_TZ)
    local_to = slot.valid_to.astimezone(LONDON_TZ)
    return f"{local_from:%H:%M}-{local_to:%H:%M}"


def _format_slot(slot: RateSlot, threshold: float) -> str:
    emoji = EMOJI_BY_CATEGORY[categorize_slot(slot, threshold)]
    return f"{emoji} {_format_time_range(slot)}: {slot.value_inc_vat:.2f}p/kWh"


def _build_message(slots: list[RateSlot], threshold: float, header: str) -> str:
    sorted_slots = sorted(slots, key=lambda slot: slot.valid_from)
    lines = [header] + [_format_slot(slot, threshold) for slot in sorted_slots]
    return "\n".join(lines)


def _post_message(
    text: str,
    *,
    bot_token: str,
    chat_id: str,
    session: requests.Session | None = None,
) -> None:
    session = session or requests.Session()
    url = f"{TELEGRAM_BASE_URL.format(token=bot_token)}/sendMessage"
    response = session.post(url, json={"chat_id": chat_id, "text": text})
    response.raise_for_status()


def send_text(
    text: str,
    *,
    bot_token: str,
    chat_id: str,
    session: requests.Session | None = None,
) -> None:
    """Post an arbitrary plain-text message, e.g. a confirmation reply."""
    _post_message(text, bot_token=bot_token, chat_id=chat_id, session=session)


def send_help(*, bot_token: str, chat_id: str, session: requests.Session | None = None) -> None:
    """Reply to /start (or an unrecognised command) with the command list."""
    _post_message(HELP_TEXT, bot_token=bot_token, chat_id=chat_id, session=session)


def poll_updates(
    *,
    bot_token: str,
    offset: int,
    session: requests.Session | None = None,
) -> tuple[list[ChatCommand], int]:
    """Fetch pending Telegram updates for the whole bot and parse recognised commands.

    Unlike a single-chat check, this returns every recognised command from
    every chat the bot is in, in the order Telegram delivered them (so a
    caller can apply /setregion before a later /today in the same batch).
    Callers should persist `next_offset` and pass it back in as `offset`
    next time, so the same updates aren't reprocessed.
    """
    session = session or requests.Session()
    url = f"{TELEGRAM_BASE_URL.format(token=bot_token)}/getUpdates"
    response = session.get(url, params={"offset": offset, "timeout": 0})
    response.raise_for_status()
    updates = response.json()["result"]

    commands: list[ChatCommand] = []
    next_offset = offset

    for update in updates:
        next_offset = max(next_offset, update["update_id"] + 1)
        message = update.get("message")
        if message is None:
            continue
        chat_id = str(message["chat"]["id"])
        text = message.get("text", "")

        threshold_match = SET_THRESHOLD_PATTERN.match(text)
        if threshold_match:
            commands.append(ChatCommand(chat_id, "setthreshold", float(threshold_match.group(1))))
            continue

        region_match = SET_REGION_PATTERN.match(text)
        if region_match:
            # Validity (is this a real region letter?) is left to the caller,
            # so it can reply with a helpful error instead of the command
            # silently vanishing.
            commands.append(ChatCommand(chat_id, "setregion", region_match.group(1).upper()))
            continue

        mode_match = SET_MODE_PATTERN.match(text)
        if mode_match:
            commands.append(ChatCommand(chat_id, "setmode", mode_match.group(1).lower()))
            continue

        if START_PATTERN.match(text):
            commands.append(ChatCommand(chat_id, "start"))
            continue

        if TODAY_PATTERN.match(text):
            commands.append(ChatCommand(chat_id, "today"))
            continue

        if TOMORROW_PATTERN.match(text):
            commands.append(ChatCommand(chat_id, "tomorrow"))
            continue

    return commands, next_offset


def send_all_slots(
    slots: list[RateSlot],
    *,
    threshold: float,
    bot_token: str,
    chat_id: str,
    header: str = "Agile prices",
    session: requests.Session | None = None,
) -> None:
    """Post every slot, marked with an emoji per `threshold`."""
    if not slots:
        return
    message = _build_message(slots, threshold, f"{header}:\n")
    _post_message(message, bot_token=bot_token, chat_id=chat_id, session=session)


def send_notable_alert(
    slots: list[RateSlot],
    *,
    threshold: float,
    bot_token: str,
    chat_id: str,
    header: str = "Agile plunge/spike alert",
    session: requests.Session | None = None,
) -> None:
    """Post only plunge/spike slots (skipping OK ones), if any exist."""
    notable_slots = filter_negative_slots(slots) + filter_spike_slots(slots, threshold)
    if not notable_slots:
        return
    message = _build_message(notable_slots, threshold, f"{header}:\n")
    _post_message(message, bot_token=bot_token, chat_id=chat_id, session=session)


def send_for_mode(
    slots: list[RateSlot],
    *,
    mode: str,
    threshold: float,
    bot_token: str,
    chat_id: str,
    day: str = "today",
    session: requests.Session | None = None,
) -> None:
    """Send the message(s) appropriate for `mode` ("all" / "alerts" / "both" / "off"),
    both headers describing `day` (e.g. "tomorrow")."""
    if mode in ("all", "both"):
        send_all_slots(
            slots, threshold=threshold, bot_token=bot_token, chat_id=chat_id,
            header=f"Agile prices for {day}", session=session,
        )
    if mode in ("alerts", "both"):
        send_notable_alert(
            slots, threshold=threshold, bot_token=bot_token, chat_id=chat_id,
            header=f"Agile plunge/spike alert for {day}", session=session,
        )
