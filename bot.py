"""OAO Control Center — Discord bot entrypoint.

Loads config, wires up the bot, discovers cogs and starts the client.
Designed to run under Railway's `worker: python bot.py` process type.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import List

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
        await bot.tree.sync()
        await bot.change_presence(
            activity=discord.Game(name="OAO Control Center")
        )
        log.info("Logged in as %s (id=%s)", bot.user, bot.user.id if bot.user else "?")

    @bot.event
    async def setup_hook() -> None:
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
