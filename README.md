# OAO Control Center — Discord Bot

Cog-based refactor of the original single-file OAO bot. Manages ARK
generator refuels, dino-feed teleporters and spam zones through the
existing PHP backend at `https://www.t-doc.co.za/discord/`.

---

## Project layout

```
discord-bot/
├── bot.py                  # entrypoint (loads cogs, starts the client)
├── config.py               # env vars, endpoints, thresholds, channel/role IDs
├── api_client.py           # aiohttp wrapper with retry + timeout
├── state.py                # thread/async-safe cross-cog state + persistence
├── utils.py                # tiny pure helpers (format_time, timezone-safe math)
├── requirements.txt
├── requirements-dev.txt    # +pytest, +ruff for local dev / CI
├── pytest.ini
├── Procfile                # "worker: python bot.py" (used by Railway)
├── .env.example            # copy to .env for local dev
├── .github/workflows/ci.yml
├── tests/                  # pytest suite (35 tests, no discord runtime needed)
└── cogs/
    ├── generators.py       # dashboard, add/refuel/rename/delete, tools, search
    ├── dinos.py            # dino-feed TP CRUD
    ├── spam_zones.py       # spam-zone CRUD + map upload
    ├── dashboard.py        # /oao_dashboard + auto-refresh + persistent views
    ├── alerts.py           # alert loop, per-server/severity channel routing
    ├── stats.py            # /oao_stats + daily snapshot post
    └── logging_cog.py      # audit log helper (bot.log_action)
```

---

## Local setup

1. **Clone / copy the folder** and `cd discord-bot`.
2. Copy `.env.example` to `.env` and fill in your `TOKEN` and `API_KEY`.
3. Install deps:
   ```bash
   python -m venv .venv
   source .venv/bin/activate   # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```
4. Run:
   ```bash
   python bot.py
   ```

The bot will hard-fail at startup if `TOKEN` or `API_KEY` is missing
(`config.validate()`).

---

## Deploying to Railway

1. Push the **whole `discord-bot/` folder** to GitHub (do not commit `.env`).
2. In Railway, create a new project **from your GitHub repo**.
3. Set env variables in the Railway dashboard:
   - `TOKEN` — your Discord bot token
   - `API_KEY` — the shared secret expected by your PHP endpoints
   - `DEV_GUILD_ID` *(optional)* — your **Discord community/server ID**
     (right-click your Discord icon → Copy Server ID). This is *not* an
     ARK server tag — it's the Discord community itself. When set, slash
     commands sync there instantly on boot. Supports a comma-separated
     list if your bot runs in multiple Discord communities
     (e.g. `123...,987...`). Leave unset for a global sync (up to ~1h).
4. Railway detects the `Procfile` and starts the process with
   `worker: python bot.py`. No further config needed.
5. First deploy will install `requirements.txt` and start the bot.

To roll out changes: `git push`. Railway auto-redeploys.

---

## Filling in Discord IDs

Open `config.py` and fill in the four constants at the top of the
"DISCORD IDs" section:

```python
GEN_CHANNEL_ID   = 0   # generator channel id
LOG_CHANNEL_ID   = 0   # audit log channel id
ALERT_CHANNEL_ID = 0   # alerts channel id
DEFAULT_ROLE     = 0   # role id used as a fallback in alerts (0 = no ping)

SERVER_ROLES = {
    # "2491": 1516139334070440050,
}
```

Everything else — API URLs, thresholds, page size — is already wired.

---

## Bug fixes included in this refactor

1. **`refresh_dashboard()`** now really re-edits every registered dashboard
   message with a fresh embed + view.
2. **`DEFAULT_ROLE`** is defined in `config.py`, defaults to `0`, and is
   used as a safe fallback in `SERVER_ROLES.get(server, DEFAULT_ROLE)`.
3. **`API_SPAM_MAP`** duplicate definition removed.
4. **`last_deleted` / `last_alerts` / `last_refuel_user` / dashboard message
   registry** all live inside `StateManager` (`state.py`) behind an
   `asyncio.Lock`, so concurrent interactions can't race.
5. **Alert resolution** only fires when a generator returns to *healthy*
   (`> LOW_HOURS`). Transitions between alert severities edit the existing
   alert message in place instead of falsely posting a resolution.
6. **`updated_at` day math** uses timezone-aware UTC (`datetime.now(timezone.utc)`)
   and clamps to zero, so mixing naive/aware timestamps or slight clock
   skew never blows up. See `utils.effective_days`.
7. **`API_KEY`** no longer hard-coded — loaded from `os.getenv("API_KEY")`
   in `config.py`. Startup fails fast if missing.
8. **API retries**: every request goes through `ApiClient._request` which
   performs 3 attempts with exponential backoff (1s -> 2s -> 4s) before
   returning `[]`. Timeouts and errors are logged instead of silently swallowed.

---

## Extending the bot

To add a new domain (e.g. "raids"):

1. Add its endpoints + constants to `config.py`.
2. Create `cogs/raids.py` with a `commands.Cog` subclass and an
   `async def setup(bot)` entry function.
3. Register the module name in `INITIAL_COGS` in `bot.py`.

Cross-cog references should be **lazy imports inside callbacks** to avoid
circular import errors (see how `cogs/dinos.py` imports `BackButton` from
`cogs/dashboard.py`).

---

## Runtime behaviour

- Slash command: **`/oao_dashboard`** — opens the top-level server picker.
- Slash command: **`/oao_stats`** — posts a public snapshot embed of every
  server (total gens, critical, low, healthy + dino TP + spam zone counts).
- Auto-refresh loop: every 5 minutes, all registered dashboard messages
  are re-edited with fresh data (`DASHBOARD_REFRESH_INTERVAL_MIN`).
- Alert loop: every 10 minutes, `check_alerts` walks every generator and
  posts / edits / resolves the alert message for it
  (`ALERT_CHECK_INTERVAL_MIN`), routed per server/severity via
  `ALERT_CHANNELS`.
- Daily snapshot: once per day at `STATS_POST_HOUR_UTC:00` UTC the bot
  posts the `/oao_stats` embed automatically to `STATS_CHANNEL_ID`
  (falls back to the alert / log channel if unset).

---

## Persistence across restarts

The top-level `ServerSelectionView` and every `ServerMenuView` are
registered as **persistent views** on startup, so any existing
`/oao_dashboard` message keeps its buttons alive without re-issuing the
command.

Dashboard message IDs are stored in a small JSON file (default:
`discord-bot/.bot_state.json`, override with `STATE_FILE_PATH`). On
startup the bot re-fetches those messages so `refresh_dashboard()` keeps
editing them.

---

## Testing

```bash
pip install -r requirements-dev.txt
pytest                # 35 tests, no Discord runtime required
ruff check .          # lint
```

The GitHub Actions workflow at `.github/workflows/ci.yml` runs both on
every push / PR against `main` on Python 3.11 and 3.12.

---

## Per-server / per-severity alert channels

Fill `ALERT_CHANNELS` in `config.py`. Lookup order:

1. `ALERT_CHANNELS[server][severity]`
2. `ALERT_CHANNELS[server]["default"]`
3. `ALERT_CHANNELS["_default"][severity]`
4. `ALERT_CHANNELS["_default"]["default"]`
5. `ALERT_CHANNEL_ID` (global fallback)

Example:

```python
ALERT_CHANNELS = {
    "2491":     {"critical": 111, "very_low": 222, "low": 222, "default": 333},
    "_default": {"critical": 444, "default": 555},
}
```
