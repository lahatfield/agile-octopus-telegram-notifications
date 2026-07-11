"""Report which required environment variables are set, without printing their values.

Safe to run any time — never prints an actual secret, only presence/absence.
Run: python -m scripts.check_env
"""

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / ".env")

REQUIRED_VARS = [
    "TELEGRAM_BOT_TOKEN",
]
OPTIONAL_VARS = [
    "REGION",  # seed default for newly self-registered chats; falls back to state/state_default.json if unset
    "THRESHOLD",  # seed default for newly self-registered chats; falls back to 30.0 if unset
]


def main() -> None:
    print("Required:")
    for name in REQUIRED_VARS:
        status = "set" if os.environ.get(name) else "MISSING"
        print(f"  {name}: {status}")

    print("Optional:")
    for name in OPTIONAL_VARS:
        status = "set" if os.environ.get(name) else "not set (using fallback)"
        print(f"  {name}: {status}")


if __name__ == "__main__":
    main()
