"""Central configuration for the OAO Discord Bot.

All secrets are loaded from environment variables. All tunable constants,
API endpoints, channel IDs and role mappings live here so that other
modules never need to know a URL literal or magic number.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List, Optional

from dotenv import load_dotenv

# Load local .env (Railway injects env vars directly, so this is a no-op there)
_ENV_FILE = Path(__file__).parent / ".env"
_ENV_FILE_LOADED = _ENV_FILE.is_file()
load_dotenv()

# =========================================================================
# SECRETS (loaded from env vars — never commit real values)
# =========================================================================
TOKEN: Optional[str] = os.getenv("TOKEN")
API_KEY: Optional[str] = os.getenv("API_KEY")

# =========================================================================
# API BASE + ENDPOINTS
# =========================================================================
API_BASE: str = "https://www.t-doc.co.za/discord"

API_GET: str = f"{API_BASE}/generators.php"
API_ADD: str = f"{API_BASE}/add.php"
API_UPDATE: str = f"{API_BASE}/update.php"
API_DELETE: str = f"{API_BASE}/delete.php"
API_RESTORE: str = f"{API_BASE}/restore.php"
API_TRASH: str = f"{API_BASE}/trash.php"
API_CLEAR_ALL: str = f"{API_BASE}/clear_all.php"

API_DINO_FEED: str = f"{API_BASE}/dino_feed.php"
API_ADD_DINO_FEED: str = f"{API_BASE}/add_dino_feed.php"
API_UPDATE_DINO_FEED: str = f"{API_BASE}/update_dino_feed.php"
API_DELETE_DINO_FEED: str = f"{API_BASE}/delete_dino_feed.php"

API_SPAM_ZONES: str = f"{API_BASE}/spam_zones.php"
API_ADD_SPAM_ZONE: str = f"{API_BASE}/add_spam_zone.php"
API_UPDATE_SPAM_ZONE: str = f"{API_BASE}/update_spam_zone.php"
API_DELETE_SPAM_ZONE: str = f"{API_BASE}/delete_spam_zone.php"

# NOTE: Bug fix #3 — duplicate API_SPAM_MAP definition removed (kept once).
API_SPAM_MAP: str = f"{API_BASE}/get_spam_map.php"
API_UPDATE_SPAM_MAP: str = f"{API_BASE}/update_spam_map.php"

# Ratholes (see PHP_SETUP.md for the required schema + endpoints).
API_RATHOLES: str = f"{API_BASE}/ratholes.php"
API_ADD_RATHOLE: str = f"{API_BASE}/add_rathole.php"
API_UPDATE_RATHOLE: str = f"{API_BASE}/update_rathole.php"
API_DELETE_RATHOLE: str = f"{API_BASE}/delete_rathole.php"
API_UPLOAD_RATHOLE_IMAGE: str = f"{API_BASE}/upload_rathole_image.php"

API_SERVER_SUMMARY: str = f"{API_BASE}/server_summary.php"

# =========================================================================
# BATTLEMETRICS (Ark: Survival Ascended — count-only, anonymous)
# =========================================================================
# Map internal server tag -> BattleMetrics server ID.
# Look up each server at https://www.battlemetrics.com/servers/arksa .
BATTLEMETRICS_IDS: Dict[str, str] = {
    "2491": "36881527",
    "2175": "24313374",
    "2513": "30966925",
    "2779": "24612845",
    "2609": "32000142",
    "2875": "39675763",
}
BATTLEMETRICS_BASE: str = "https://api.battlemetrics.com/servers"

# Optional Discord channel ID for a self-healing dashboard.
# When set, if the bot restarts and finds NO registered dashboard messages
# (e.g. after a Railway deploy wipes the state file), it auto-posts a
# fresh /oao_dashboard-style message to this channel so the 5-min stats
# refresh keeps working without any manual intervention.
DASHBOARD_CHANNEL_ID: int = int(os.getenv("DASHBOARD_CHANNEL_ID", "0"))

# ARK: Survival Ascended official servers sit behind Steam Datagram Relay
# so live player *names* can't be fetched via API or A2S. We display the
# count from BattleMetrics and link out to their web page for the roster.

# =========================================================================
# DISCORD IDs (fill these in with your real IDs)
# =========================================================================
GEN_CHANNEL_ID: int = 0  # ark-generator channel
LOG_CHANNEL_ID: int = 0  # log channel
ALERT_CHANNEL_ID: int = 0  # alerts channel

# Bug fix #2 — DEFAULT_ROLE is now always defined; used when a server-specific
# role isn't found in SERVER_ROLES. Set to 0 (falsy) to disable role pings.
DEFAULT_ROLE: int = 0

# Legacy general role id (kept for backwards compatibility with any commands
# that referenced ROLE_ID directly). Safe to leave as 0.
ROLE_ID: int = 0

# Map server tag -> role id used for @role mentions in alerts.
SERVER_ROLES: Dict[str, int] = {
    # "2491": 1516139334070440050,
}

# ---------------------------------------------------------------------------
# Per-server / per-severity alert channels (backlog #2)
#
# Look-up order for `AlertsCog`:
#   1. ALERT_CHANNELS[server][severity]   (e.g. "critical" / "very_low" / "low")
#   2. ALERT_CHANNELS[server]["default"]
#   3. ALERT_CHANNELS["_default"][severity]
#   4. ALERT_CHANNELS["_default"]["default"]
#   5. ALERT_CHANNEL_ID (global fallback above)
#
# Leave empty to use ALERT_CHANNEL_ID for everything.
# ---------------------------------------------------------------------------
ALERT_CHANNELS: Dict[str, Dict[str, int]] = {
    # "2491": {"critical": 111, "very_low": 222, "low": 222, "default": 333},
    # "_default": {"critical": 444},
}

# Optional dedicated channel for the daily /oao_stats snapshot.
# Falls back to ALERT_CHANNEL_ID (then to LOG_CHANNEL_ID) if 0.
STATS_CHANNEL_ID: int = 0
# Hour of the day (0-23, UTC) at which the daily stats post fires.
STATS_POST_HOUR_UTC: int = 12

# =========================================================================
# GAME / DOMAIN CONSTANTS
# =========================================================================
SERVERS: List[str] = [
    "2491",
    "2175",
    "2513",
    "2779",
    "2609",
    "2875",
]

# Pagination page size for the dashboard.
PER_PAGE: int = 15

# =========================================================================
# ALERT THRESHOLDS (in HOURS unless noted)
# =========================================================================
CRITICAL_HOURS: float = 1.0
VERY_LOW_HOURS: float = 3.0
LOW_HOURS: float = 6.0

# Dashboard color thresholds (in DAYS, matches display logic).
CRITICAL_DAYS: float = 5.0
LOW_DAYS: float = 10.0

# =========================================================================
# TASK INTERVALS (minutes)
# =========================================================================
ALERT_CHECK_INTERVAL_MIN: int = 10
DASHBOARD_REFRESH_INTERVAL_MIN: int = 5

# =========================================================================
# API CLIENT SETTINGS
# =========================================================================
API_TIMEOUT_SECONDS: int = 15
API_RETRY_ATTEMPTS: int = 3
API_RETRY_BASE_DELAY: float = 1.0  # exponential backoff base (seconds)

# =========================================================================
# SLASH COMMAND SYNC
# =========================================================================
# One or more Discord GUILD ids (comma-separated) to sync slash commands to
# instantly on startup. Leave unset for a global sync (up to ~1h propagation).
#
# NOTE: this is your Discord community/server id, NOT an ARK server tag.
# In Discord: Settings -> Advanced -> Developer Mode ON, then right-click
# your community icon -> Copy Server ID.
#
# Examples:
#   DEV_GUILD_ID=123456789012345678
#   DEV_GUILD_ID=123456789012345678,987654321098765432
_dev_guild_raw = os.getenv("DEV_GUILD_ID", "")
DEV_GUILD_IDS: List[int] = []
for _piece in _dev_guild_raw.split(","):
    _piece = _piece.strip()
    if not _piece:
        continue
    try:
        DEV_GUILD_IDS.append(int(_piece))
    except ValueError:
        pass

# Backwards-compatible single-value alias (first id, or 0 if none).
DEV_GUILD_ID: int = DEV_GUILD_IDS[0] if DEV_GUILD_IDS else 0

# =========================================================================
# PERSISTENCE (backlog #1 — survive restarts)
# =========================================================================
# Location for the small JSON file that stores dashboard message ids so
# refresh_dashboard() can keep editing them after a bot restart.
STATE_FILE_PATH: Path = Path(
    os.getenv("STATE_FILE_PATH", str(Path(__file__).parent / ".bot_state.json"))
)


def validate() -> None:
    """Fail fast at startup if required secrets are missing or malformed."""
    missing = [k for k, v in {"TOKEN": TOKEN, "API_KEY": API_KEY}.items() if not v]
    if missing:
        raise RuntimeError(
            f"Missing required environment variables: {', '.join(missing)}. "
            "Set them in your .env file (local) or Railway dashboard (prod)."
        )

    # Cheap sanity check — a real bot token is ~70 chars, has 2 dots, and no
    # surrounding quotes/whitespace. This catches the most common pasting
    # mistakes without ever logging the actual secret.
    token = TOKEN or ""
    problems = []
    if token != token.strip():
        problems.append("has leading/trailing whitespace")
    if token.startswith(('"', "'")) or token.endswith(('"', "'")):
        problems.append("is wrapped in quotes")
    if token.count(".") != 2:
        problems.append(f"expected 2 dots in a bot token, found {token.count('.')}")
    if len(token.strip()) < 50:
        problems.append(f"length looks too short ({len(token.strip())} chars)")

    # Masked preview: first 6 + last 4 characters, nothing in between.
    stripped = token.strip()
    if len(stripped) >= 10:
        preview = f"{stripped[:6]}...{stripped[-4:]} (len={len(stripped)})"
    else:
        preview = f"(len={len(stripped)})"

    import logging
    log = logging.getLogger(__name__)
    log.info("TOKEN preview: %s", preview)
    log.info(
        "TOKEN source diagnostic: .env file at %s exists=%s; "
        "os.environ has TOKEN key=%s (raw len=%d)",
        _ENV_FILE,
        _ENV_FILE_LOADED,
        "TOKEN" in os.environ,
        len(os.environ.get("TOKEN", "")),
    )
    if problems:
        log.error(
            "TOKEN value looks malformed: %s. Please re-copy from the Discord "
            "Developer Portal (Bot tab -> Reset Token) with no quotes/whitespace.",
            "; ".join(problems),
        )
