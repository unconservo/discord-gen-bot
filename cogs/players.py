"""Players cog — BattleMetrics player list & join/leave tracker.

Provides:
    * `fetch_bm_server(bm_id)` — one-shot fetch for a single server
    * `build_players_embed(server, data)` — embed showing current roster
    * `PlayersButton` — used from ServerMenuView (dashboard.py)
    * `PlayerTrackerCog` — background loop polling every N minutes and
      posting join/leave events to a dedicated tracker channel

BattleMetrics is a public read-only API; no auth key is required.
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Any, Dict, List, Optional, Set, Tuple

import aiohttp
import discord
from discord.ext import commands, tasks

from config import (
    BATTLEMETRICS_BASE,
    BATTLEMETRICS_IDS,
    BATTLEMETRICS_POLL_INTERVAL_MIN,
    LOG_CHANNEL_ID,
    PLAYER_TRACKER_CHANNEL_ID,
    SERVERS,
)

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# BattleMetrics HTTP helper (no API key, no retries — cheap public endpoint)
# ---------------------------------------------------------------------------
async def fetch_bm_server(bm_id: str) -> Dict[str, Any]:
    """Return a normalised dict for a single BattleMetrics server.

    Shape::
        {
            "name": "EU-PVP-Aberration2491",
            "status": "online" | "offline" | ...,
            "count": 1,
            "max": 70,
            "players": ["SurvivorBob", "TastierGem"],  # sorted names for display
            "player_details": {
                "SurvivorBob": {
                    "id": "123456",
                    "session_start": "2026-02-10T18:30:00.000Z",
                    "bm_url": "https://www.battlemetrics.com/players/123456"
                }
            }
        }

    On any HTTP / parse failure returns a status='error' shell so callers
    can render 'unknown' without crashing.
    """
    url = f"{BATTLEMETRICS_BASE}/{bm_id}?include=player,session"
    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as resp:
                payload = await resp.json(content_type=None)
    except Exception as e:  # noqa: BLE001
        log.warning("BattleMetrics fetch failed for %s: %s", bm_id, e)
        return {
            "name": "?",
            "status": "error",
            "count": 0,
            "max": 0,
            "players": [],
            "player_details": {},
        }

    data = payload.get("data") or {}
    attrs = data.get("attributes") or {}
    included = payload.get("included") or []

    # Map player_id -> player_name from the player entries.
    player_names: Dict[str, str] = {}
    for item in included:
        if item.get("type") != "player":
            continue
        pid = str(item.get("id", ""))
        pname = (item.get("attributes") or {}).get("name", "?")
        if pid:
            player_names[pid] = pname

    # Map player_id -> session_start from session entries where stop is null
    # (currently active session).
    session_starts: Dict[str, str] = {}
    for item in included:
        if item.get("type") != "session":
            continue
        sattrs = item.get("attributes") or {}
        if sattrs.get("stop") is not None:
            continue  # closed session; ignore
        rels = item.get("relationships") or {}
        pdata = ((rels.get("player") or {}).get("data") or {})
        pid = str(pdata.get("id", ""))
        if pid and sattrs.get("start"):
            session_starts[pid] = sattrs["start"]

    player_details: Dict[str, Dict[str, str]] = {}
    for pid, pname in player_names.items():
        player_details[pname] = {
            "id": pid,
            "session_start": session_starts.get(pid, ""),
            "bm_url": f"https://www.battlemetrics.com/players/{pid}",
        }

    return {
        "name": attrs.get("name", "?"),
        "status": attrs.get("status", "?"),
        "count": int(attrs.get("players") or 0),
        "max": int(attrs.get("maxPlayers") or 0),
        "players": sorted(player_names.values(), key=str.lower),
        "player_details": player_details,
    }


def build_players_embed(server: str, data: Dict[str, Any]) -> discord.Embed:
    """Render the 'who's on this server right now' embed."""
    status = data.get("status", "?")
    color = {
        "online": 0x2ECC71,
        "offline": 0xE74C3C,
        "dead": 0xE74C3C,
        "error": 0x95A5A6,
    }.get(status, 0xF1C40F)

    embed = discord.Embed(
        title=f"Server {server} — Players Online",
        description=(
            f"**{data.get('name', '?')}**\n"
            f"Status: `{status}`  •  Players: **{data.get('count', 0)}/"
            f"{data.get('max', 0)}**"
        ),
        color=color,
        timestamp=dt.datetime.now(dt.timezone.utc),
    )

    players: List[str] = data.get("players") or []
    details: Dict[str, Dict[str, str]] = data.get("player_details") or {}

    def _line(name: str) -> str:
        d = details.get(name) or {}
        url = d.get("bm_url")
        started = d.get("session_start", "")
        since = _format_duration(started)
        if url:
            return f"• [{name}]({url}) — {since}"
        return f"• {name}"

    if players:
        # Chunk into fields of ~10 names each so long lists don't overflow.
        chunk = 10
        for idx in range(0, len(players), chunk):
            slice_ = players[idx : idx + chunk]
            embed.add_field(
                name=f"Roster ({idx + 1}-{idx + len(slice_)})",
                value="\n".join(_line(p) for p in slice_),
                inline=False,
            )
    else:
        embed.add_field(
            name="Roster",
            value="*No players online.*"
            if status == "online"
            else "*Server offline or unreachable.*",
            inline=False,
        )

    embed.set_footer(text="Data via BattleMetrics")
    return embed


# ---------------------------------------------------------------------------
# Button for ServerMenuView (imported by dashboard.py)
# ---------------------------------------------------------------------------
class PlayersButton(discord.ui.Button):
    def __init__(self, server: str) -> None:
        super().__init__(
            label="Players Online",
            style=discord.ButtonStyle.primary,
            custom_id=f"oao:players:{server}",
        )
        self.server = server

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        bm_id = BATTLEMETRICS_IDS.get(self.server)
        if not bm_id:
            await interaction.followup.send(
                f"No BattleMetrics ID configured for server {self.server}.",
                ephemeral=True,
            )
            return
        data = await fetch_bm_server(bm_id)
        embed = build_players_embed(self.server, data)
        # Import lazily to avoid a circular import with dashboard.
        from cogs.dashboard import ServerMenuView

        await interaction.edit_original_response(
            content=None, embed=embed, view=ServerMenuView(self.server)
        )


# ---------------------------------------------------------------------------
# Background join/leave tracker
# ---------------------------------------------------------------------------
def _diff_rosters(
    old: Set[str], new: Set[str]
) -> Tuple[List[str], List[str]]:
    """Return (joined, left) sorted alphabetically."""
    return sorted(new - old, key=str.lower), sorted(old - new, key=str.lower)


def _format_duration(start_iso: str) -> str:
    """Return human-readable duration since an ISO timestamp string."""
    if not start_iso:
        return "unknown"
    try:
        start = dt.datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
    except ValueError:
        return "unknown"
    delta = dt.datetime.now(dt.timezone.utc) - start
    total_seconds = int(delta.total_seconds())
    if total_seconds < 0:
        return "unknown"
    hours, remainder = divmod(total_seconds, 3600)
    minutes = remainder // 60
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


class PlayerTrackerCog(commands.Cog):
    """Polls BattleMetrics every N minutes and posts join/leave notices."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        # server -> set of player names last seen
        self._rosters: Dict[str, Set[str]] = {}
        # server -> {player_name -> details dict from fetch_bm_server}
        self._details: Dict[str, Dict[str, Dict[str, str]]] = {}
        # Track whether the first sample has been taken so we don't spam
        # "everyone just joined" on startup.
        self._primed: Set[str] = set()
        self.poll_loop.start()

    def cog_unload(self) -> None:
        self.poll_loop.cancel()

    def _target_channel_id(self) -> int:
        return PLAYER_TRACKER_CHANNEL_ID or LOG_CHANNEL_ID or 0

    @tasks.loop(minutes=BATTLEMETRICS_POLL_INTERVAL_MIN)
    async def poll_loop(self) -> None:
        channel_id = self._target_channel_id()
        channel = self.bot.get_channel(channel_id) if channel_id else None

        for server in SERVERS:
            bm_id = BATTLEMETRICS_IDS.get(server)
            if not bm_id:
                continue
            try:
                data = await fetch_bm_server(bm_id)
            except Exception as e:  # noqa: BLE001
                log.warning("poll_loop fetch failed for %s: %s", server, e)
                continue

            new_roster: Set[str] = set(data.get("players") or [])
            new_details: Dict[str, Dict[str, str]] = (
                data.get("player_details") or {}
            )
            old_roster = self._rosters.get(server, set())
            old_details = self._details.get(server, {})
            self._rosters[server] = new_roster
            self._details[server] = new_details

            if server not in self._primed:
                self._primed.add(server)
                continue  # first sample — establish baseline silently

            if not isinstance(channel, discord.TextChannel):
                continue

            joined, left = _diff_rosters(old_roster, new_roster)
            if not joined and not left:
                continue

            embed = discord.Embed(
                title=f"Server {server} — Player Activity",
                color=0x3498DB,
                timestamp=dt.datetime.now(dt.timezone.utc),
            )
            if joined:
                lines = []
                for name in joined[:25]:
                    d = new_details.get(name) or {}
                    bm_url = d.get("bm_url")
                    session_start = d.get("session_start", "")
                    since = _format_duration(session_start)
                    if bm_url:
                        lines.append(f"• [{name}]({bm_url}) — session started {since} ago")
                    else:
                        lines.append(f"• {name}")
                embed.add_field(
                    name=f"Joined ({len(joined)})",
                    value="\n".join(lines) or "—",
                    inline=False,
                )
            if left:
                lines = []
                for name in left[:25]:
                    prev = old_details.get(name) or {}
                    bm_url = prev.get("bm_url")
                    session_start = prev.get("session_start", "")
                    duration = _format_duration(session_start)
                    if bm_url:
                        lines.append(f"• [{name}]({bm_url}) — was online for {duration}")
                    else:
                        lines.append(f"• {name} — was online for {duration}")
                embed.add_field(
                    name=f"Left ({len(left)})",
                    value="\n".join(lines) or "—",
                    inline=False,
                )
            embed.set_footer(
                text=(
                    f"Now {data.get('count', 0)}/{data.get('max', 0)} online "
                    f"• via BattleMetrics"
                )
            )
            try:
                await channel.send(embed=embed)
            except discord.DiscordException as e:
                log.warning("poll_loop send failed for %s: %s", server, e)

    @poll_loop.before_loop
    async def _before_poll(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(PlayerTrackerCog(bot))
