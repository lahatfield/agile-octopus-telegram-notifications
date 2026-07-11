"""One-time (or one-off update) interactive setup: saves the default DNO region letter.

Run this locally: python -m scripts.setup_region
Writes to state/state_default.json, which is tracked in git -- commit and
push after running this. This is only the *seed* region used the moment a
new chat self-registers with the bot (before it's run /setregion itself);
it has no effect on chats that have already set their own region.
"""

import json

from octopus_core import VALID_REGIONS
from scripts.chat_state import SHARED_STATE_PATH


def main() -> None:
    print("Enter your DNO region letter. Options:")
    for letter, name in VALID_REGIONS.items():
        print(f"  {letter} - {name}")

    while True:
        region = input("Region letter: ").strip().upper()
        if region in VALID_REGIONS:
            break
        print(f"'{region}' isn't a recognised region letter, try again.")

    SHARED_STATE_PATH.write_text(json.dumps({"region": region}, indent=2))
    print(f"Saved region '{region}' ({VALID_REGIONS[region]}) to {SHARED_STATE_PATH}")
    print("Remember to commit and push state/state_default.json.")


if __name__ == "__main__":
    main()
