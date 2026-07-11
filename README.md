# Agile Octopus Telegram Notifications

A Python bot that watches [Octopus Energy's Agile](https://octopus.energy/smart/agile/) half-hourly
electricity tariff and posts alerts to Telegram when prices go negative, drop to a
cheap/"ok" level, or spike above a configurable threshold. One bot, added to as many
Telegram chats as you like (a household group, a family group, a DM, ...) -- each chat
configures its own region, threshold, and which messages it wants independently.

## How it works

Each day (after Octopus publishes the next day's rates, ~4pm UK time), a scheduled job:

1. Looks up the current Agile product code (these roll over periodically, so it's looked
   up dynamically rather than hard-coded).
2. Fetches tomorrow's half-hourly rates for every region any registered chat uses.
3. Categorises every slot as **negative** (💰 you're paid to use electricity), **ok**
   (✅ at or below that chat's threshold), or **spike** (❌ above it).
4. Sends each chat the message type(s) it's configured for (see `/setmode` below).

Separately, a job polls Telegram every few minutes for commands, so config changes and
on-demand requests (`/today`, `/tomorrow`) take effect within a few minutes rather than
waiting for the next scheduled daily run.

## Architecture

| Path | Purpose |
| --- | --- |
| `notifiers/telegram.py` | Formats slots and talks to the Telegram Bot API: sends messages, parses incoming commands across all chats. |
| `scripts/chat_state.py` | Loads/saves `state/state_telegram.json`. |
| `scripts/rate_windows.py` | Computes the UK-local-calendar UTC windows ("today remaining", "tomorrow") passed to `octopus_core.fetch_agile_rates`. |
| `scripts/telegram_alerts.py` | The daily job: sends every registered chat its configured alerts. Read-only against state. Run via GitHub Actions. |
| `scripts/poll_commands.py` | The frequent-poll job: registers new chats and handles all commands, including `/today`/`/tomorrow`. The only job that writes state. Run via GitHub Actions. |
| `scripts/setup_region.py` | One-time (or one-off update) interactive script that sets the default region seeded to newly self-registered chats. |
| `scripts/check_env.py` | Reports which required environment variables are set, without printing their actual values. |

Rate fetching/categorizing (`octopus_core`) lives in a separate repo,
[agile-octopus-core](https://github.com/lahatfield/agile-octopus-core), and is pulled in
as a regular dependency (see `pyproject.toml`).

### Configuration and state

- **`.env`** (gitignored, never committed) holds secrets and seed defaults.
  Copy `.env.example` to `.env` and fill in real values.
- **`state/state_default.json`** (tracked in git) holds the default DNO region
  (Distribution Network Operator) - Octopus's single-letter code (A–P) for your regional
  electricity distributor - seeded to any chat the moment it first messages the bot.
- **`state/state_telegram.json`** (tracked in git) holds every registered chat's own
  region, threshold and mode, plus a single cursor tracking which Telegram messages have
  already been processed (Telegram's `getUpdates` cursor is bot-wide, not per-chat):
  ```json
  {
    "offset": 384437557,
    "chats": {
      "<chat_id>": {"region": "P", "threshold": 30.0, "mode": "both"}
    }
  }
  ```
  Only `scripts/poll_commands.py` ever writes this file. This project is intended for a
  handful of your own chats, not as a public multi-tenant service -- every chat_id
  committed here belongs to a chat you administer, the same way the region/threshold were
  already public before. If you ever wanted to let strangers self-serve add this bot to
  their own groups, this design would need revisiting (e.g. a private state store).

## Setup

### 1. Install dependencies

Requires [uv](https://docs.astral.sh/uv/getting-started/installation/).

```sh
uv sync --group dev
```

This creates `.venv` and installs everything pinned in `uv.lock` (runtime deps plus
`pytest`, for running tests).

### 2. Create a Telegram bot

Via [@BotFather](https://t.me/BotFather): `/newbot`. Add it to any Telegram chats you
want alerts in — a group, or just DM it directly. No privacy-mode changes needed: the bot
only ever reacts to slash commands, which Telegram delivers to bots regardless of privacy
mode, so leave privacy mode on (the default) and it'll never see ordinary chat messages.

Each chat registers itself the first time you send it any command (e.g. `/start`) — no
need to look up or configure a chat ID anywhere.

### 3. Configure secrets

```sh
cp .env.example .env
```
Fill in `TELEGRAM_BOT_TOKEN` in `.env`. `REGION` and `THRESHOLD` are optional seed
defaults used the moment a new chat registers itself (see
[Configuration and state](#configuration-and-state) above).

Run `uv run python -m scripts.check_env` any time to confirm which required variables
are set, without ever printing their actual values.

### 4. Set the default region

```sh
uv run python -m scripts.setup_region
```

### 5. Run it

```sh
uv run python -m scripts.poll_commands     # registers chats, handles commands
uv run python -m scripts.telegram_alerts   # sends that day's alerts
```

## Telegram commands

Sent as a message in any chat the bot is in:

- `/setthreshold 25` — prices at or below 25p/kWh count as "ok"; above that, "spike".
- `/setregion C` — switch this chat to a different DNO region.
- `/setmode all|alerts|both|off` — which daily messages this chat receives: every slot,
  only plunge/spike alerts, both, or nothing.
- `/today` — send today's remaining slots right now.
- `/tomorrow` — send tomorrow's slots right now, or a "not published yet" reply if
  Octopus hasn't published them (before ~4pm UK).
- `/start` — registers the chat (if new) and replies with this command list.

`/setregion`, `/setthreshold` and `/setmode` take effect within a few minutes (the
command-polling job runs on a `*/5 * * * *` schedule), not instantly — this keeps
everything running on free scheduled GitHub Actions rather than needing an always-on
server. `/today` and `/tomorrow` reply on that same poll, so they're effectively instant
on the same timescale.

## Running tests

```sh
uv run python -m pytest
```

## Deployment

Two scheduled GitHub Actions workflows (see `.github/workflows/`):

- `daily-rundown.yml` — once a day (`30 16 * * *`), sends every registered chat its
  configured alerts. Read-only against state, so it only needs the default
  (read-only) `GITHUB_TOKEN` permissions.
- `poll-commands.yml` — every five minutes, handles all commands and registers new
  chats. The only workflow that commits `state/state_telegram.json`, so it needs
  `permissions: contents: write`.

Note GitHub disables scheduled workflows in a repo after 60 days with no commits (not
runs) — if notifications silently stop, check whether they've been auto-disabled in the
Actions tab.