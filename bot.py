"""OAO Control Center — Discord bot entrypoint.

Loads config, wires up the bot, discovers cogs and starts the client.
Designed to run under Railway's `worker: python bot.py` process type.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
from pathlib import Path
from typing import List

# Make sure this script's directory (which contains `cogs/`) is on sys.path
# regardless of how the process is launched (Railway sometimes uses wrappers).
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import discord
from discord.ext import commands

import config

# -------------------------------------------------------------------------
# Logging
# -------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("bot")


# -------------------------------------------------------------------------
# Bot factory
# -------------------------------------------------------------------------
INITIAL_COGS: List[str] = [
    "cogs.logging_cog",
    "cogs.generators",
    "cogs.dinos",
    "cogs.spam_zones",
    "cogs.dashboard",
    "cogs.alerts",
    "cogs.stats",
]


def make_bot() -> commands.Bot:
    intents = discord.Intents.default()
    intents.message_content = True
    bot = commands.Bot(command_prefix="!", intents=intents)

    @bot.event
    async def on_ready() -> None:
        # Guild-scoped sync is nearly instant; global sync can take up to
        # ~1 hour. Set DEV_GUILD_ID (comma-separated for multiple) for
        # immediate availability.
        try:
            if config.DEV_GUILD_IDS:
                total = 0
                for gid in config.DEV_GUILD_IDS:
                    guild = discord.Object(id=gid)
                    bot.tree.copy_global_to(guild=guild)
                    synced = await bot.tree.sync(guild=guild)
                    total += len(synced)
                    log.info(
                        "Synced %d slash command(s) to guild %s (instant).",
                        len(synced),
                        gid,
                    )
                log.info(
                    "Total: %d slash commands synced across %d guild(s).",
                    total,
                    len(config.DEV_GUILD_IDS),
                )
            else:
                synced = await bot.tree.sync()
                log.info(
                    "Synced %d slash command(s) globally (may take up to ~1h "
                    "to appear in every guild).",
                    len(synced),
                )
        except discord.DiscordException as e:
            log.exception("Slash-command sync failed: %s", e)

        await bot.change_presence(
            activity=discord.Game(name="OAO Control Center")
        )
        log.info("Logged in as %s (id=%s)", bot.user, bot.user.id if bot.user else "?")

    @bot.event
    async def setup_hook() -> None:
        cogs_dir = _HERE / "cogs"
        if not cogs_dir.is_dir():
            log.error(
                "Missing cogs/ folder next to bot.py (expected at %s). "
                "None of the slash commands will be registered. Make sure the "
                "cogs/ directory is included in your Railway deployment / git repo.",
                cogs_dir,
            )
            return

        for ext in INITIAL_COGS:
            try:
                await bot.load_extension(ext)
                log.info("Loaded cog: %s", ext)
            except Exception as e:  # noqa: BLE001
                log.exception("Failed to load cog %s: %s", ext, e)

    return bot


async def _run_once() -> None:
    """Run a single bot session and clean up its aiohttp session on exit."""
    from api_client import api_client

    # Re-log the token preview on every restart so it's easy to find in logs.
    token = (config.TOKEN or "").strip()
    if len(token) >= 10:
        log.info(
            "About to login with token: %s...%s (len=%d)",
            token[:6],
            token[-4:],
            len(token),
        )
    else:
        log.info("About to login with token: (len=%d)", len(token))

    bot = make_bot()
    try:
        await bot.start(config.TOKEN)  # type: ignore[arg-type]
    finally:
        await api_client.close()
        if not bot.is_closed():
            await bot.close()


def main() -> None:
    config.validate()

    # Same auto-restart behaviour as the original bot.
    while True:
        try:
            asyncio.run(_run_once())
        except KeyboardInterrupt:
            log.info("Interrupted — shutting down.")
            return
        except Exception as e:  # noqa: BLE001
            log.exception("Bot crashed: %s", e)
            log.info("Restarting in 10 seconds...")
            time.sleep(10)


if __name__ == "__main__":
    main()
