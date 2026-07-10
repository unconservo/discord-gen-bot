"""Players cog — BattleMetrics COUNT-only lookup for ARK: Survival Ascended.

Why count-only? Official ASA servers sit behind Steam Datagram Relay
(SDR), so live *names* aren't reachable via A2S UDP. BattleMetrics
publishes the count anonymously; the full roster only exposes to the
server owner. We show the count on the button and link out to
BattleMetrics for anyone who wants the roster.
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Any, Dict

import aiohttp
import discord
from discord.ext import commands

from config import BATTLEMETRICS_BASE, BATTLEMETRICS_IDS

log = logging.getLogger(__name__)


async def fetch_bm_server(bm_id: str) -> Dict[str, Any]:
    """Return a normalised dict for a single BattleMetrics server.

    Shape::
        {"name": str, "status": str, "count": int, "max": int}
    """
    url = f"{BATTLEMETRICS_BASE}/{bm_id}"
    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as resp:
                payload = await resp.json(content_type=None)
    except Exception as e:  # noqa: BLE001
        log.warning("BattleMetrics fetch failed for %s: %s", bm_id, e)
        return {"name": "?", "status": "error", "count": 0, "max": 0}

    attrs = (payload.get("data") or {}).get("attributes") or {}
    return {
        "name": attrs.get("name", "?"),
        "status": attrs.get("status", "?"),
        "count": int(attrs.get("players") or 0),
        "max": int(attrs.get("maxPlayers") or 0),
    }


def build_players_embed(server: str, data: Dict[str, Any], bm_id: str) -> discord.Embed:
    """Compact 'players online' card for one server."""
    status = data.get("status", "?")
    color = {
        "online": 0x2ECC71,
        "offline": 0xE74C3C,
        "dead": 0xE74C3C,
        "error": 0x95A5A6,
    }.get(status, 0xF1C40F)

    bm_url = f"https://www.battlemetrics.com/servers/arksa/{bm_id}"
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
    embed.add_field(
        name="Roster",
        value=(
            f"[View live player list on BattleMetrics]({bm_url})\n"
            "*Official ASA servers hide player names behind Steam Datagram "
            "Relay — click the link to see who's on.*"
        ),
        inline=False,
    )
    embed.set_footer(text="Count via BattleMetrics")
    return embed


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
        embed = build_players_embed(self.server, data, bm_id)
        from cogs.dashboard import ServerMenuView  # lazy: avoid circular import

        await interaction.edit_original_response(
            content=None, embed=embed, view=ServerMenuView(self.server)
        )


class PlayersCog(commands.Cog):
    """Empty cog — exists so `bot.load_extension('cogs.players')` succeeds
    and PlayersButton stays importable across the bot."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(PlayersCog(bot))
