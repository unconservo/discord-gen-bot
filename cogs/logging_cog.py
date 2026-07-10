"""User-action logging cog.

Exposes a bot-wide `log_action` coroutine that other cogs call to append
audit lines into `LOG_CHANNEL_ID`.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import discord
from discord.ext import commands

from config import LOG_CHANNEL_ID

log = logging.getLogger(__name__)


class LoggingCog(commands.Cog):
    """Provides `bot.log_action(...)` for other cogs."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        # Attach the helper directly to the bot instance so any cog can call
        # `await self.bot.log_action(...)` without extra imports.
        bot.log_action = self.log_action  # type: ignore[attr-defined]

    async def log_action(
        self,
        user: Any,
        action: str,
        name: str,
        server: str,
        value: Optional[str] = None,
    ) -> None:
        """Post a formatted audit line to the log channel."""
        ch = self.bot.get_channel(LOG_CHANNEL_ID)
        if not isinstance(ch, discord.TextChannel):
            log.debug(
                "Skipping log — LOG_CHANNEL_ID (%s) not resolvable to a text channel.",
                LOG_CHANNEL_ID,
            )
            return

        value_text = f" -> {value}" if value is not None else ""
        try:
            await ch.send(f"[log] {user} -> {action} -> {name} [{server}]{value_text}")
        except discord.DiscordException as e:
            log.warning("Failed to send log message: %s", e)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(LoggingCog(bot))
