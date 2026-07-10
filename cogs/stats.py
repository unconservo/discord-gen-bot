"""Stats cog — /oao_stats slash command and a daily scheduled snapshot post.

Posts a public embed summarising per-server generator status (total, critical,
low, healthy) plus dino-feed TP and spam-zone counts. The daily loop fires
once per day at `STATS_POST_HOUR_UTC`.
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks

from api_client import api_client
from config import (
    ALERT_CHANNEL_ID,
    API_GET,
    API_RATHOLES,
    API_SERVER_SUMMARY,
    LOG_CHANNEL_ID,
    SERVERS,
    STATS_CHANNEL_ID,
    STATS_POST_HOUR_UTC,
)
from utils import effective_days

log = logging.getLogger(__name__)


def _classify_gen(days: float) -> str:
    from config import CRITICAL_DAYS, LOW_DAYS  # local import to avoid cycles
    if days <= CRITICAL_DAYS:
        return "critical"
    if days <= LOW_DAYS:
        return "low"
    return "healthy"


async def build_stats_embed() -> discord.Embed:
    """Compose the stats snapshot embed from the two summary endpoints."""
    embed = discord.Embed(
        title="OAO Daily Snapshot",
        color=0x2ECC71,
        timestamp=dt.datetime.now(dt.timezone.utc),
    )

    # Try the aggregated server-summary endpoint first (cheap).
    summaries: dict[str, dict] = {}
    rathole_counts: dict[str, int] = {}
    for server in SERVERS:
        summary = await api_client.get(API_SERVER_SUMMARY, {"server": server})
        summaries[server] = summary if isinstance(summary, dict) else {}
        ratholes_data = await api_client.get(API_RATHOLES, {"server": server})
        rathole_counts[server] = (
            len(ratholes_data) if isinstance(ratholes_data, list) else 0
        )

    # Fall back / cross-check with the raw generator list so counts still make
    # sense if the summary endpoint is unavailable.
    raw = await api_client.get(API_GET)
    if isinstance(raw, list) and raw:
        for server in SERVERS:
            gens = [g for g in raw if str(g.get("server")) == server]
            if not gens:
                continue
            counts = {"critical": 0, "low": 0, "healthy": 0}
            for g in gens:
                remaining = effective_days(float(g["days"]), g.get("updated_at"))
                counts[_classify_gen(remaining)] += 1
            summaries[server] = {
                **summaries.get(server, {}),
                "generators": len(gens),
                **counts,
            }

    total_gens = 0
    total_critical = 0
    total_ratholes = 0
    for server in SERVERS:
        s = summaries.get(server, {})
        gens = int(s.get("generators", 0))
        critical = int(s.get("critical", 0))
        low = int(s.get("low", 0))
        healthy = int(s.get("healthy", 0))
        dino = int(s.get("dino_feed", 0))
        spam = int(s.get("spam_zones", 0))
        ratholes = int(rathole_counts.get(server, 0))

        total_gens += gens
        total_critical += critical
        total_ratholes += ratholes

        embed.add_field(
            name=f"Server {server}",
            value=(
                f"Generators: **{gens}**  |  Critical: **{critical}**\n"
                f"Low: {low}  |  Healthy: {healthy}\n"
                f"Dino TPs: {dino}  |  Spam Zones: {spam}  |  Ratholes: {ratholes}"
            ),
            inline=False,
        )

    embed.description = (
        f"**Total generators:** {total_gens}   |   "
        f"**Critical:** {total_critical}   |   "
        f"**Ratholes:** {total_ratholes}"
    )
    embed.set_footer(text="Auto-posted daily")
    return embed


def _default_stats_channel_id() -> int:
    return STATS_CHANNEL_ID or ALERT_CHANNEL_ID or LOG_CHANNEL_ID


class StatsCog(commands.Cog):
    """Owns /oao_stats and the daily-snapshot loop."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.daily_snapshot.start()

    def cog_unload(self) -> None:
        self.daily_snapshot.cancel()

    @app_commands.command(
        name="oao_stats",
        description="Post a snapshot of all servers (public in this channel).",
    )
    async def oao_stats(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        try:
            embed = await build_stats_embed()
            await interaction.followup.send(embed=embed)
        except Exception as e:  # noqa: BLE001
            log.exception("oao_stats command failed: %s", e)
            await interaction.followup.send(
                "Failed to build stats snapshot.", ephemeral=True
            )

    @tasks.loop(
        time=dt.time(hour=STATS_POST_HOUR_UTC, minute=0, tzinfo=dt.timezone.utc)
    )
    async def daily_snapshot(self) -> None:
        channel_id = _default_stats_channel_id()
        if not channel_id:
            log.debug("daily_snapshot: no channel configured; skipping.")
            return
        channel = self.bot.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            log.debug(
                "daily_snapshot: channel id %s not resolvable to a text channel.",
                channel_id,
            )
            return
        try:
            embed = await build_stats_embed()
            await channel.send(embed=embed)
        except Exception as e:  # noqa: BLE001 — task must never die
            log.exception("daily_snapshot post failed: %s", e)

    @daily_snapshot.before_loop
    async def _before_daily(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(StatsCog(bot))
