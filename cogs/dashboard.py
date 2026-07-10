"""Dashboard cog — top-level menu, /oao_dashboard slash command, auto-refresh."""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands, tasks

from api_client import api_client
from config import API_RATHOLES, API_SERVER_SUMMARY, DASHBOARD_REFRESH_INTERVAL_MIN, SERVERS
from cogs.dinos import DinoFeedMenuButton
from cogs.generators import GeneratorsMenuButton, refresh_dashboard
from cogs.ratholes import RatholeMenuButton
from cogs.spam_zones import SpamMenuButton
from state import state

log = logging.getLogger(__name__)


# =========================================================================
# NAV BUTTONS
# =========================================================================
class HomeButton(discord.ui.Button):
    def __init__(self) -> None:
        super().__init__(
            label="Home",
            style=discord.ButtonStyle.secondary,
            custom_id="oao:nav:home",
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            content="OAO Control Center\n\nSelect Server",
            embed=None,
            view=ServerSelectionView(),
        )


class BackButton(discord.ui.Button):
    def __init__(self, server: str) -> None:
        super().__init__(
            label="Server Home",
            style=discord.ButtonStyle.secondary,
            custom_id=f"oao:nav:back:{server}",
        )
        self.server = server

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            content=f"Server {self.server}",
            embed=None,
            view=ServerMenuView(self.server),
        )


# =========================================================================
# SERVER SELECTION
# =========================================================================
class ServerButton(discord.ui.Button):
    def __init__(self, server: str) -> None:
        super().__init__(
            label=server,
            style=discord.ButtonStyle.primary,
            custom_id=f"oao:server:{server}",
        )
        self.server = server

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        summary = await api_client.get(API_SERVER_SUMMARY, {"server": self.server})
        if not isinstance(summary, dict):
            summary = {}

        # Count ratholes independently — server_summary.php doesn't include them.
        ratholes_data = await api_client.get(API_RATHOLES, {"server": self.server})
        rathole_count = len(ratholes_data) if isinstance(ratholes_data, list) else 0

        embed = discord.Embed(
            title=f"Server {self.server} Status", color=0x00FF99
        )
        embed.add_field(
            name="Generators",
            value=(
                f"Total: {summary.get('generators', 0)}\n"
                f"Critical: {summary.get('critical', 0)}\n"
                f"Low: {summary.get('low', 0)}\n"
                f"Healthy: {summary.get('healthy', 0)}"
            ),
            inline=False,
        )
        embed.add_field(
            name="Defense Dino Feed TPs",
            value=f"TP Locations: {summary.get('dino_feed', 0)}",
            inline=False,
        )
        embed.add_field(
            name="Spam",
            value=f"Zones: {summary.get('spam_zones', 0)}",
            inline=False,
        )
        embed.add_field(
            name="Ratholes",
            value=f"Locations: {rathole_count}",
            inline=False,
        )
        await interaction.edit_original_response(
            content=None, embed=embed, view=ServerMenuView(self.server)
        )


class ServerSelectionView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)
        for server in SERVERS:
            self.add_item(ServerButton(server))


class ServerMenuView(discord.ui.View):
    def __init__(self, server: str) -> None:
        super().__init__(timeout=None)
        self.server = server
        self.add_item(GeneratorsMenuButton(server))
        self.add_item(DinoFeedMenuButton(server))
        self.add_item(SpamMenuButton(server))
        self.add_item(RatholeMenuButton(server))
        from cogs.players import PlayersButton  # avoid circular import at import time
        self.add_item(PlayersButton(server))
        self.add_item(HomeButton())


# =========================================================================
# DASHBOARD COG
# =========================================================================
class DashboardCog(commands.Cog):
    """Registers the /oao_dashboard slash command and the auto-refresh loop."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.auto_refresh.start()

    def cog_unload(self) -> None:
        self.auto_refresh.cancel()

    async def cog_load(self) -> None:
        """Register persistent views (backlog #1)."""
        self.bot.add_view(ServerSelectionView())
        for server in SERVERS:
            self.bot.add_view(ServerMenuView(server))
        log.info("Registered persistent views for %d server(s).", len(SERVERS))

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        """Rehydrate saved dashboard message references (backlog #1)."""
        await self._rehydrate_dashboards()

    async def _rehydrate_dashboards(self) -> None:
        entries = state.load_persisted()
        if not entries:
            return
        loaded = 0
        for channel_id, message_id in entries:
            channel = self.bot.get_channel(channel_id)
            if not isinstance(channel, discord.TextChannel):
                continue
            try:
                msg = await channel.fetch_message(message_id)
                # Bypass persistence write here — we're reading, not adding new.
                async with state.lock():
                    state.dashboard_messages[channel_id] = msg
                loaded += 1
            except (discord.NotFound, discord.Forbidden):
                continue
            except discord.DiscordException as e:
                log.warning("Failed to rehydrate dashboard %s/%s: %s", channel_id, message_id, e)
        log.info("Rehydrated %d dashboard message(s).", loaded)

    @app_commands.command(
        name="oao_dashboard", description="Open the OAO Control Center."
    )
    async def oao_dashboard(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        msg = await interaction.followup.send(
            "OAO Control Center\n\nSelect Server", view=ServerSelectionView()
        )
        try:
            if isinstance(msg, discord.Message):
                await state.register_dashboard(msg.channel.id, msg)
        except discord.DiscordException as e:
            log.debug("Could not register dashboard message: %s", e)

    @tasks.loop(minutes=DASHBOARD_REFRESH_INTERVAL_MIN)
    async def auto_refresh(self) -> None:
        """Bug fix #1 — periodically re-render registered dashboards."""
        try:
            await refresh_dashboard(self.bot)
        except Exception as e:  # noqa: BLE001 — task must never die
            log.exception("auto_refresh failed: %s", e)

    @auto_refresh.before_loop
    async def _before_auto_refresh(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(DashboardCog(bot))
