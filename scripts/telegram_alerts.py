"""Daily entry point: sends each registered chat its configured Agile price messages.

Run daily (via GitHub Actions) after Octopus publishes next-day rates (~4pm UK).
Read-only against state -- this script never registers chats or applies
/setregion, /setthreshold, /setmode; that's all handled by the more frequent
`scripts.poll_commands` job, so this one never needs write access to the repo.

Run as a module from the project root: python -m scripts.telegram_alerts
"""

import os
from pathlib import Path

from dotenv import load_dotenv

from octopus_core import fetch_agile_rates, get_current_agile_product_code
from notifiers.telegram import send_for_mode
from scripts.chat_state import load_state
from scripts.rate_windows import tomorrows_utc_window

PROJECT_ROOT = Path(__file__).parent.parent

load_dotenv(PROJECT_ROOT / ".env")  # no-op locally if .env doesn't exist; harmless in CI too


def main() -> None:
    bot_token = os.environ["TELEGRAM_BOT_TOKEN"]
    state = load_state()
    chats = state["chats"]

    if not chats:
        print("No registered chats yet, nothing to send.")
        return

    product_code = get_current_agile_product_code()
    period_from, period_to = tomorrows_utc_window()

    slots_by_region: dict[str, list] = {}

    for chat_id, config in chats.items():
        mode = config["mode"]
        if mode == "off":
            continue

        region = config["region"]

        try:
            if region not in slots_by_region:
                slots_by_region[region] = fetch_agile_rates(product_code, region, period_from, period_to)
                print(f"Region {region}: {len(slots_by_region[region])} slots")
            slots = slots_by_region[region]

            send_for_mode(
                slots,
                mode=mode,
                threshold=config["threshold"],
                bot_token=bot_token,
                chat_id=chat_id,
                day="tomorrow",
            )
        except Exception as exc:  # noqa: BLE001 - one chat's failure shouldn't sink the rest
            print(f"Failed to send to chat {chat_id}: {exc}")

    print("Done.")


if __name__ == "__main__":
    main()
