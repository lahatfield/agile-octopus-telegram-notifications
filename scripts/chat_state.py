"""Load/save the multi-chat Telegram state file.

state/state_telegram.json shape:
    {
      "offset": 384437557,
      "chats": {
        "<chat_id>": {"region": "P", "threshold": 30.0, "mode": "both"}
      }
    }

`offset` is a single bot-wide getUpdates cursor (Telegram's own offset isn't
per-chat), so it lives at the top level, outside `chats`.
"""

import json
import os
from pathlib import Path

from octopus_core import VALID_REGIONS

PROJECT_ROOT = Path(__file__).parent.parent
STATE_DIR = PROJECT_ROOT / "state"
# Seed-only default region, written by `python -m scripts.setup_region`. Used
# only when a brand new chat registers itself and hasn't run /setregion yet.
SHARED_STATE_PATH = STATE_DIR / "state_default.json"
STATE_PATH = STATE_DIR / "state_telegram.json"

DEFAULT_MODE = "both"
DEFAULT_THRESHOLD = 30.0


def default_chat_config() -> dict:
    """Seed config for a chat that has just self-registered."""
    if SHARED_STATE_PATH.exists():
        region = json.loads(SHARED_STATE_PATH.read_text())["region"]
    else:
        region = os.environ.get("REGION")
    if not region:
        raise RuntimeError(
            "No state/state_default.json and REGION isn't set. "
            "Run `python -m scripts.setup_region` first, or set REGION."
        )
    if region not in VALID_REGIONS:
        raise RuntimeError(f"Default region '{region}' isn't a recognised region letter.")

    return {
        "region": region,
        "threshold": float(os.environ.get("THRESHOLD", str(DEFAULT_THRESHOLD))),
        "mode": DEFAULT_MODE,
    }


def load_state() -> dict:
    """Load the multi-chat state file, or a fresh empty state if it doesn't exist yet."""
    if not STATE_PATH.exists():
        return {"offset": 0, "chats": {}}
    return json.loads(STATE_PATH.read_text())


def save_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state, indent=2))
