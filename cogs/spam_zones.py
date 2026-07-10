"""Spam zones management cog.

Owns spam-zone CRUD plus the per-server map image upload/display.
"""

from __future__ import annotations

import logging
from typing import List

import discord
from discord.ext import commands

from api_client import api_client
from config import (
    API_ADD_SPAM_ZONE,
    API_DELETE_SPAM_ZONE,
    API_SPAM_MAP,
    API_SPAM_ZONES,
    API_UPDATE_SPAM_MAP,
    API_UPDATE_SPAM_ZONE,
)

log = logging.getLogger(__name__)


# =========================================================================
# MODALS
# =========================================================================
class AddZoneModal(discord.ui.Modal, title="Add Spam Zone"):
    zone_name = discord.ui.TextInput(label="Zone Name")
    description = discord.ui.TextInput(
        label="Spam Description",
        style=discord.TextStyle.paragraph,
        required=False,
    )

    def __init__(self, server: str) -> None:
        super().__init__()
        self.server = server

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        await api_client.get(
            API_ADD_SPAM_ZONE,
            {
                "server": self.server,
                "zone_name": self.zone_name.value,
                "description": self.description.value,
            },
        )
        await interaction.followup.send("Zone Added", ephemeral=True)


class EditZoneModal(discord.ui.Modal, title="Edit Spam Zone"):
    zone_name = discord.ui.TextInput(label="Zone Name")
    description = discord.ui.TextInput(
        label="Spam Description",
        style=discord.TextStyle.paragraph,
        required=False,
    )

    def __init__(self, zone_id: int, current_name: str, current_description: str) -> None:
        super().__init__()
        self.zone_id = zone_id
        self.zone_name.default = current_name
        self.description.default = current_description or ""

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        await api_client.get(
            API_UPDATE_SPAM_ZONE,
            {
                "id": self.zone_id,
                "zone_name": self.zone_name.value,
                "description": self.description.value,
            },
        )
        await interaction.followup.send("Zone Updated", ephemeral=True)


class SpamMapModal(discord.ui.Modal, title="Update Server Map"):
    image_url = discord.ui.TextInput(
        label="Map Image URL", required=True, max_length=1000
    )

    def __init__(self, server: str) -> None:
        super().__init__()
        self.server = server

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        await api_client.get(
            API_UPDATE_SPAM_MAP,
            {"server": self.server, "image_url": self.image_url.value},
        )
        await interaction.followup.send("Map Updated", ephemeral=True)


# =========================================================================
# SELECTS
# =========================================================================
class DeleteZoneSelect(discord.ui.Select):
    def __init__(self, data: List[dict]) -> None:
        self.records = data
        options = [
            discord.SelectOption(label=row["zone_name"][:100], value=str(row["id"]))
            for row in data[:25]
        ]
        super().__init__(placeholder="Select zone to delete...", options=options)

    async def callback(self, interaction: discord.Interaction) -> None:
        zone_id = int(self.values[0])
        row = next(r for r in self.records if int(r["id"]) == zone_id)
        await api_client.get(API_DELETE_SPAM_ZONE, {"id": zone_id})
        await interaction.response.send_message(
            f"Deleted Zone: {row['zone_name']}", ephemeral=True
        )


class DeleteZoneSelectView(discord.ui.View):
    def __init__(self, data: List[dict]) -> None:
        super().__init__(timeout=120)
        self.add_item(DeleteZoneSelect(data))


class EditZoneSelect(discord.ui.Select):
    def __init__(self, data: List[dict]) -> None:
        self.records = data
        options = [
            discord.SelectOption(label=row["zone_name"][:100], value=str(row["id"]))
            for row in data[:25]
        ]
        super().__init__(placeholder="Select zone to edit...", options=options)

    async def callback(self, interaction: discord.Interaction) -> None:
        zone_id = int(self.values[0])
        row = next(r for r in self.records if int(r["id"]) == zone_id)
        await interaction.response.send_modal(
            EditZoneModal(zone_id, row["zone_name"], row["description"])
        )


class EditZoneSelectView(discord.ui.View):
    def __init__(self, data: List[dict]) -> None:
        super().__init__(timeout=120)
        self.add_item(EditZoneSelect(data))


# =========================================================================
# BUTTONS
# =========================================================================
class AddZoneButton(discord.ui.Button):
    def __init__(self, server: str) -> None:
        super().__init__(label="Add Zone", style=discord.ButtonStyle.success)
        self.server = server

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(AddZoneModal(self.server))


class EditZoneButton(discord.ui.Button):
    def __init__(self, server: str) -> None:
        super().__init__(label="Edit Zone", style=discord.ButtonStyle.primary)
        self.server = server

    async def callback(self, interaction: discord.Interaction) -> None:
        data = await api_client.get(API_SPAM_ZONES, {"server": self.server})
        if not data:
            await interaction.response.send_message("No zones found", ephemeral=True)
            return
        await interaction.response.send_message(
            "Select zone to edit", view=EditZoneSelectView(data), ephemeral=True
        )


class DeleteZoneButton(discord.ui.Button):
    def __init__(self, server: str) -> None:
        super().__init__(label="Delete Zone", style=discord.ButtonStyle.danger)
        self.server = server

    async def callback(self, interaction: discord.Interaction) -> None:
        data = await api_client.get(API_SPAM_ZONES, {"server": self.server})
        if not data:
            await interaction.response.send_message("No zones found", ephemeral=True)
            return
        await interaction.response.send_message(
            "Select zone to delete",
            view=DeleteZoneSelectView(data),
            ephemeral=True,
        )


class UploadMapButton(discord.ui.Button):
    def __init__(self, server: str) -> None:
        super().__init__(label="Upload Map", style=discord.ButtonStyle.success)
        self.server = server

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(SpamMapModal(self.server))


class RefreshSpamButton(discord.ui.Button):
    def __init__(self, server: str) -> None:
        super().__init__(label="Refresh", style=discord.ButtonStyle.secondary)
        self.server = server

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        data = await api_client.get(API_SPAM_ZONES, {"server": self.server})
        map_data = await api_client.get(API_SPAM_MAP, {"server": self.server})
        await interaction.edit_original_response(
            content=None,
            embed=_build_spam_embed(self.server, data, map_data),
            view=SpamView(self.server),
        )


def _build_spam_embed(server: str, data: list, map_data) -> discord.Embed:
    embed = discord.Embed(title=f"Spam - Server {server}", color=0xFF9900)
    if isinstance(map_data, dict) and map_data.get("image_url"):
        embed.set_image(url=map_data["image_url"])
        embed.add_field(
            name="Server Map URL", value=map_data["image_url"], inline=False
        )
    if not data:
        embed.description = "No spam zones configured."
    else:
        for row in data[:25]:
            embed.add_field(
                name=row["zone_name"],
                value=row["description"] or "No Description",
                inline=False,
            )
    return embed


# =========================================================================
# VIEWS
# =========================================================================
class SpamView(discord.ui.View):
    def __init__(self, server: str) -> None:
        super().__init__(timeout=None)
        self.server = server
        self.add_item(AddZoneButton(server))
        self.add_item(EditZoneButton(server))
        self.add_item(DeleteZoneButton(server))
        self.add_item(UploadMapButton(server))
        self.add_item(RefreshSpamButton(server))

        from cogs.dashboard import BackButton  # lazy — avoid circular import

        self.add_item(BackButton(server))


class SpamMenuButton(discord.ui.Button):
    """Server-menu entry point into the spam zones screen."""

    def __init__(self, server: str) -> None:
        super().__init__(
            label="Spam",
            style=discord.ButtonStyle.secondary,
            custom_id=f"oao:menu:spam:{server}",
        )
        self.server = server

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        data = await api_client.get(API_SPAM_ZONES, {"server": self.server})
        map_data = await api_client.get(API_SPAM_MAP, {"server": self.server})
        await interaction.edit_original_response(
            content=None,
            embed=_build_spam_embed(self.server, data, map_data),
            view=SpamView(self.server),
        )


class SpamZonesCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(SpamZonesCog(bot))
