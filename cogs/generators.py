"""Generators cog — dashboard views, action modals, refresh helpers.

Owns:
    * `build_embed` — Discord embed for the paginated generator list.
    * `MainView` — the dashboard/search/tools tabbed container.
    * `ActionView` — per-generator Refuel/Subzone/Rename/Delete actions.
    * All modals: Add / Refuel / Subzone / Rename.
    * Search + Jump helpers, Critical / Show-All / Tools buttons.
    * `refresh_dashboard(bot)` — bug fix #1: actually re-edits the stored
       dashboard message with a fresh embed and view.
"""

from __future__ import annotations

import csv
import json
import logging
import os
from typing import List, Optional

import discord
from discord.ext import commands

from api_client import api_client
from config import (
    API_ADD,
    API_CLEAR_ALL,
    API_DELETE,
    API_GET,
    API_RESTORE,
    API_UPDATE,
    CRITICAL_DAYS,
    LOW_DAYS,
    PER_PAGE,
)
from state import state
from utils import effective_days, format_time, now_utc

log = logging.getLogger(__name__)


# =========================================================================
# EMBED BUILDER
# =========================================================================
def build_embed(
    data: List[dict],
    page: int = 0,
    server_filter: Optional[str] = None,
    subzone_filter: Optional[str] = None,
    highlight: Optional[str] = None,
) -> discord.Embed:
    """Compose the paginated generator dashboard embed."""

    if server_filter:
        data = [g for g in data if g.get("server") == server_filter]
    if subzone_filter:
        data = [g for g in data if g.get("subzone") == subzone_filter]

    title = "Generator Dashboard"
    if server_filter:
        title += f" -- {server_filter}"
    if subzone_filter:
        title += f" | {subzone_filter}"

    embed = discord.Embed(title=title, color=0x00FF99)

    if not data:
        embed.description = "No generators found"
        return embed

    data.sort(
        key=lambda g: (str(g.get("subzone", "")), float(g["days"]))
    )

    start = page * PER_PAGE
    end = start + PER_PAGE
    slice_data = data[start:end]

    current_subzone: Optional[str] = None
    for g in slice_data:
        subzone = g.get("subzone", "Unassigned")
        if subzone != current_subzone:
            current_subzone = subzone
            embed.add_field(
                name=f"[zone] {subzone}",
                value="----------------",
                inline=False,
            )

        # Bug fix #6 — timezone-safe elapsed-days math with clamp.
        days = effective_days(float(g["days"]), g.get("updated_at"))

        name_text = g["name"]
        if highlight and g["name"] == highlight:
            name_text = f"-> {g['name']}"

        if days <= CRITICAL_DAYS:
            value = f"**{format_time(days)} CRITICAL**"
        elif days <= LOW_DAYS:
            value = f"**{format_time(days)} LOW**"
        else:
            value = f"{format_time(days)} OK"

        embed.add_field(name=name_text, value=value, inline=False)

    total_pages = max(1, (len(data) - 1) // PER_PAGE + 1)

    critical_count = sum(1 for g in data if float(g["days"]) <= CRITICAL_DAYS)
    low_count = sum(
        1 for g in data if CRITICAL_DAYS < float(g["days"]) <= LOW_DAYS
    )
    healthy_count = sum(1 for g in data if float(g["days"]) > LOW_DAYS)

    embed.set_footer(
        text=(
            f"Page {page + 1}/{total_pages} | Total: {len(data)} | "
            f"Critical: {critical_count} | Low: {low_count} | "
            f"Healthy: {healthy_count}"
        )
    )
    return embed


# =========================================================================
# REFRESH HELPER (bug fix #1)
# =========================================================================
async def refresh_dashboard(bot: Optional[commands.Bot] = None) -> None:
    """Re-edit every registered dashboard message with a fresh **stats
    snapshot** (compact) instead of the giant paginated generator list.

    The full generator dashboard was too long — every auto-refresh would
    push a huge card into the channel. Users can still click into the
    generator dashboard via the server-selection buttons on the same message.

    Cogs register their dashboard messages via `state.register_dashboard(...)`.
    Failures are logged but never raised — a broken message should not kill
    the caller's flow.
    """
    dashboards = await state.all_dashboards()
    if not dashboards:
        log.info(
            "refresh_dashboard: no dashboards registered — nothing to refresh. "
            "Run /oao_dashboard or set DASHBOARD_CHANNEL_ID for auto-post."
        )
        return

    # Lazy imports — avoid circular deps between generators / stats / dashboard.
    from cogs.dashboard import ServerSelectionView
    from cogs.stats import build_stats_embed

    try:
        embed = await build_stats_embed()
    except Exception as e:  # noqa: BLE001
        log.warning("refresh_dashboard: build_stats_embed failed: %s", e)
        return

    log.info("refresh_dashboard: refreshing %d dashboard message(s).", len(dashboards))
    stale: list[int] = []
    for channel_id, message in dashboards.items():
        try:
            await message.edit(embed=embed, view=ServerSelectionView())
        except discord.NotFound:
            log.info("Dashboard in channel %s no longer exists — unregistering.", channel_id)
            stale.append(channel_id)
        except discord.DiscordException as e:
            log.warning("Failed to refresh dashboard in %s: %s", channel_id, e)

    for cid in stale:
        await state.unregister_dashboard(cid)


# =========================================================================
# ACTION MODALS
# =========================================================================
class AddModal(discord.ui.Modal, title="Add Generator"):
    name = discord.ui.TextInput(label="Name")
    days = discord.ui.TextInput(label="Days")
    server = discord.ui.TextInput(label="Server")
    subzone = discord.ui.TextInput(label="Subzone")

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            val = float(self.days.value)
        except ValueError:
            await interaction.followup.send("Invalid number", ephemeral=True)
            return

        await api_client.get(
            API_ADD,
            {
                "name": self.name.value,
                "days": val,
                "server": self.server.value,
                "subzone": self.subzone.value,
            },
        )

        logger = getattr(interaction.client, "log_action", None)
        if logger:
            await logger(
                interaction.user, "ADD", self.name.value, self.server.value, f"{val:.1f}d"
            )

        await interaction.followup.send("Generator added", ephemeral=True)
        await refresh_dashboard(interaction.client)


class RefuelModal(discord.ui.Modal, title="Refuel Generator"):
    days = discord.ui.TextInput(label="Set Days")

    def __init__(self, name: str) -> None:
        super().__init__()
        self.name = name

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            val = float(self.days.value)
        except ValueError:
            await interaction.followup.send("Invalid number", ephemeral=True)
            return

        await api_client.get(
            API_UPDATE,
            {
                "name": self.name,
                "days": val,
                # Match the original bot's format: naive-UTC ISO without a
                # timezone suffix. MySQL DATETIME/TIMESTAMP columns reject
                # the "+00:00" suffix produced by an aware datetime.
                "updated_at": now_utc().replace(tzinfo=None).isoformat(),
            },
        )

        await state.set_refuel_user(self.name, interaction.user.name)

        data = await api_client.get(API_GET)
        server = "Unknown"
        if isinstance(data, list):
            server = next(
                (g.get("server", "Unknown") for g in data if g["name"] == self.name),
                "Unknown",
            )

        logger = getattr(interaction.client, "log_action", None)
        if logger:
            await logger(interaction.user, "UPDATE", self.name, server, f"{val:.1f}d")

        await interaction.followup.send(
            f"{self.name} updated to {val:.1f} days", ephemeral=True
        )
        await refresh_dashboard(interaction.client)


class SubzoneModal(discord.ui.Modal, title="Update Subzone"):
    subzone = discord.ui.TextInput(label="Subzone", required=True, max_length=100)

    def __init__(self, name: str) -> None:
        super().__init__()
        self.name = name

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        await api_client.get(
            API_UPDATE, {"name": self.name, "subzone": self.subzone.value}
        )
        await interaction.followup.send(
            f"Subzone updated to: {self.subzone.value}", ephemeral=True
        )
        await refresh_dashboard(interaction.client)


class RenameModal(discord.ui.Modal, title="Rename Generator"):
    new_name = discord.ui.TextInput(
        label="New Generator Name", required=True, max_length=100
    )

    def __init__(self, name: str) -> None:
        super().__init__()
        self.old_name = name

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        await api_client.get(
            API_UPDATE, {"name": self.old_name, "new_name": self.new_name.value}
        )
        await interaction.followup.send(
            f"Renamed to: {self.new_name.value}", ephemeral=True
        )
        await refresh_dashboard(interaction.client)


# =========================================================================
# DELETE CONFIRM
# =========================================================================
class ConfirmDelete(discord.ui.View):
    def __init__(self, name: str) -> None:
        super().__init__()
        self.name = name

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.danger)
    async def confirm(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        data = await api_client.get(API_GET)
        server = "Unknown"
        if isinstance(data, list):
            server = next(
                (g.get("server", "Unknown") for g in data if g["name"] == self.name),
                "Unknown",
            )

        await api_client.get(API_DELETE, {"name": self.name})
        await state.set_last_deleted(self.name)

        logger = getattr(interaction.client, "log_action", None)
        if logger:
            await logger(interaction.user, "DELETE", self.name, server)

        await interaction.followup.send("Deleted", ephemeral=True)
        await refresh_dashboard(interaction.client)


# =========================================================================
# ACTION VIEW (per generator)
# =========================================================================
class ActionView(discord.ui.View):
    def __init__(self, name: str) -> None:
        super().__init__()
        self.name = name

    @discord.ui.button(label="Refuel", style=discord.ButtonStyle.success)
    async def refuel(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.send_modal(RefuelModal(self.name))

    @discord.ui.button(label="Subzone", style=discord.ButtonStyle.primary)
    async def subzone(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.send_modal(SubzoneModal(self.name))

    @discord.ui.button(label="Rename", style=discord.ButtonStyle.secondary)
    async def rename(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.send_modal(RenameModal(self.name))

    @discord.ui.button(label="Delete", style=discord.ButtonStyle.danger)
    async def delete(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.send_message(
            f"Delete {self.name}?",
            view=ConfirmDelete(self.name),
            ephemeral=True,
        )


# =========================================================================
# JUMP / SEARCH
# =========================================================================
class JumpButton(discord.ui.Button):
    def __init__(self, name: str) -> None:
        super().__init__(label=name[:80])
        self.gen_name = name

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            f"Loading {self.gen_name}...", ephemeral=True
        )
        data = await api_client.get(API_GET)
        if not data:
            await interaction.followup.send("Failed to load data", ephemeral=True)
            return

        view: "MainView" = self.view  # type: ignore[assignment]
        if view.server_filter:
            data = [
                g
                for g in data
                if view.server_filter.lower() in str(g.get("server", "")).lower()
            ]
        if not data:
            data = await api_client.get(API_GET)

        data.sort(key=lambda g: float(g["days"]))
        index = next(
            (i for i, g in enumerate(data) if g["name"] == self.gen_name), 0
        )
        page = index // PER_PAGE

        await interaction.followup.edit_message(
            interaction.message.id,
            content=f"Jumped to: {self.gen_name}",
            embed=build_embed(data, page, view.server_filter, highlight=self.gen_name),
            view=MainView(data, page, "dashboard", view.server_filter),
        )
        await interaction.followup.send(
            f"{self.gen_name}", view=ActionView(self.gen_name), ephemeral=True
        )


class SearchResultSelect(discord.ui.Select):
    def __init__(
        self, results: List[dict], server_filter: Optional[str], page: int = 0
    ) -> None:
        self.results = results
        self.server_filter = server_filter
        self.page = page

        start = page * PER_PAGE
        end = start + PER_PAGE
        page_results = results[start:end]

        options = [
            discord.SelectOption(label=g["name"][:100], value=g["name"])
            for g in page_results
        ]
        super().__init__(
            placeholder=f"Select Generator ({len(results)} found)", options=options
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        gen_name = self.values[0]
        data = await api_client.get(API_GET)
        if not isinstance(data, list):
            data = []
        data.sort(key=lambda g: float(g["days"]))
        index = next(
            (i for i, g in enumerate(data) if g["name"] == gen_name), 0
        )
        page = index // PER_PAGE

        await interaction.response.edit_message(
            content=f"Jumped to: {gen_name}",
            embed=build_embed(data, page, self.server_filter, highlight=gen_name),
            view=MainView(data, page, "dashboard", self.server_filter),
        )
        await interaction.followup.send(
            f"{gen_name}", view=ActionView(gen_name), ephemeral=True
        )


class SearchResultsPrevButton(discord.ui.Button):
    def __init__(self) -> None:
        super().__init__(label="Previous", style=discord.ButtonStyle.secondary)

    async def callback(self, interaction: discord.Interaction) -> None:
        view: "SearchResultsView" = self.view  # type: ignore[assignment]
        await interaction.response.edit_message(
            view=SearchResultsView(view.results, view.server_filter, view.page - 1)
        )


class SearchResultsNextButton(discord.ui.Button):
    def __init__(self) -> None:
        super().__init__(label="Next", style=discord.ButtonStyle.secondary)

    async def callback(self, interaction: discord.Interaction) -> None:
        view: "SearchResultsView" = self.view  # type: ignore[assignment]
        await interaction.response.edit_message(
            view=SearchResultsView(view.results, view.server_filter, view.page + 1)
        )


class SearchResultsView(discord.ui.View):
    def __init__(
        self, results: List[dict], server_filter: Optional[str], page: int = 0
    ) -> None:
        super().__init__(timeout=120)
        self.results = results
        self.server_filter = server_filter
        self.page = page

        total_pages = max(1, (len(results) - 1) // PER_PAGE + 1)
        self.add_item(SearchResultSelect(results, server_filter, page))
        if page > 0:
            self.add_item(SearchResultsPrevButton())
        if page < total_pages - 1:
            self.add_item(SearchResultsNextButton())


class SearchModal(discord.ui.Modal, title="Search Generator"):
    query = discord.ui.TextInput(
        label="Generator Name",
        placeholder="Type part of the generator name...",
        required=True,
    )

    def __init__(self, view: "MainView") -> None:
        super().__init__()
        self.view_ref = view

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)

        data = await api_client.get(API_GET)
        if not isinstance(data, list):
            data = []

        if self.view_ref.server_filter:
            data = [
                g
                for g in data
                if str(g.get("server", "")).strip()
                == str(self.view_ref.server_filter).strip()
            ]

        query = self.query.value.lower().strip()
        results = [g for g in data if query in g["name"].lower()]
        if not results:
            await interaction.followup.send(
                "No matching generators found.", ephemeral=True
            )
            return

        results.sort(key=lambda g: float(g["days"]))
        total_pages = max(1, (len(results) - 1) // PER_PAGE + 1)

        await interaction.followup.send(
            f"Found {len(results)} matching generators.\nPage 1/{total_pages}",
            view=SearchResultsView(results, self.view_ref.server_filter, page=0),
            ephemeral=True,
        )


class SearchInputButton(discord.ui.Button):
    def __init__(self) -> None:
        super().__init__(label="Search by Name", style=discord.ButtonStyle.primary)

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(SearchModal(self.view))  # type: ignore[arg-type]


# =========================================================================
# FILTER SELECTS
# =========================================================================
class ServerSelect(discord.ui.Select):
    def __init__(self, data: List[dict]) -> None:
        servers = sorted(
            {str(g.get("server")).strip() for g in data if g.get("server")}
        )
        options = [discord.SelectOption(label="All Servers", value="ALL")]
        options.extend(discord.SelectOption(label=s, value=s) for s in servers)
        super().__init__(placeholder="Filter by server...", options=options)

    async def callback(self, interaction: discord.Interaction) -> None:
        view: "MainView" = self.view  # type: ignore[assignment]
        selected = self.values[0]
        view.server_filter = None if selected == "ALL" else selected
        view.subzone_filter = None

        await interaction.response.edit_message(
            embed=build_embed(view.data, view.page, view.server_filter, None),
            view=MainView(view.data, view.page, view.tab, view.server_filter, None),
        )


class SubzoneSelect(discord.ui.Select):
    def __init__(
        self, data: List[dict], server_filter: Optional[str] = None
    ) -> None:
        subzones = sorted(
            {
                str(g.get("subzone")).strip()
                for g in data
                if g.get("subzone")
                and (not server_filter or str(g.get("server")) == str(server_filter))
            }
        )
        options = [discord.SelectOption(label="All Subzones", value="ALL")]
        options.extend(discord.SelectOption(label=s, value=s) for s in subzones)
        super().__init__(placeholder="Filter by subzone...", options=options)

    async def callback(self, interaction: discord.Interaction) -> None:
        view: "MainView" = self.view  # type: ignore[assignment]
        selected = self.values[0]
        view.subzone_filter = None if selected == "ALL" else selected

        await interaction.response.edit_message(
            embed=build_embed(
                view.data, view.page, view.server_filter, view.subzone_filter
            ),
            view=MainView(
                view.data,
                view.page,
                view.tab,
                view.server_filter,
                view.subzone_filter,
            ),
        )


class GeneratorSelect(discord.ui.Select):
    def __init__(self, data: List[dict], page: int = 0) -> None:
        start = page * PER_PAGE
        end = start + PER_PAGE
        page_data = data[start:end]
        options = [discord.SelectOption(label=g["name"]) for g in page_data]
        if not options:
            options = [discord.SelectOption(label="No generators")]
        super().__init__(placeholder="Select generator", options=options)

    async def callback(self, interaction: discord.Interaction) -> None:
        name = self.values[0]
        await interaction.response.send_message(
            f"{name}", view=ActionView(name), ephemeral=True
        )


class SearchSelect(discord.ui.Select):
    def __init__(self, data: List[dict]) -> None:
        options = [discord.SelectOption(label=g["name"]) for g in data]
        if not options:
            options = [discord.SelectOption(label="No generators")]
        super().__init__(placeholder="Search generator...", options=options)
        self.data = data

    async def callback(self, interaction: discord.Interaction) -> None:
        name = self.values[0]
        await interaction.response.send_message(
            f"{name}", view=ActionView(name), ephemeral=True
        )


# =========================================================================
# PAGINATION BUTTONS
# =========================================================================
class PrevButton(discord.ui.Button):
    def __init__(self) -> None:
        super().__init__(label="Prev")

    async def callback(self, interaction: discord.Interaction) -> None:
        view: "MainView" = self.view  # type: ignore[assignment]
        new_page = max(view.page - 1, 0)
        await interaction.response.edit_message(
            embed=build_embed(
                view.data, new_page, view.server_filter, view.subzone_filter
            ),
            view=MainView(
                view.data,
                new_page,
                view.tab,
                view.server_filter,
                view.subzone_filter,
            ),
        )


class NextButton(discord.ui.Button):
    def __init__(self) -> None:
        super().__init__(label="Next")

    async def callback(self, interaction: discord.Interaction) -> None:
        view: "MainView" = self.view  # type: ignore[assignment]
        max_page = (len(view.data) - 1) // PER_PAGE
        new_page = min(view.page + 1, max_page)
        await interaction.response.edit_message(
            embed=build_embed(
                view.data, new_page, view.server_filter, view.subzone_filter
            ),
            view=MainView(
                view.data,
                new_page,
                view.tab,
                view.server_filter,
                view.subzone_filter,
            ),
        )


# =========================================================================
# TOOLS BUTTONS
# =========================================================================
class CriticalButton(discord.ui.Button):
    def __init__(self) -> None:
        super().__init__(label="Critical")

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        data = await api_client.get(API_GET)
        view: "MainView" = self.view  # type: ignore[assignment]

        if view.server_filter:
            data = [
                g
                for g in data
                if str(g.get("server")).strip() == str(view.server_filter).strip()
            ]

        crit = [g for g in data if float(g["days"]) <= 1]
        if not crit:
            await interaction.followup.send(
                "No critical generators", ephemeral=True
            )
            return

        msg = "\n".join(f"{g['name']} -> {g['days']}d" for g in crit)
        await interaction.followup.send(msg, ephemeral=True)


class ShowAllButton(discord.ui.Button):
    def __init__(self) -> None:
        super().__init__(label="Show All")

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        data = await api_client.get(API_GET)
        view: "MainView" = self.view  # type: ignore[assignment]

        if view.server_filter:
            data = [
                g
                for g in data
                if str(g.get("server")).strip() == str(view.server_filter).strip()
            ]
        if not data:
            await interaction.followup.send("No generators found", ephemeral=True)
            return

        data.sort(key=lambda g: float(g["days"]))
        lines = [f"{g['name']} -> {g['days']}d" for g in data]

        chunks: List[str] = []
        current = ""
        for line in lines:
            if len(current) + len(line) + 1 > 1900:
                chunks.append(current)
                current = line
            else:
                current += ("\n" if current else "") + line
        if current:
            chunks.append(current)

        await interaction.followup.send(chunks[0], ephemeral=True)
        for chunk in chunks[1:]:
            await interaction.followup.send(chunk, ephemeral=True)


class AddButton(discord.ui.Button):
    def __init__(self) -> None:
        super().__init__(label="Add")

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(AddModal())


class UndoButton(discord.ui.Button):
    def __init__(self) -> None:
        super().__init__(label="Undo")

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        name = await state.pop_last_deleted()
        if not name:
            await interaction.followup.send("Nothing to undo", ephemeral=True)
            return

        await api_client.get(API_RESTORE, {"name": name})

        logger = getattr(interaction.client, "log_action", None)
        if logger:
            await logger(interaction.user, "UNDO", name, "Unknown")

        await interaction.followup.send("Restored", ephemeral=True)
        await refresh_dashboard(interaction.client)


class BackupButton(discord.ui.Button):
    def __init__(self) -> None:
        super().__init__(label="Backup")

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        data = await api_client.get(API_GET)
        path = "backup.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        await interaction.followup.send(file=discord.File(path), ephemeral=True)
        os.remove(path)


class CSVButton(discord.ui.Button):
    def __init__(self) -> None:
        super().__init__(label="CSV")

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        data = await api_client.get(API_GET)
        path = "gens.csv"
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Name", "Days"])
            for g in data:
                writer.writerow([g["name"], g["days"]])
        await interaction.followup.send(file=discord.File(path), ephemeral=True)
        os.remove(path)


class ResetAlertsButton(discord.ui.Button):
    def __init__(self) -> None:
        super().__init__(label="Alert Reset")

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        await state.clear_alerts()
        await interaction.followup.send("Alerts reset", ephemeral=True)


class HelpButton(discord.ui.Button):
    def __init__(self) -> None:
        super().__init__(label="Help")

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        msg = (
            "Generator Bot Help\n\n"
            "Dashboard -> Select -> Refuel/Delete\n"
            "Search -> Find / Critical / Show All\n"
            "Tools -> Add / Undo / Backup / CSV / Reset\n\n"
            "Alerts auto-track + resolve with user info."
        )
        await interaction.followup.send(msg, ephemeral=True)


# =========================================================================
# TABS
# =========================================================================
class TabButton(discord.ui.Button):
    def __init__(self, label: str, tab: str) -> None:
        super().__init__(label=label)
        self.tab = tab

    async def callback(self, interaction: discord.Interaction) -> None:
        data = await api_client.get(API_GET)
        await interaction.response.edit_message(
            embed=build_embed(data, 0, None, None),
            view=MainView(data, 0, self.tab, None, None),
        )


# =========================================================================
# NAV BUTTONS
# =========================================================================
class GeneratorBackButton(discord.ui.Button):
    def __init__(self, server: str) -> None:
        super().__init__(
            label="Server Home", style=discord.ButtonStyle.secondary, row=4
        )
        self.server = server

    async def callback(self, interaction: discord.Interaction) -> None:
        # Lazy import — avoids circular dependency with dashboard cog.
        from cogs.dashboard import ServerMenuView

        await interaction.response.edit_message(
            content=f"Server {self.server}",
            embed=None,
            view=ServerMenuView(self.server),
        )


class RefreshGeneratorButton(discord.ui.Button):
    def __init__(self, server: str) -> None:
        super().__init__(
            label="Refresh", style=discord.ButtonStyle.secondary, row=4
        )
        self.server = server

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        data = await api_client.get(API_GET)
        await interaction.edit_original_response(
            content=None,
            embed=build_embed(data, 0, self.server),
            view=MainView(data, 0, "dashboard", self.server),
        )


class GeneratorsMenuButton(discord.ui.Button):
    """Server-menu entry point into the generator dashboard."""

    def __init__(self, server: str) -> None:
        super().__init__(
            label="Generators",
            style=discord.ButtonStyle.success,
            custom_id=f"oao:menu:gens:{server}",
        )
        self.server = server

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        data = await api_client.get(API_GET)
        await interaction.edit_original_response(
            content=None,
            embed=build_embed(data, 0, self.server),
            view=MainView(data, 0, "dashboard", self.server),
        )
        # Register the message as a dashboard so background refresh keeps it fresh.
        try:
            msg = await interaction.original_response()
            await state.register_dashboard(msg.channel.id, msg)
        except discord.DiscordException as e:
            log.debug("Could not register dashboard message: %s", e)


# =========================================================================
# MAIN VIEW (tabbed dashboard)
# =========================================================================
class MainView(discord.ui.View):
    def __init__(
        self,
        data: List[dict],
        page: int = 0,
        tab: str = "dashboard",
        server_filter: Optional[str] = None,
        subzone_filter: Optional[str] = None,
    ) -> None:
        super().__init__(timeout=None)
        self.data = data
        self.page = page
        self.tab = tab
        self.server_filter = server_filter
        self.subzone_filter = subzone_filter

        # Tabs
        self.add_item(TabButton("Dashboard", "dashboard"))
        self.add_item(TabButton("Search", "search"))
        self.add_item(TabButton("Tools", "tools"))

        if tab == "dashboard":
            self.add_item(ServerSelect(data))
            self.add_item(SubzoneSelect(data, server_filter))
            self.add_item(PrevButton())
            self.add_item(NextButton())

            filtered = data
            if server_filter:
                filtered = [g for g in filtered if g.get("server") == server_filter]
            if subzone_filter:
                filtered = [g for g in filtered if g.get("subzone") == subzone_filter]

            self.add_item(GeneratorSelect(filtered, page))

            if server_filter:
                self.add_item(RefreshGeneratorButton(server_filter))
                self.add_item(GeneratorBackButton(server_filter))

        elif tab == "search":
            self.add_item(ServerSelect(data))
            self.add_item(SubzoneSelect(data, server_filter))

            filtered = data
            if server_filter:
                filtered = [g for g in filtered if g.get("server") == server_filter]
            if subzone_filter:
                filtered = [g for g in filtered if g.get("subzone") == subzone_filter]

            start = page * PER_PAGE
            end = start + PER_PAGE
            page_data = filtered[start:end]

            self.add_item(PrevButton())
            self.add_item(NextButton())
            self.add_item(SearchSelect(page_data))
            self.add_item(SearchInputButton())
            self.add_item(CriticalButton())
            self.add_item(ShowAllButton())

        elif tab == "tools":
            self.add_item(AddButton())
            self.add_item(UndoButton())
            self.add_item(BackupButton())
            self.add_item(CSVButton())
            self.add_item(ResetAlertsButton())
            self.add_item(HelpButton())


# =========================================================================
# COG
# =========================================================================
class GeneratorsCog(commands.Cog):
    """Registers generator-related persistent views on bot startup."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(GeneratorsCog(bot))
