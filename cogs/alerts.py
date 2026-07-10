"""Background alert-check cog.

Bug fixes:
    * #4 — reads/writes go through the shared `state` manager under a lock.
    * #5 — a generator is only marked **resolved** when it truly returns to
      healthy (> LOW_HOURS). Transitions between alerting severities (e.g.
      critical -> low) update the existing alert message in place instead of
      spamming a new one and instead of falsely marking things "resolved".
    * #6 — day/time math uses timezone-aware UTC and clamps to zero
      (via `utils.effective_days`).
    * #2 — DEFAULT_ROLE always defined and used as a safe fallback.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Optional

import discord
from discord.ext import commands, tasks

from api_client import api_client
from config import (
    ALERT_CHANNEL_ID,
    ALERT_CHANNELS,
    ALERT_CHECK_INTERVAL_MIN,
    API_GET,
    CRITICAL_HOURS,
    DEFAULT_ROLE,
    LOW_HOURS,
    SERVER_ROLES,
    VERY_LOW_HOURS,
)
from state import state
from utils import effective_days, format_time

log = logging.getLogger(__name__)


class AlertState(str, Enum):
    HEALTHY = "healthy"
    LOW = "low"
    VERY_LOW = "very_low"
    CRITICAL = "critical"


def classify(hours: float) -> AlertState:
    """Map remaining hours to an AlertState."""
    if hours <= CRITICAL_HOURS:
        return AlertState.CRITICAL
    if hours <= VERY_LOW_HOURS:
        return AlertState.VERY_LOW
    if hours <= LOW_HOURS:
        return AlertState.LOW
    return AlertState.HEALTHY


def _severity_message(
    alert_state: AlertState,
    server: str,
    name: str,
    days: float,
    role_mention: str = "",
) -> str:
    """Compose the human-readable text for an alert of the given severity."""
    label = {
        AlertState.CRITICAL: "CRITICAL",
        AlertState.VERY_LOW: "VERY LOW",
        AlertState.LOW: "LOW",
    }.get(alert_state, "")

    icon = "[!!]" if alert_state == AlertState.CRITICAL else "[!]"
    mention = f"{role_mention} " if role_mention else ""
    return f"{icon} {mention}[{server}] {name} {label} ({format_time(days)})".strip()


def resolve_alert_channel_id(server: str, alert_state: AlertState) -> int:
    """Look up the alert channel id for a given server + severity.

    Order: server->severity, server->default, _default->severity,
    _default->default, then the global `ALERT_CHANNEL_ID`.
    """
    severity_key = alert_state.value
    for scope in (server, "_default"):
        bucket = ALERT_CHANNELS.get(scope)
        if not bucket:
            continue
        if severity_key in bucket and bucket[severity_key]:
            return bucket[severity_key]
        if "default" in bucket and bucket["default"]:
            return bucket["default"]
    return ALERT_CHANNEL_ID


class AlertsCog(commands.Cog):
    """Runs the periodic alert check loop."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.check_alerts.start()

    def cog_unload(self) -> None:
        self.check_alerts.cancel()

    @tasks.loop(minutes=ALERT_CHECK_INTERVAL_MIN)
    async def check_alerts(self) -> None:
        try:
            await self._run_check()
        except Exception as e:  # noqa: BLE001 — task must never die
            log.exception("check_alerts failed: %s", e)

    @check_alerts.before_loop
    async def _before_check_alerts(self) -> None:
        await self.bot.wait_until_ready()

    async def _run_check(self) -> None:
        data = await api_client.get(API_GET)
        if not isinstance(data, list):
            log.warning("check_alerts: unexpected API_GET payload type")
            return

        async with state.lock():
            for g in data:
                await self._process_row(g)

    def _get_channel(self, server: str, alert_state: AlertState) -> Optional[discord.TextChannel]:
        channel_id = resolve_alert_channel_id(server, alert_state)
        if not channel_id:
            return None
        ch = self.bot.get_channel(channel_id)
        return ch if isinstance(ch, discord.TextChannel) else None

    async def _process_row(self, g: dict) -> None:
        name = g.get("name")
        if not name:
            return
        server = str(g.get("server", "Unknown"))

        # Use effective (timezone-safe, clamped) days — bug fix #6.
        remaining_days = effective_days(float(g["days"]), g.get("updated_at"))
        remaining_hours = remaining_days * 24

        new_state = classify(remaining_hours)
        prev = state.last_alerts.get(name)
        prev_state: Optional[AlertState] = (
            AlertState(prev["state"]) if prev else None
        )

        if new_state == prev_state:
            return  # no change, nothing to do

        # -----------------------------------------------------------------
        # Escalation / de-escalation between alert states (still not healthy).
        # -----------------------------------------------------------------
        if new_state != AlertState.HEALTHY:
            channel = self._get_channel(server, new_state)
            if channel is None:
                log.debug(
                    "check_alerts: no channel resolvable for server=%s severity=%s",
                    server,
                    new_state.value,
                )
                return

            role_id = SERVER_ROLES.get(server, DEFAULT_ROLE)
            role_mention = f"<@&{role_id}>" if role_id else ""
            text = _severity_message(
                new_state, server, name, remaining_days, role_mention
            )

            # If an alert message already exists AND it lives in the same channel
            # as the new severity, edit it in place. Otherwise send a fresh one
            # in the new channel and let the old message stand — bug fix #5:
            # do NOT send a "resolved" message for non-healthy transitions.
            prev_msg = prev.get("message") if prev else None
            if (
                isinstance(prev_msg, discord.Message)
                and prev_msg.channel.id == channel.id
            ):
                try:
                    await prev_msg.edit(content=text)
                    state.last_alerts[name] = {
                        "state": new_state.value,
                        "message": prev_msg,
                    }
                    return
                except discord.DiscordException as e:
                    log.warning("Failed to edit alert for %s: %s", name, e)

            try:
                msg = await channel.send(text)
                state.last_alerts[name] = {"state": new_state.value, "message": msg}
            except discord.DiscordException as e:
                log.warning("Failed to send alert for %s: %s", name, e)
            return

        # -----------------------------------------------------------------
        # Truly resolved (new_state == HEALTHY).
        # -----------------------------------------------------------------
        if prev:
            user = state.last_refuel_user.get(name, "Unknown")
            prev_msg = prev.get("message")
            if isinstance(prev_msg, discord.Message):
                try:
                    await prev_msg.edit(
                        content=(
                            f"[ok] [{server}] {name} resolved by **{user}** "
                            f"({format_time(remaining_days)})"
                        )
                    )
                except discord.DiscordException as e:
                    log.warning("Failed to edit resolved alert for %s: %s", name, e)

            state.last_alerts.pop(name, None)
            state.last_refuel_user.pop(name, None)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AlertsCog(bot))
