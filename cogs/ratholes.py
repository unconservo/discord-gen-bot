"""Ratholes cog — per-server rathole location + image management.

UX (mirrors the spam-zones flow):
    Server menu -> "Ratholes" button -> RatholeView with:
        Add / Edit / Delete / Refresh / Back
    * Add    -> modal (name, description, image URL)
    * Edit   -> select existing rathole -> modal pre-filled
    * Delete -> select existing rathole -> confirmation

Slash commands (still supported, useful for direct file uploads because
Discord modals cannot accept file attachments):
    /rathole_add / /rathole_edit / /rathole_delete
"""

from __future__ import annotations

import logging
from typing import List, Optional

import discord
from discord import app_commands
from discord.ext import commands

from api_client import api_client
from config import (
    API_ADD_RATHOLE,
    API_DELETE_RATHOLE,
    API_RATHOLES,
    API_UPDATE_RATHOLE,
    SERVERS,
)

log = logging.getLogger(__name__)


# =========================================================================
# HELPERS
# =========================================================================
async def _fetch_ratholes(server: str) -> List[dict]:
    data = await api_client.get(API_RATHOLES, {"server": server})
    return data if isinstance(data, list) else []


def _rathole_embed(row: dict, index: int, total: int, server: str) -> discord.Embed:
    embed = discord.Embed(
        title=f"Rathole: {row.get('rathole_name', 'Unnamed')}",
        description=row.get("description") or "*No description*",
        color=0x9B59B6,
    )
    if row.get("image_url"):
        embed.set_image(url=row["image_url"])
    if row.get("created_by"):
        embed.add_field(name="Added by", value=str(row["created_by"]), inline=True)
    embed.set_footer(text=f"Server {server}  |  {index + 1} / {total}")
    return embed


def _empty_embed(server: str) -> discord.Embed:
    return discord.Embed(
        title=f"Ratholes - Server {server}",
        description=(
            "No ratholes configured yet.\n\n"
            "Click **Add Rathole** or use `/rathole_add`."
        ),
        color=0x9B59B6,
    )


# =========================================================================
# MODALS
# =========================================================================
class AddRatholeModal(discord.ui.Modal, title="Add Rathole"):
    name = discord.ui.TextInput(label="Rathole Name", max_length=255)
    description = discord.ui.TextInput(
        label="Description",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=1000,
    )
    image_url = discord.ui.TextInput(
        label="Image URL (optional)",
        placeholder="Right-click any Discord image -> Copy Link, then paste here",
        required=False,
        max_length=1000,
    )

    def __init__(self, server: str) -> None:
        super().__init__()
        self.server = server

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        await api_client.get(
            API_ADD_RATHOLE,
            {
                "server": self.server,
                "rathole_name": self.name.value,
                "description": self.description.value,
                "image_url": self.image_url.value,
                "created_by": interaction.user.name,
            },
        )
        logger = getattr(interaction.client, "log_action", None)
        if logger:
            await logger(interaction.user, "RATHOLE_ADD", self.name.value, self.server)
        await interaction.followup.send(
            f"Rathole **{self.name.value}** added.", ephemeral=True
        )


class EditRatholeModal(discord.ui.Modal, title="Edit Rathole"):
    description = discord.ui.TextInput(
        label="Description",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=1000,
    )
    image_url = discord.ui.TextInput(
        label="Image URL",
        placeholder="Paste a new URL, or leave unchanged",
        required=False,
        max_length=1000,
    )

    def __init__(self, server: str, row: dict) -> None:
        super().__init__()
        self.server = server
        self.rathole_name = row["rathole_name"]
        self.description.default = row.get("description") or ""
        self.image_url.default = row.get("image_url") or ""

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        params = {
            "server": self.server,
            "rathole_name": self.rathole_name,
            "description": self.description.value,
            "image_url": self.image_url.value,
        }
        await api_client.get(API_UPDATE_RATHOLE, params)
        logger = getattr(interaction.client, "log_action", None)
        if logger:
            await logger(interaction.user, "RATHOLE_EDIT", self.rathole_name, self.server)
        await interaction.followup.send(
            f"Rathole **{self.rathole_name}** updated.", ephemeral=True
        )


# =========================================================================
# SELECTS (edit / delete pickers)
# =========================================================================
class EditRatholeSelect(discord.ui.Select):
    def __init__(self, server: str, records: List[dict]) -> None:
        self.server = server
        self.records = records
        options = [
            discord.SelectOption(label=r["rathole_name"][:100], value=r["rathole_name"])
            for r in records[:25]
        ]
        super().__init__(placeholder="Select rathole to edit...", options=options)

    async def callback(self, interaction: discord.Interaction) -> None:
        name = self.values[0]
        row = next(r for r in self.records if r["rathole_name"] == name)
        await interaction.response.send_modal(EditRatholeModal(self.server, row))


class EditRatholeSelectView(discord.ui.View):
    def __init__(self, server: str, records: List[dict]) -> None:
        super().__init__(timeout=120)
        self.add_item(EditRatholeSelect(server, records))


class DeleteRatholeSelect(discord.ui.Select):
    def __init__(self, server: str, records: List[dict]) -> None:
        self.server = server
        self.records = records
        options = [
            discord.SelectOption(label=r["rathole_name"][:100], value=r["rathole_name"])
            for r in records[:25]
        ]
        super().__init__(placeholder="Select rathole to delete...", options=options)

    async def callback(self, interaction: discord.Interaction) -> None:
        name = self.values[0]
        await api_client.get(
            API_DELETE_RATHOLE,
            {"server": self.server, "rathole_name": name},
        )
        logger = getattr(interaction.client, "log_action", None)
        if logger:
            await logger(interaction.user, "RATHOLE_DELETE", name, self.server)
        await interaction.response.send_message(
            f"Deleted rathole **{name}**.", ephemeral=True
        )


class DeleteRatholeSelectView(discord.ui.View):
    def __init__(self, server: str, records: List[dict]) -> None:
        super().__init__(timeout=120)
        self.add_item(DeleteRatholeSelect(server, records))


# =========================================================================
# ACTION BUTTONS
# =========================================================================
class AddRatholeButton(discord.ui.Button):
    def __init__(self, server: str) -> None:
        super().__init__(label="Add Rathole", style=discord.ButtonStyle.success)
        self.server = server

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(AddRatholeModal(self.server))


class EditRatholeButton(discord.ui.Button):
    def __init__(self, server: str) -> None:
        super().__init__(label="Edit Rathole", style=discord.ButtonStyle.primary)
        self.server = server

    async def callback(self, interaction: discord.Interaction) -> None:
        records = await _fetch_ratholes(self.server)
        if not records:
            await interaction.response.send_message("No ratholes found.", ephemeral=True)
            return
        await interaction.response.send_message(
            "Select rathole to edit",
            view=EditRatholeSelectView(self.server, records),
            ephemeral=True,
        )


class DeleteRatholeButton(discord.ui.Button):
    def __init__(self, server: str) -> None:
        super().__init__(label="Delete Rathole", style=discord.ButtonStyle.danger)
        self.server = server

    async def callback(self, interaction: discord.Interaction) -> None:
        records = await _fetch_ratholes(self.server)
        if not records:
            await interaction.response.send_message("No ratholes found.", ephemeral=True)
            return
        await interaction.response.send_message(
            "Select rathole to delete",
            view=DeleteRatholeSelectView(self.server, records),
            ephemeral=True,
        )


class RatholePrevButton(discord.ui.Button):
    def __init__(self) -> None:
        super().__init__(label="Prev", style=discord.ButtonStyle.secondary)

    async def callback(self, interaction: discord.Interaction) -> None:
        view: "RatholeView" = self.view  # type: ignore[assignment]
        if not view.ratholes:
            await interaction.response.defer()
            return
        view.page = (view.page - 1) % len(view.ratholes)
        await interaction.response.edit_message(embed=view.current_embed(), view=view)


class RatholeNextButton(discord.ui.Button):
    def __init__(self) -> None:
        super().__init__(label="Next", style=discord.ButtonStyle.secondary)

    async def callback(self, interaction: discord.Interaction) -> None:
        view: "RatholeView" = self.view  # type: ignore[assignment]
        if not view.ratholes:
            await interaction.response.defer()
            return
        view.page = (view.page + 1) % len(view.ratholes)
        await interaction.response.edit_message(embed=view.current_embed(), view=view)


class RatholeRefreshButton(discord.ui.Button):
    def __init__(self, server: str) -> None:
        super().__init__(label="Refresh", style=discord.ButtonStyle.secondary)
        self.server = server

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        records = await _fetch_ratholes(self.server)
        new_view = RatholeView(self.server, records, page=0)
        await interaction.edit_original_response(
            content=None, embed=new_view.current_embed(), view=new_view
        )


# =========================================================================
# MAIN VIEW
# =========================================================================
class RatholeView(discord.ui.View):
    """Full CRUD view for ratholes on one server."""

    def __init__(self, server: str, ratholes: List[dict], page: int = 0) -> None:
        super().__init__(timeout=None)
        self.server = server
        self.ratholes = ratholes
        self.page = max(0, min(page, len(ratholes) - 1)) if ratholes else 0

        self.add_item(AddRatholeButton(server))
        self.add_item(EditRatholeButton(server))
        self.add_item(DeleteRatholeButton(server))
        self.add_item(RatholeRefreshButton(server))

        self.add_item(RatholePrevButton())
        self.add_item(RatholeNextButton())

        from cogs.dashboard import BackButton  # lazy import to avoid cycle

        self.add_item(BackButton(server))

    def current_embed(self) -> discord.Embed:
        if not self.ratholes:
            return _empty_embed(self.server)
        return _rathole_embed(
            self.ratholes[self.page], self.page, len(self.ratholes), self.server
        )


# =========================================================================
# SERVER-MENU ENTRY BUTTON
# =========================================================================
class RatholeMenuButton(discord.ui.Button):
    def __init__(self, server: str) -> None:
        super().__init__(
            label="Ratholes",
            style=discord.ButtonStyle.primary,
            custom_id=f"oao:menu:ratholes:{server}",
        )
        self.server = server

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        records = await _fetch_ratholes(self.server)
        view = RatholeView(self.server, records, page=0)
        await interaction.edit_original_response(
            content=None, embed=view.current_embed(), view=view
        )


# =========================================================================
# SLASH COMMANDS (kept — file-upload path)
# =========================================================================
def _server_choices() -> List[app_commands.Choice[str]]:
    return [app_commands.Choice(name=s, value=s) for s in SERVERS]


class RatholesCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="rathole_add",
        description="Add a rathole (supports direct file upload).",
    )
    @app_commands.describe(
        server="ARK server tag",
        name="Rathole name",
        description="Notes on the rathole",
        image="Optional screenshot",
    )
    @app_commands.choices(server=_server_choices())
    async def rathole_add(
        self,
        interaction: discord.Interaction,
        server: app_commands.Choice[str],
        name: str,
        description: str,
        image: Optional[discord.Attachment] = None,
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        params = {
            "server": server.value,
            "rathole_name": name,
            "description": description,
            "created_by": interaction.user.name,
        }
        if image is not None:
            params["image_url"] = image.url
        await api_client.get(API_ADD_RATHOLE, params)
        logger = getattr(interaction.client, "log_action", None)
        if logger:
            await logger(interaction.user, "RATHOLE_ADD", name, server.value)
        img_note = " with image" if image is not None else ""
        await interaction.followup.send(
            f"Rathole **{name}** added to **{server.value}**{img_note}.",
            ephemeral=True,
        )

    @app_commands.command(
        name="rathole_edit",
        description="Edit a rathole (upload a new image or update description).",
    )
    @app_commands.describe(
        server="ARK server tag",
        name="Rathole to edit",
        description="New description (optional)",
        image="New screenshot (optional)",
    )
    @app_commands.choices(server=_server_choices())
    async def rathole_edit(
        self,
        interaction: discord.Interaction,
        server: app_commands.Choice[str],
        name: str,
        description: Optional[str] = None,
        image: Optional[discord.Attachment] = None,
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        if description is None and image is None:
            await interaction.followup.send(
                "Nothing to update - supply description and/or image.",
                ephemeral=True,
            )
            return
        params: dict = {"server": server.value, "rathole_name": name}
        if description is not None:
            params["description"] = description
        if image is not None:
            params["image_url"] = image.url
        await api_client.get(API_UPDATE_RATHOLE, params)
        logger = getattr(interaction.client, "log_action", None)
        if logger:
            await logger(interaction.user, "RATHOLE_EDIT", name, server.value)
        await interaction.followup.send(
            f"Rathole **{name}** updated on **{server.value}**.",
            ephemeral=True,
        )

    @app_commands.command(
        name="rathole_delete",
        description="Delete a rathole.",
    )
    @app_commands.describe(server="ARK server tag", name="Rathole to delete")
    @app_commands.choices(server=_server_choices())
    async def rathole_delete(
        self,
        interaction: discord.Interaction,
        server: app_commands.Choice[str],
        name: str,
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        await api_client.get(
            API_DELETE_RATHOLE,
            {"server": server.value, "rathole_name": name},
        )
        logger = getattr(interaction.client, "log_action", None)
        if logger:
            await logger(interaction.user, "RATHOLE_DELETE", name, server.value)
        await interaction.followup.send(
            f"Rathole **{name}** deleted from **{server.value}**.",
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(RatholesCog(bot))
