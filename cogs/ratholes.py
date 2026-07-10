"""Ratholes cog — per-server rathole location + image management.

Slash commands (image uploads happen here because Discord modals cannot
accept file attachments):
    /rathole_add     server + name + description + optional image
    /rathole_edit    server + name + optional new_description + optional image
    /rathole_delete  server + name

Server-menu integration:
    RatholeMenuButton on `ServerMenuView` -> RatholeListView shows all
    ratholes for that server with their images.
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


def _build_rathole_embed(row: dict, index: int, total: int, server: str) -> discord.Embed:
    embed = discord.Embed(
        title=f"Rathole: {row.get('rathole_name', 'Unnamed')}",
        description=row.get("description") or "*No description*",
        color=0x9B59B6,
    )
    if row.get("image_url"):
        embed.set_image(url=row["image_url"])
    created_by = row.get("created_by")
    if created_by:
        embed.add_field(name="Added by", value=str(created_by), inline=True)
    embed.set_footer(text=f"Server {server}  |  {index + 1} / {total}")
    return embed


# =========================================================================
# PAGINATED LIST VIEW
# =========================================================================
class RatholeListView(discord.ui.View):
    """Paginated view of all ratholes for a server. One rathole per page."""

    def __init__(self, server: str, ratholes: List[dict], page: int = 0) -> None:
        super().__init__(timeout=None)
        self.server = server
        self.ratholes = ratholes
        self.page = max(0, min(page, len(ratholes) - 1)) if ratholes else 0

        # Nav buttons.
        self.add_item(RatholePrevButton())
        self.add_item(RatholeNextButton())
        self.add_item(RatholeRefreshButton(server))

        # Back to server menu.
        from cogs.dashboard import BackButton  # lazy — avoids circular import

        self.add_item(BackButton(server))

    def current_embed(self) -> discord.Embed:
        if not self.ratholes:
            return discord.Embed(
                title=f"Ratholes - Server {self.server}",
                description=(
                    "No ratholes configured yet.\n\n"
                    "Use `/rathole_add` to add one."
                ),
                color=0x9B59B6,
            )
        return _build_rathole_embed(
            self.ratholes[self.page], self.page, len(self.ratholes), self.server
        )


class RatholePrevButton(discord.ui.Button):
    def __init__(self) -> None:
        super().__init__(label="Prev", style=discord.ButtonStyle.secondary)

    async def callback(self, interaction: discord.Interaction) -> None:
        view: RatholeListView = self.view  # type: ignore[assignment]
        if not view.ratholes:
            await interaction.response.defer()
            return
        view.page = (view.page - 1) % len(view.ratholes)
        await interaction.response.edit_message(embed=view.current_embed(), view=view)


class RatholeNextButton(discord.ui.Button):
    def __init__(self) -> None:
        super().__init__(label="Next", style=discord.ButtonStyle.secondary)

    async def callback(self, interaction: discord.Interaction) -> None:
        view: RatholeListView = self.view  # type: ignore[assignment]
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
        ratholes = await _fetch_ratholes(self.server)
        new_view = RatholeListView(self.server, ratholes, page=0)
        await interaction.edit_original_response(
            content=None, embed=new_view.current_embed(), view=new_view
        )


# =========================================================================
# SERVER-MENU ENTRY BUTTON
# =========================================================================
class RatholeMenuButton(discord.ui.Button):
    """Added to ServerMenuView so users can browse ratholes per server."""

    def __init__(self, server: str) -> None:
        super().__init__(
            label="Ratholes",
            style=discord.ButtonStyle.primary,
            custom_id=f"oao:menu:ratholes:{server}",
        )
        self.server = server

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        ratholes = await _fetch_ratholes(self.server)
        view = RatholeListView(self.server, ratholes, page=0)
        await interaction.edit_original_response(
            content=None, embed=view.current_embed(), view=view
        )


# =========================================================================
# SLASH COMMANDS
# =========================================================================
def _server_choices() -> List[app_commands.Choice[str]]:
    return [app_commands.Choice(name=s, value=s) for s in SERVERS]


class RatholesCog(commands.Cog):
    """Slash commands for creating / editing / deleting ratholes."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ------------------------------------------------------------------
    # /rathole_add
    # ------------------------------------------------------------------
    @app_commands.command(
        name="rathole_add",
        description="Add a rathole location to a server (optionally with an image).",
    )
    @app_commands.describe(
        server="ARK server tag (e.g. 2491)",
        name="Short name for this rathole",
        description="Longer notes on where / how to find it",
        image="Screenshot (optional)",
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
            f"Rathole **{name}** added to server **{server.value}**{img_note}.",
            ephemeral=True,
        )

    # ------------------------------------------------------------------
    # /rathole_edit
    # ------------------------------------------------------------------
    @app_commands.command(
        name="rathole_edit",
        description="Edit a rathole's description and/or replace its image.",
    )
    @app_commands.describe(
        server="ARK server tag",
        name="Name of the rathole to edit",
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
                "Nothing to update - supply `description` and/or `image`.",
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
            f"Rathole **{name}** updated on server **{server.value}**.",
            ephemeral=True,
        )

    # ------------------------------------------------------------------
    # /rathole_delete
    # ------------------------------------------------------------------
    @app_commands.command(
        name="rathole_delete",
        description="Delete a rathole from a server.",
    )
    @app_commands.describe(server="ARK server tag", name="Name of the rathole")
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
            f"Rathole **{name}** deleted from server **{server.value}**.",
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(RatholesCog(bot))
