"""Ratholes cog — per-server rathole location + image management.

UX (mirrors the spam-zones flow, no slash commands):
    Server menu -> "Ratholes" button -> RatholeView with:
        Add / Edit / Delete / Upload Image / Refresh / Back
    * Add          -> modal (name, description)
    * Edit         -> select existing -> modal pre-filled (description)
    * Delete       -> select existing -> deleted
    * Upload Image -> select existing -> bot prompts you to drop a file in
                      the channel -> bot re-uploads it to the PHP backend's
                      /discord/ratholes/ folder and stores the permanent URL.

Requires the new PHP endpoint `upload_rathole_image.php` (see PHP_SETUP.md).
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import List, Optional

import aiohttp
import discord
from discord.ext import commands

from api_client import api_client
from config import (
    API_ADD_RATHOLE,
    API_DELETE_RATHOLE,
    API_KEY,
    API_RATHOLES,
    API_TIMEOUT_SECONDS,
    API_UPDATE_RATHOLE,
    API_UPLOAD_RATHOLE_IMAGE,
)

log = logging.getLogger(__name__)

# How long the bot waits for the user's follow-up image message.
IMAGE_UPLOAD_TIMEOUT_SECONDS = 90


# =========================================================================
# HELPERS
# =========================================================================
async def _fetch_ratholes(server: str) -> List[dict]:
    data = await api_client.get(API_RATHOLES, {"server": server})
    return data if isinstance(data, list) else []


async def _upload_image_to_backend(
    server: str, rathole_name: str, filename: str, data: bytes
) -> Optional[str]:
    """POST the image bytes to the PHP backend. Returns the public URL, or None."""
    form = aiohttp.FormData()
    form.add_field("file", data, filename=filename, content_type="application/octet-stream")

    params = {"key": API_KEY or "", "server": server, "rathole_name": rathole_name}
    timeout = aiohttp.ClientTimeout(total=max(30, API_TIMEOUT_SECONDS * 2))

    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                API_UPLOAD_RATHOLE_IMAGE, params=params, data=form
            ) as resp:
                text = await resp.text()
                if resp.status != 200:
                    log.warning(
                        "Image upload HTTP %s: %s", resp.status, text[:200]
                    )
                    return None
                try:
                    body = json.loads(text)
                except json.JSONDecodeError:
                    log.warning("Image upload returned non-JSON: %s", text[:200])
                    return None
                if body.get("ok") and body.get("url"):
                    return str(body["url"])
                log.warning("Image upload response missing url: %s", body)
                return None
    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        log.warning("Image upload failed: %s", e)
        return None


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
        description="No ratholes configured yet.\n\nClick **Add Rathole** to add one.",
        color=0x9B59B6,
    )


async def _wait_for_image_and_upload(
    interaction: discord.Interaction, server: str, rathole_name: str
) -> None:
    """Prompt the invoker to drop an image, then re-host it on the backend.

    Sends only ephemeral status messages to `interaction`. The user's own
    upload message stays in the channel (they can delete it if they like);
    we don't delete other people's messages because that requires Manage
    Messages permission we may not have.
    """
    await interaction.followup.send(
        f"Post an image in this channel within {IMAGE_UPLOAD_TIMEOUT_SECONDS}s to "
        f"attach it to **{rathole_name}**, or type `skip` to leave the image unchanged.",
        ephemeral=True,
    )

    def check(m: discord.Message) -> bool:
        return (
            m.author.id == interaction.user.id
            and m.channel.id == interaction.channel_id
            and (bool(m.attachments) or m.content.strip().lower() == "skip")
        )

    try:
        msg: discord.Message = await interaction.client.wait_for(
            "message", check=check, timeout=IMAGE_UPLOAD_TIMEOUT_SECONDS
        )
    except asyncio.TimeoutError:
        await interaction.followup.send(
            "No image received in time - rathole saved without an image.",
            ephemeral=True,
        )
        return

    if msg.content.strip().lower() == "skip" or not msg.attachments:
        await interaction.followup.send("Skipped image upload.", ephemeral=True)
        return

    attachment = msg.attachments[0]
    try:
        data = await attachment.read()
    except discord.DiscordException as e:
        log.warning("Failed to read attachment bytes: %s", e)
        await interaction.followup.send(
            "Couldn't read the uploaded file - please try again.", ephemeral=True
        )
        return

    url = await _upload_image_to_backend(
        server, rathole_name, attachment.filename or "image.png", data
    )

    if url:
        await interaction.followup.send(
            f"Image saved to backend and attached to **{rathole_name}**.",
            ephemeral=True,
        )
    else:
        await interaction.followup.send(
            "Image upload failed on the backend - rathole saved without an image.",
            ephemeral=True,
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
                "created_by": interaction.user.name,
            },
        )
        logger = getattr(interaction.client, "log_action", None)
        if logger:
            await logger(interaction.user, "RATHOLE_ADD", self.name.value, self.server)
        await interaction.followup.send(
            f"Rathole **{self.name.value}** added.", ephemeral=True
        )
        # Immediately offer image attachment.
        await _wait_for_image_and_upload(interaction, self.server, self.name.value)


class EditRatholeModal(discord.ui.Modal, title="Edit Rathole"):
    description = discord.ui.TextInput(
        label="Description",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=1000,
    )

    def __init__(self, server: str, row: dict) -> None:
        super().__init__()
        self.server = server
        self.rathole_name = row["rathole_name"]
        self.description.default = row.get("description") or ""

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        await api_client.get(
            API_UPDATE_RATHOLE,
            {
                "server": self.server,
                "rathole_name": self.rathole_name,
                "description": self.description.value,
            },
        )
        logger = getattr(interaction.client, "log_action", None)
        if logger:
            await logger(interaction.user, "RATHOLE_EDIT", self.rathole_name, self.server)
        await interaction.followup.send(
            f"Rathole **{self.rathole_name}** updated.", ephemeral=True
        )


# =========================================================================
# SELECTS
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


class UploadImageSelect(discord.ui.Select):
    def __init__(self, server: str, records: List[dict]) -> None:
        self.server = server
        self.records = records
        options = [
            discord.SelectOption(label=r["rathole_name"][:100], value=r["rathole_name"])
            for r in records[:25]
        ]
        super().__init__(
            placeholder="Select rathole to attach image to...", options=options
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        name = self.values[0]
        await interaction.response.defer(ephemeral=True)
        await _wait_for_image_and_upload(interaction, self.server, name)


class UploadImageSelectView(discord.ui.View):
    def __init__(self, server: str, records: List[dict]) -> None:
        super().__init__(timeout=120)
        self.add_item(UploadImageSelect(server, records))


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


class UploadImageButton(discord.ui.Button):
    def __init__(self, server: str) -> None:
        super().__init__(label="Upload Image", style=discord.ButtonStyle.success)
        self.server = server

    async def callback(self, interaction: discord.Interaction) -> None:
        records = await _fetch_ratholes(self.server)
        if not records:
            await interaction.response.send_message(
                "No ratholes yet - add one first.", ephemeral=True
            )
            return
        await interaction.response.send_message(
            "Select rathole to attach an image to",
            view=UploadImageSelectView(self.server, records),
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
        self.add_item(UploadImageButton(server))
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
# COG
# =========================================================================
class RatholesCog(commands.Cog):
    """No slash commands - all interaction is via the RatholeView buttons."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(RatholesCog(bot))
