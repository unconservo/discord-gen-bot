"""Health cog — /oao_ping.

Pings every external PHP endpoint the bot depends on and reports latency +
status in a compact embed so you can diagnose outages without digging
through Railway logs.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Tuple

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

from config import (
    API_GET,
    API_KEY,
    API_RATHOLES,
    API_SERVER_SUMMARY,
    BATTLEMETRICS_BASE,
    BATTLEMETRICS_IDS,
    SERVERS,
)

log = logging.getLogger(__name__)

# Sample server used for endpoint sanity check.
_SAMPLE_SERVER = SERVERS[0] if SERVERS else ""


async def _ping(url: str, params: dict, timeout: float = 5.0) -> Tuple[str, int]:
    """Return (status_label, latency_ms). Never raises."""
    started = time.monotonic()
    try:
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=timeout)
        ) as session:
            async with session.get(url, params=params) as resp:
                await resp.read()
                latency_ms = int((time.monotonic() - started) * 1000)
                if 200 <= resp.status < 300:
                    return f"OK ({resp.status})", latency_ms
                return f"HTTP {resp.status}", latency_ms
    except asyncio.TimeoutError:
        return f"TIMEOUT >{int(timeout*1000)}ms", int(timeout * 1000)
    except Exception as e:  # noqa: BLE001
        latency_ms = int((time.monotonic() - started) * 1000)
        return f"ERROR: {type(e).__name__}", latency_ms


class HealthCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="oao_ping",
        description="Test all backend endpoints and show latency + status.",
    )
    async def oao_ping(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)

        # Build parallel pings — one per key endpoint.
        endpoints = [
            ("PHP · generators", API_GET, {"key": API_KEY}),
            ("PHP · server_summary", API_SERVER_SUMMARY, {"key": API_KEY, "server": _SAMPLE_SERVER}),
            ("PHP · ratholes", API_RATHOLES, {"key": API_KEY, "server": _SAMPLE_SERVER}),
        ]
        if BATTLEMETRICS_IDS:
            sample_bm_id = next(iter(BATTLEMETRICS_IDS.values()))
            endpoints.append(
                ("BattleMetrics", f"{BATTLEMETRICS_BASE}/{sample_bm_id}", {})
            )

        results = await asyncio.gather(
            *[_ping(url, params) for _, url, params in endpoints]
        )

        embed = discord.Embed(
            title="OAO Backend Health",
            color=0x2ECC71,  # will flip to red below if anything is failing
        )
        any_bad = False
        for (label, url, _), (status, latency) in zip(endpoints, results):
            ok = status.startswith("OK")
            if not ok:
                any_bad = True
            icon = ":green_circle:" if ok else ":red_circle:"
            embed.add_field(
                name=f"{icon} {label}",
                value=f"`{status}` · **{latency} ms**",
                inline=False,
            )

        if any_bad:
            embed.color = 0xE74C3C
            embed.set_footer(text="One or more endpoints are unhealthy.")
        else:
            embed.set_footer(text="All endpoints healthy.")

        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(HealthCog(bot))
