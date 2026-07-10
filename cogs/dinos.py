"""Dino feed TP management cog.

Owns the Defense Dino Feed TP list per server: add / edit / delete / refresh.
"""

from __future__ import annotations

from typing import List

import discord
from discord.ext import commands

from api_client import api_client
from config import (
    API_ADD_DINO_FEED,
    API_DELETE_DINO_FEED,
    API_DINO_FEED,
    API_UPDATE_DINO_FEED,
)


# =========================================================================
# MODALS
# =========================================================================
class AddDinoFeedModal(discord.ui.Modal, title="Add Defense Dino Feed TP"):
    tp_name = discord.ui.TextInput(label="TP Name", required=True, max_length=255)

    def __init__(self, server: str) -> None:
        super().__init__()
        self.server = server

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        await api_client.get(
            API_ADD_DINO_FEED,
            {"server": self.server, "tp_name": self.tp_name.value},
        )
        await interaction.followup.send("TP Added", ephemeral=True)


class EditDinoFeedModal(discord.ui.Modal, title="Edit Defense Dino Feed TP"):
    tp_name = discord.ui.TextInput(label="TP Name", required=True, max_length=255)

    def __init__(self, tp_id: int, current_name: str) -> None:
        super().__init__()
        self.tp_id = tp_id
        self.tp_name.default = current_name

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        await api_client.get(
            API_UPDATE_DINO_FEED,
            {"id": self.tp_id, "tp_name": self.tp_name.value},
        )
        await interaction.followup.send("TP Updated", ephemeral=True)


# =========================================================================
# SELECTS + VIEWS
# =========================================================================
class DeleteDinoFeedSelect(discord.ui.Select):
    def __init__(self, data: List[dict]) -> None:
        self.records = data
        options = [
            discord.SelectOption(label=row["tp_name"][:100], value=str(row["id"]))
            for row in data[:25]
        ]
        super().__init__(placeholder="Select TP to delete...", options=options)

    async def callback(self, interaction: discord.Interaction) -> None:
        tp_id = int(self.values[0])
        row = next(r for r in self.records if int(r["id"]) == tp_id)
        await api_client.get(API_DELETE_DINO_FEED, {"id": tp_id})
        await interaction.response.send_message(
            f"Deleted: {row['tp_name']}", ephemeral=True
        )


class DeleteDinoFeedSelectView(discord.ui.View):
    def __init__(self, data: List[dict]) -> None:
        super().__init__(timeout=120)
        self.add_item(DeleteDinoFeedSelect(data))


class EditDinoFeedSelect(discord.ui.Select):
    def __init__(self, data: List[dict]) -> None:
        self.records = data
        options = [
            discord.SelectOption(label=row["tp_name"][:100], value=str(row["id"]))
            for row in data[:25]
        ]
        super().__init__(placeholder="Select TP...", options=options)

    async def callback(self, interaction: discord.Interaction) -> None:
        tp_id = int(self.values[0])
        row = next(r for r in self.records if int(r["id"]) == tp_id)
        await interaction.response.send_modal(EditDinoFeedModal(tp_id, row["tp_name"]))


class EditDinoFeedSelectView(discord.ui.View):
    def __init__(self, data: List[dict]) -> None:
        super().__init__(timeout=120)
        self.add_item(EditDinoFeedSelect(data))


# =========================================================================
# BUTTONS
# =========================================================================
class AddDinoFeedButton(discord.ui.Button):
    def __init__(self, server: str) -> None:
        super().__init__(label="Add TP", style=discord.ButtonStyle.success)
        self.server = server

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(AddDinoFeedModal(self.server))


class EditDinoFeedButton(discord.ui.Button):
    def __init__(self, server: str) -> None:
        super().__init__(label="Edit TP", style=discord.ButtonStyle.primary)
        self.server = server

    async def callback(self, interaction: discord.Interaction) -> None:
        data = await api_client.get(API_DINO_FEED, {"server": self.server})
        if not data:
            await interaction.response.send_message(
                "No TP records found", ephemeral=True
            )
            return
        await interaction.response.send_message(
            "Select TP to edit",
            view=EditDinoFeedSelectView(data),
            ephemeral=True,
        )


class DeleteDinoFeedButton(discord.ui.Button):
    def __init__(self, server: str) -> None:
        super().__init__(label="Delete TP", style=discord.ButtonStyle.danger)
        self.server = server

    async def callback(self, interaction: discord.Interaction) -> None:
        data = await api_client.get(API_DINO_FEED, {"server": self.server})
        if not data:
            await interaction.response.send_message(
                "No TP records found", ephemeral=True
            )
            return
        await interaction.response.send_message(
            "Select TP to delete",
            view=DeleteDinoFeedSelectView(data),
            ephemeral=True,
        )


class RefreshDinoFeedButton(discord.ui.Button):
    def __init__(self, server: str) -> None:
        super().__init__(label="Refresh", style=discord.ButtonStyle.secondary)
        self.server = server

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        data = await api_client.get(API_DINO_FEED, {"server": self.server})
        await interaction.edit_original_response(
            content=None,
            embed=_build_dino_embed(self.server, data),
            view=DinoFeedView(self.server),
        )


def _build_dino_embed(server: str, data: list) -> discord.Embed:
    embed = discord.Embed(
        title=f"Defense Dino Feed TPs - Server {server}", color=0x00FF99
    )
    if not data:
        embed.description = "No Defense Dino Feed TPs configured."
    else:
        for row in data[:25]:
            embed.add_field(name=row["tp_name"], value="Active", inline=False)
    return embed


# =========================================================================
# TOP-LEVEL VIEW
# =========================================================================
class DinoFeedView(discord.ui.View):
    def __init__(self, server: str) -> None:
        super().__init__(timeout=None)
        self.server = server
        self.add_item(AddDinoFeedButton(server))
        self.add_item(EditDinoFeedButton(server))
        self.add_item(DeleteDinoFeedButton(server))
        self.add_item(RefreshDinoFeedButton(server))

        # Back button imported lazily to avoid circular dependency.
        from cogs.dashboard import BackButton

        self.add_item(BackButton(server))


class DinoFeedMenuButton(discord.ui.Button):
    """Server-menu entry point into the dino feed screen."""

    def __init__(self, server: str) -> None:
        super().__init__(
            label="Defense Dino Feed TPs",
            style=discord.ButtonStyle.primary,
            custom_id=f"oao:menu:dinos:{server}",
        )
        self.server = server

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        data = await api_client.get(API_DINO_FEED, {"server": self.server})
        await interaction.edit_original_response(
            content=None,
            embed=_build_dino_embed(self.server, data),
            view=DinoFeedView(self.server),
        )


class DinosCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(DinosCog(bot))
