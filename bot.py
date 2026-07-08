        
import discord
from discord.ext import commands, tasks
import requests
import json
import os
import csv
import datetime
import aiohttp



# =========================
# CONFIG (CHANGE THESE)
# =========================

import os
TOKEN = os.getenv("TOKEN")

API_KEY = "SUPER_SECRET_KEY"  # ✅ MUST MATCH PHP

API_GET = "https://www.t-doc.co.za/discord/generators.php"
API_ADD = "https://www.t-doc.co.za/discord/add.php"
API_UPDATE = "https://www.t-doc.co.za/discord/update.php"
API_DELETE = "https://www.t-doc.co.za/discord/delete.php"
API_RESTORE = "https://www.t-doc.co.za/discord/restore.php"
API_TRASH = "https://www.t-doc.co.za/discord/trash.php"
API_CLEAR_ALL = "https://www.t-doc.co.za/discord/clear_all.php"
API_DINO_FEED = "https://www.t-doc.co.za/discord/dino_feed.php"
API_ADD_DINO_FEED = "https://www.t-doc.co.za/discord/add_dino_feed.php"
API_UPDATE_DINO_FEED = "https://www.t-doc.co.za/discord/update_dino_feed.php"
API_DELETE_DINO_FEED = "https://www.t-doc.co.za/discord/delete_dino_feed.php"
API_SPAM_ZONES = "https://www.t-doc.co.za/discord/spam_zones.php"
API_DELETE_SPAM_ZONE = "https://www.t-doc.co.za/discord/delete_spam_zone.php"
API_ADD_SPAM_ZONE = "https://www.t-doc.co.za/discord/add_spam_zone.php"
API_UPDATE_SPAM_ZONE = "https://www.t-doc.co.za/discord/update_spam_zone.php"
ROLE_ID = 1133565753409425408  # replace with your role ID
GEN_CHANNEL_ID = 1516131475312087160   # ✅ ark-generator channel
LOG_CHANNEL_ID = 1516132183293563010   # ✅ log channel
ALERT_CHANNEL_ID = 1516171257421500537  # ⚠️ your alerts channel


dashboard_message = None
last_deleted = None
last_alerts = {}
last_refuel_user = {}     # ✅ NEW: tracks who refueled



API_KEY = "SUPER_SECRET_KEY"  # ✅ MUST MATCH PHP

PER_PAGE = 15

SERVER_ROLES = {
    "2491": 1516430449520545876, 
}


SERVERS = [
    "2491"
]





# ========================
# BOT
# ========================
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ========================
# SAFE API
# ========================


import aiohttp
import asyncio

async def api_get(url, params=None):
    params = params or {}
    params["key"] = API_KEY

    timeout = aiohttp.ClientTimeout(total=15)  # ✅ 5 second max

    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, params=params) as r:
                text = await r.text()

                if not text.strip():
                    return []

                return json.loads(text)

    except asyncio.TimeoutError:
        print("⚠️ API TIMEOUT")
        return []

    except Exception as e:
        print("❌ API ERROR:", e)
        return []





# ========================
# LOGGING ✅ FINAL VERSION
# ========================
async def log_action(user, action, name, server, value=None):
    ch = bot.get_channel(LOG_CHANNEL_ID)
    if not ch:
        return

    # ✅ Format value (optional)
    value_text = f" → {value}" if value is not None else ""

    await ch.send(
        f"📋 {user} → {action} → {name} [{server}]{value_text}"
    )


# ========================
# REFRESH DASHBOARD
# ========================

async def refresh_dashboard():
    return


# ========================
# Jump SYSTEM ✅ UPDATED
# ========================







class DeleteZoneSelectView(discord.ui.View):
    def __init__(self, data):
        super().__init__(timeout=120)

        self.add_item(
            DeleteZoneSelect(data)
        )


class DeleteZoneSelect(discord.ui.Select):
    def __init__(self, data):

        self.records = data

        options = []

        for row in data[:25]:
            options.append(
                discord.SelectOption(
                    label=row["zone_name"][:100],
                    value=str(row["id"])
                )
            )

        super().__init__(
            placeholder="Select zone to delete...",
            options=options
        )

    async def callback(self, interaction):

        zone_id = int(self.values[0])

        row = next(
            r for r in self.records
            if int(r["id"]) == zone_id
        )

        await api_get(
            API_DELETE_SPAM_ZONE,
            {
                "id": zone_id
            }
        )

        await interaction.response.send_message(
            f"✅ Deleted Zone: {row['zone_name']}",
            ephemeral=True
        )


class DeleteZoneButton(discord.ui.Button):
    def __init__(self, server):
        super().__init__(
            label="🗑 Delete Zone",
            style=discord.ButtonStyle.danger
        )

        self.server = server

    async def callback(self, interaction):

        data = await api_get(
            API_SPAM_ZONES,
            {
                "server": self.server
            }
        )

        if not data:
            return await interaction.response.send_message(
                "❌ No zones found",
                ephemeral=True
            )

        await interaction.response.send_message(
            "Select zone to delete",
            view=DeleteZoneSelectView(data),
            ephemeral=True
        )




class JumpButton(discord.ui.Button):
    def __init__(self, name):
        super().__init__(label=name[:80])
        self.gen_name = name

    async def callback(self, interaction):
        # ✅ Respond immediately (NO waiting)
        await interaction.response.send_message(
            f"⏳ Loading {self.gen_name}...",
            ephemeral=True
        )

        data = await api_get(API_GET)

        if not data:
            return await interaction.followup.send(
                "❌ Failed to load data",
                ephemeral=True
            )

        view = self.view

        # ✅ FIXED server filtering
        if view.server_filter:
            data = [
                g for g in data
                if view.server_filter.lower() in str(g.get("server", "")).lower()
            ]

        # ✅ fallback
        if not data:
            data = await api_get(API_GET)

        data.sort(key=lambda g: float(g["days"]))

        index = next(
            (i for i, g in enumerate(data) if g["name"] == self.gen_name),
            0
        )

        page = index // PER_PAGE

        # ✅ EDIT MAIN DASHBOARD MESSAGE
        await interaction.followup.edit_message(
            interaction.message.id,
            content=f"📍 Jumped to: {self.gen_name}",
            embed=build_embed(
                data,
                page,
                view.server_filter,
                highlight=self.gen_name
            ),
            view=MainView(
                data,
                page,
                "dashboard",
                view.server_filter
            )
        )

        # ✅ ACTION MENU
        await interaction.followup.send(
            f"⚡ {self.gen_name}",
            view=ActionView(self.gen_name),
            ephemeral=True
        )

# NEW CLASSES FOR NEW DASHBOARD FOR GENERATORS / SPAM / DINO FEED 




class DeleteDinoFeedSelectView(discord.ui.View):
    def __init__(self, data):
        super().__init__(timeout=120)

        self.add_item(
            DeleteDinoFeedSelect(data)
        )


class DeleteDinoFeedSelect(discord.ui.Select):
    def __init__(self, data):

        self.records = data

        options = []

        for row in data[:25]:
            options.append(
                discord.SelectOption(
                    label=row["tp_name"][:100],
                    value=str(row["id"])
                )
            )

        super().__init__(
            placeholder="Select TP to delete...",
            options=options
        )

    async def callback(self, interaction):

        tp_id = int(self.values[0])

        row = next(
            r for r in self.records
            if int(r["id"]) == tp_id
        )

        await api_get(
            API_DELETE_DINO_FEED,
            {
                "id": tp_id
            }
        )

        await interaction.response.send_message(
            f"✅ Deleted: {row['tp_name']}",
            ephemeral=True
        )


class DeleteDinoFeedButton(discord.ui.Button):
    def __init__(self, server):
        super().__init__(
            label="🗑 Delete TP",
            style=discord.ButtonStyle.danger
        )

        self.server = server

    async def callback(self, interaction):

        data = await api_get(
            API_DINO_FEED,
            {
                "server": self.server
            }
        )

        if not data:
            return await interaction.response.send_message(
                "❌ No TP records found",
                ephemeral=True
            )

        await interaction.response.send_message(
            "Select TP to delete",
            view=DeleteDinoFeedSelectView(data),
            ephemeral=True
        )


class RefreshDinoFeedButton(discord.ui.Button):
    def __init__(self, server):
        super().__init__(
            label="🔄 Refresh",
            style=discord.ButtonStyle.secondary
        )

        self.server = server

    async def callback(self, interaction):

        await interaction.response.defer()

        data = await api_get(
            API_DINO_FEED,
            {
                "server": self.server
            }
        )

        embed = discord.Embed(
            title=f"🦖 Dino Feed - Server {self.server}",
            color=0x00ff99
        )

        if not data:
            embed.description = "No Dino Feed TPs configured."
        else:
            for row in data[:25]:
                embed.add_field(
                    name=row["tp_name"],
                    value="✅ Active",
                    inline=False
                )

        await interaction.edit_original_response(
            content=None,
            embed=embed,
            view=DinoFeedView(self.server)
        )



class ServerButton(discord.ui.Button):
    def __init__(self, server):
        super().__init__(
            label=server,
            style=discord.ButtonStyle.primary
        )

        self.server = server

    async def callback(self, interaction):

        await interaction.response.edit_message(
            content=f"🌍 Server {self.server}",
            view=ServerMenuView(
                self.server
            ),
            embed=None
        )


class ServerSelectionView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

        for server in SERVERS:
            self.add_item(
                ServerButton(server)
            )



class GeneratorsMenuButton(discord.ui.Button):
    def __init__(self, server):
        super().__init__(
            label="⚡ Generators",
            style=discord.ButtonStyle.success
        )

        self.server = server

    async def callback(self, interaction):

        await interaction.response.defer()

        data = await api_get(API_GET)

        await interaction.edit_original_response(
            content=None,
            embed=build_embed(
                data,
                0,
                self.server
            ),
            view=MainView(
                data,
                0,
                "dashboard",
                self.server
            )
        )





class DinoFeedMenuButton(discord.ui.Button):
    def __init__(self, server):
        super().__init__(
            label="🦖 Dino Feed",
            style=discord.ButtonStyle.primary
        )

        self.server = server

    async def callback(self, interaction):

        await interaction.response.defer()

        data = await api_get(
            API_DINO_FEED,
            {
                "server": self.server
            }
        )

        embed = discord.Embed(
            title=f"🦖 Dino Feed - Server {self.server}",
            color=0x00ff99
        )

        if not data:
            embed.description = "No Dino Feed TPs configured."
        else:
            for row in data[:25]:
                embed.add_field(
                    name=row["tp_name"],
                    value="✅ Active",
                    inline=False
                )

        await interaction.edit_original_response(
            content=None,
            embed=embed,
            view=DinoFeedView(self.server)
        )






class DinoFeedView(discord.ui.View):
    def __init__(self, server):
        super().__init__(timeout=None)

        self.server = server

        self.add_item(
            AddDinoFeedButton(server)
        )

        self.add_item(
            EditDinoFeedButton(server)
        )

        self.add_item(
            DeleteDinoFeedButton(server)
        )

        self.add_item(
            RefreshDinoFeedButton(server)
        )







class AddDinoFeedButton(discord.ui.Button):
    def __init__(self, server):
        super().__init__(
            label="➕ Add TP",
            style=discord.ButtonStyle.success
        )

        self.server = server

    async def callback(self, interaction):

        await interaction.response.send_modal(
            AddDinoFeedModal(
                self.server
            )
        )



class AddZoneButton(discord.ui.Button):
    def __init__(self, server):
        super().__init__(
            label="➕ Add Zone",
            style=discord.ButtonStyle.success
        )

        self.server = server

    async def callback(self, interaction):

        await interaction.response.send_modal(
            AddZoneModal(self.server)
        )



class SpamMenuButton(discord.ui.Button):
    def __init__(self, server):
        super().__init__(
            label="🏗 Spam",
            style=discord.ButtonStyle.secondary
        )

        self.server = server

    async def callback(self, interaction):

        await interaction.response.defer()

        data = await api_get(
            API_SPAM_ZONES,
            {
                "server": self.server
            }
        )

        embed = discord.Embed(
            title=f"🏗 Spam - Server {self.server}",
            color=0xff9900
        )

        if not data:
            embed.description = "No spam zones configured."
        else:
            for row in data[:25]:
                embed.add_field(
                    name=row["zone_name"],
                    value=row["description"] or "No Description",
                    inline=False
                )

        await interaction.edit_original_response(
            content=None,
            embed=embed,
            view=SpamView(self.server)
        )




class SpamView(discord.ui.View):
    def __init__(self, server):
        super().__init__(timeout=None)

        self.server = server

        self.add_item(
            AddZoneButton(server)
        )

        self.add_item(
            EditZoneButton(server)
        )

        self.add_item(
            DeleteZoneButton(server)
        )







class ServerMenuView(discord.ui.View):
    def __init__(self, server):
        super().__init__(timeout=None)

        self.add_item(
            GeneratorsMenuButton(server)
        )

        self.add_item(
            DinoFeedMenuButton(server)
        )

        self.add_item(
            SpamMenuButton(server)
        )



# ========================
# ALERT SYSTEM ✅ UPDATED
# ========================

@tasks.loop(minutes=10)
async def check_alerts():
    data = await api_get(API_GET)
    ch = bot.get_channel(ALERT_CHANNEL_ID)

    if not ch:
        return

    for g in data:
        name = g["name"]
        server = g.get("server", "Unknown")

        days = float(g["days"])
        hours = days * 24

        prev = last_alerts.get(name)

        state = None
        if hours <= 1:
            state = "critical"
        elif hours <= 3:
            state = "very_low"
        elif hours <= 6:
            state = "low"

        prev_state = prev["state"] if prev else None

        if state != prev_state:

            # ========================
            # CRITICAL ALERT ✅
            # ========================
            if state == "critical":
                role_id = SERVER_ROLES.get(server, DEFAULT_ROLE)
                mention = f"<@&{role_id}>" if role_id else ""

                msg = await ch.send(
                    f"🚨 {mention} [{server}] {name} CRITICAL ({format_time(days)})"
                )

                last_alerts[name] = {
                    "state": state,
                    "message": msg
                }

            # ========================
            # VERY LOW
            # ========================
            elif state == "very_low":
                msg = await ch.send(
                    f"⚠️ [{server}] {name} VERY LOW ({format_time(days)})"
                )

                last_alerts[name] = {
                    "state": state,
                    "message": msg
                }

            # ========================
            # LOW
            # ========================
            elif state == "low":
                msg = await ch.send(
                    f"⚠️ [{server}] {name} LOW ({format_time(days)})"
                )

                last_alerts[name] = {
                    "state": state,
                    "message": msg
                }

            # ========================
            # RESOLVED
            # ========================
            else:
                if prev:
                    user = last_refuel_user.get(name, "Unknown")

                    try:
                        await prev["message"].edit(
                            content=f"✅ [{server}] {name} resolved by **{user}** ({format_time(days)})"
                        )
                    except:
                        pass

                    del last_alerts[name]

                    if name in last_refuel_user:
                        del last_refuel_user[name]


@tasks.loop(minutes=5)
async def auto_refresh():
    await refresh_dashboard()


# ========================
# EMBED
# ========================

def format_time(days):
    total_minutes = int(days * 24 * 60)

    d = total_minutes // (24 * 60)
    h = (total_minutes % (24 * 60)) // 60
    m = total_minutes % 60

    if d > 0:
        return f"{d}d {h}h"
    elif h > 0:
        return f"{h}h {m}m"
    else:
        return f"{m}m"






from datetime import datetime


def build_embed(
    data,
    page=0,
    server_filter=None,
    subzone_filter=None,
    highlight=None
):

    if server_filter:
        data = [
            g for g in data
            if g.get("server") == server_filter
        ]

    if subzone_filter:
        data = [
            g for g in data
            if g.get("subzone") == subzone_filter
        ]

    title = "⚡ Generator Dashboard"

    if server_filter:
        title += f" — {server_filter}"

    if subzone_filter:
        title += f" | {subzone_filter}"

    embed = discord.Embed(
        title=title,
        color=0x00ff99
    )

    if not data:
        embed.description = "No generators found"
        return embed

    data.sort(
        key=lambda g: (
            str(g.get("subzone", "")),
            float(g["days"])
        )
    )

    start = page * PER_PAGE
    end = start + PER_PAGE
    slice_data = data[start:end]

    current_subzone = None

    for g in slice_data:

        subzone = g.get(
            "subzone",
            "Unassigned"
        )

        if subzone != current_subzone:
            current_subzone = subzone

            embed.add_field(
                name=f"📍 {subzone}",
                value="────────────────",
                inline=False
            )

        days = float(g["days"])

        if "updated_at" in g and g["updated_at"]:
            try:
                last_update = datetime.fromisoformat(
                    g["updated_at"]
                )

                now = datetime.utcnow()

                elapsed_days = (
                    now - last_update
                ).total_seconds() / 86400

                days -= elapsed_days

            except:
                days = float(g["days"])

        if days < 0:
            days = 0

        name_text = g["name"]

        if highlight and g["name"] == highlight:
            name_text = f"👉 {g['name']}"

        if days <= 5:
            value = (
                f"**{format_time(days)} "
                f"CRITICAL 🚨**"
            )
        elif days <= 10:
            value = (
                f"**{format_time(days)} "
                f"LOW ⚠️**"
            )
        else:
            value = f"{format_time(days)} ✅"

        embed.add_field(
            name=name_text,
            value=value,
            inline=False
        )

    total_pages = max(
        1,
        (len(data) - 1) // PER_PAGE + 1
    )

    embed.set_footer(
        text=f"Page {page+1}/{total_pages}"
    )

    return embed





# ========================
# PAGINATION BUTTONS
# ========================




class PrevButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="⬅️")

    async def callback(self, interaction):
        view = self.view

        new_page = max(view.page - 1, 0)

        await interaction.response.edit_message(
            embed=build_embed(
                view.data,
                new_page,
                view.server_filter,
                view.subzone_filter
            ),
            view=MainView(
                view.data,
                new_page,
                view.tab,
                view.server_filter,
                view.subzone_filter
            )
        )


class NextButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="➡️")

    async def callback(self, interaction):
        view = self.view

        max_page = (len(view.data) - 1) // PER_PAGE
        new_page = min(view.page + 1, max_page)

        await interaction.response.edit_message(
            embed=build_embed(
                view.data,
                new_page,
                view.server_filter,
                view.subzone_filter
            ),
            view=MainView(
                view.data,
                new_page,
                view.tab,
                view.server_filter,
                view.subzone_filter
            )
        )


class EditZoneButton(discord.ui.Button):
    def __init__(self, server):
        super().__init__(
            label="✏️ Edit Zone",
            style=discord.ButtonStyle.primary
        )

        self.server = server

    async def callback(self, interaction):

        data = await api_get(
            API_SPAM_ZONES,
            {
                "server": self.server
            }
        )

        if not data:
            return await interaction.response.send_message(
                "❌ No zones found",
                ephemeral=True
            )

        await interaction.response.send_message(
            "Select zone to edit",
            view=EditZoneSelectView(data),
            ephemeral=True
        )


class EditZoneSelect(discord.ui.Select):
    def __init__(self, data):

        self.records = data

        options = []

        for row in data[:25]:
            options.append(
                discord.SelectOption(
                    label=row["zone_name"][:100],
                    value=str(row["id"])
                )
            )

        super().__init__(
            placeholder="Select zone to edit...",
            options=options
        )

    async def callback(self, interaction):

        zone_id = int(self.values[0])

        row = next(
            r for r in self.records
            if int(r["id"]) == zone_id
        )

        await interaction.response.send_modal(
            EditZoneModal(
                zone_id,
                row["zone_name"],
                row["description"]
            )
        )


class EditZoneSelectView(discord.ui.View):
    def __init__(self, data):
        super().__init__(timeout=120)

        self.add_item(
            EditZoneSelect(data)
        )





# ========================
# MODALS
# ========================


class EditZoneModal(
    discord.ui.Modal,
    title="Edit Spam Zone"
):
    zone_name = discord.ui.TextInput(
        label="Zone Name"
    )

    description = discord.ui.TextInput(
        label="Spam Description",
        style=discord.TextStyle.paragraph,
        required=False
    )

    def __init__(
        self,
        zone_id,
        current_name,
        current_description
    ):
        super().__init__()

        self.zone_id = zone_id

        self.zone_name.default = current_name
        self.description.default = current_description or ""

    async def on_submit(self, interaction):

        await interaction.response.defer(
            ephemeral=True
        )

        await api_get(
            API_UPDATE_SPAM_ZONE,
            {
                "id": self.zone_id,
                "zone_name": self.zone_name.value,
                "description": self.description.value
            }
        )

        await interaction.followup.send(
            "✅ Zone Updated",
            ephemeral=True
        )



class AddZoneModal(
    discord.ui.Modal,
    title="Add Spam Zone"
):
    zone_name = discord.ui.TextInput(
        label="Zone Name"
    )

    description = discord.ui.TextInput(
        label="Spam Description",
        style=discord.TextStyle.paragraph,
        required=False
    )

    def __init__(self, server):
        super().__init__()
        self.server = server

    async def on_submit(self, interaction):

        await interaction.response.defer(
            ephemeral=True
        )

        await api_get(
            API_ADD_SPAM_ZONE,
            {
                "server": self.server,
                "zone_name": self.zone_name.value,
                "description": self.description.value
            }
        )

        await interaction.followup.send(
            "✅ Zone Added",
            ephemeral=True
        )


class EditDinoFeedSelectView(discord.ui.View):
    def __init__(self, data):
        super().__init__(timeout=120)

        self.add_item(
            EditDinoFeedSelect(data)
        )


class EditDinoFeedSelect(discord.ui.Select):
    def __init__(self, data):

        self.records = data

        options = []

        for row in data[:25]:
            options.append(
                discord.SelectOption(
                    label=row["tp_name"][:100],
                    value=str(row["id"])
                )
            )

        super().__init__(
            placeholder="Select TP...",
            options=options
        )

    async def callback(self, interaction):

        tp_id = int(self.values[0])

        row = next(
            r for r in self.records
            if int(r["id"]) == tp_id
        )

        await interaction.response.send_modal(
            EditDinoFeedModal(
                tp_id,
                row["tp_name"]
            )
        )


class EditDinoFeedButton(discord.ui.Button):
    def __init__(self, server):
        super().__init__(
            label="✏️ Edit TP",
            style=discord.ButtonStyle.primary
        )

        self.server = server

    async def callback(self, interaction):

        data = await api_get(
            API_DINO_FEED,
            {
                "server": self.server
            }
        )

        if not data:
            return await interaction.response.send_message(
                "❌ No TP records found",
                ephemeral=True
            )

        await interaction.response.send_message(
            "Select TP to edit",
            view=EditDinoFeedSelectView(data),
            ephemeral=True
        )


class EditDinoFeedModal(
    discord.ui.Modal,
    title="Edit Dino Feed TP"
):
    tp_name = discord.ui.TextInput(
        label="TP Name",
        required=True,
        max_length=255
    )

    def __init__(self, tp_id, current_name):
        super().__init__()

        self.tp_id = tp_id

        self.tp_name.default = current_name

    async def on_submit(self, interaction):

        await interaction.response.defer(
            ephemeral=True
        )

        await api_get(
            API_UPDATE_DINO_FEED,
            {
                "id": self.tp_id,
                "tp_name": self.tp_name.value
            }
        )

        await interaction.followup.send(
            "✅ TP Updated",
            ephemeral=True
        )


class AddDinoFeedModal(
    discord.ui.Modal,
    title="Add Dino Feed TP"
):
    tp_name = discord.ui.TextInput(
        label="TP Name",
        required=True,
        max_length=255
    )

    def __init__(self, server):
        super().__init__()
        self.server = server

    async def on_submit(self, interaction):

        await interaction.response.defer(
            ephemeral=True
        )

        await api_get(
            API_ADD_DINO_FEED,
            {
                "server": self.server,
                "tp_name": self.tp_name.value
            }
        )

        await interaction.followup.send(
            "✅ TP Added",
            ephemeral=True
        )





class SearchResultSelect(discord.ui.Select):
    def __init__(self, results, server_filter, page=0):
        self.results = results
        self.server_filter = server_filter
        self.page = page

        PER_PAGE = 15

        start = page * PER_PAGE
        end = start + PER_PAGE

        page_results = results[start:end]

        options = []

        for g in page_results:
            options.append(
                discord.SelectOption(
                    label=g["name"][:100],
                    value=g["name"]
                )
            )

        super().__init__(
            placeholder=f"Select Generator ({len(results)} found)",
            options=options
        )

    async def callback(self, interaction):
        gen_name = self.values[0]

        data = await api_get(API_GET)

        data.sort(key=lambda g: float(g["days"]))

        index = next(
            (
                i for i, g in enumerate(data)
                if g["name"] == gen_name
            ),
            0
        )

        page = index // PER_PAGE

        await interaction.response.edit_message(
            content=f"📍 Jumped to: {gen_name}",
            embed=build_embed(
                data,
                page,
                self.server_filter,
                highlight=gen_name
            ),
            view=MainView(
                data,
                page,
                "dashboard",
                self.server_filter
            )
        )

        await interaction.followup.send(
            f"⚡ {gen_name}",
            view=ActionView(gen_name),
            ephemeral=True
        )



class SearchResultsView(discord.ui.View):
    def __init__(self, results, server_filter, page=0):
        super().__init__(timeout=120)

        self.results = results
        self.server_filter = server_filter
        self.page = page

        PER_PAGE = 15
        total_pages = max(
            1,
            (len(results) - 1) // PER_PAGE + 1
        )

        self.add_item(
            SearchResultSelect(
                results,
                server_filter,
                page
            )
        )

        if page > 0:
            self.add_item(SearchResultsPrevButton())

        if page < total_pages - 1:
            self.add_item(SearchResultsNextButton())



class SearchResultsPrevButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="⬅ Previous",
            style=discord.ButtonStyle.secondary
        )

    async def callback(self, interaction):
        view = self.view

        await interaction.response.edit_message(
            view=SearchResultsView(
                view.results,
                view.server_filter,
                view.page - 1
            )
        )



class SearchResultsNextButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="Next ➡",
            style=discord.ButtonStyle.secondary
        )

    async def callback(self, interaction):
        view = self.view

        await interaction.response.edit_message(
            view=SearchResultsView(
                view.results,
                view.server_filter,
                view.page + 1
            )
        )





from datetime import datetime


class AddModal(discord.ui.Modal, title="Add Generator"):
    name = discord.ui.TextInput(label="Name")
    days = discord.ui.TextInput(label="Days")
    server = discord.ui.TextInput(label="Server")
    subzone = discord.ui.TextInput(label="Subzone")

    async def on_submit(self, interaction):
        await interaction.response.defer(ephemeral=True)

        try:
            val = float(self.days.value)
        except:
            return await interaction.followup.send(
                "❌ Invalid number",
                ephemeral=True
            )

        await api_get(API_ADD, {
            "name": self.name.value,
            "days": val,
            "server": self.server.value,
            "subzone": self.subzone.value
        })

        await log_action(
            interaction.user,
            "ADD",
            self.name.value,
            self.server.value,
            f"{val:.1f}d"
        )

        await interaction.followup.send(
            "✅ Generator added",
            ephemeral=True
        )

        await refresh_dashboard()









from datetime import datetime

class RefuelModal(discord.ui.Modal, title="Refuel Generator"):
    days = discord.ui.TextInput(label="Set Days")

    def __init__(self, name):
        super().__init__()
        self.name = name

    async def on_submit(self, interaction):
        await interaction.response.defer(ephemeral=True)

        try:
            val = float(self.days.value)
        except:
            return await interaction.followup.send("❌ Invalid number", ephemeral=True)

        await api_get(API_UPDATE, {
            "name": self.name,
            "days": val,
            "updated_at": datetime.utcnow().isoformat()  # ✅ NEW
        })

        last_refuel_user[self.name] = interaction.user.name

        data = await api_get(API_GET)
        server = next(
            (g.get("server") for g in data if g["name"] == self.name),
            "Unknown"
        )

        await log_action(
            interaction.user,
            "UPDATE",
            self.name,
            server,
            f"{val:.1f}d"
        )

        await interaction.followup.send(
            f"✅ {self.name} updated to {val:.1f} days",
            ephemeral=True
        )

        await refresh_dashboard()



class SubzoneModal(discord.ui.Modal, title="Update Subzone"):
    subzone = discord.ui.TextInput(
        label="Subzone",
        required=True,
        max_length=100
    )

    def __init__(self, name):
        super().__init__()
        self.name = name

    async def on_submit(self, interaction):
        await interaction.response.defer(ephemeral=True)

        await api_get(
            API_UPDATE,
            {
                "name": self.name,
                "subzone": self.subzone.value
            }
        )

        await interaction.followup.send(
            f"✅ Subzone updated to: {self.subzone.value}",
            ephemeral=True
        )

        await refresh_dashboard()


class RenameModal(discord.ui.Modal, title="Rename Generator"):
    new_name = discord.ui.TextInput(
        label="New Generator Name",
        required=True,
        max_length=100
    )

    def __init__(self, name):
        super().__init__()
        self.old_name = name

    async def on_submit(self, interaction):
        await interaction.response.defer(ephemeral=True)

        await api_get(
            API_UPDATE,
            {
                "name": self.old_name,
                "new_name": self.new_name.value
            }
        )

        await interaction.followup.send(
            f"✅ Renamed to: {self.new_name.value}",
            ephemeral=True
        )

        await refresh_dashboard()


# ========================
# DELETE
# ========================


class ConfirmDelete(discord.ui.View):
    def __init__(self, name):
        super().__init__()
        self.name = name

    @discord.ui.button(label="✅ Confirm", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction, button):
        global last_deleted

        await interaction.response.defer(ephemeral=True)

        # ✅ Get server BEFORE delete
        data = await api_get(API_GET)
        server = next(
            (g.get("server") for g in data if g["name"] == self.name),
            "Unknown"
        )

        # ✅ Delete generator
        await api_get(API_DELETE, {
            "name": self.name
        })

        last_deleted = self.name

        # ✅ Log DELETE (no value needed)
        await log_action(
            interaction.user,
            "DELETE",
            self.name,
            server
        )

        await interaction.followup.send(
            "✅ Deleted",
            ephemeral=True
        )

        await refresh_dashboard()



# ========================
# ACTION VIEW
# ========================


class ActionView(discord.ui.View):
    def __init__(self, name):
        super().__init__()
        self.name = name

    @discord.ui.button(
        label="⛽ Refuel",
        style=discord.ButtonStyle.success
    )
    async def refuel(self, interaction, button):
        await interaction.response.send_modal(
            RefuelModal(self.name)
        )

    @discord.ui.button(
        label="📝 Subzone",
        style=discord.ButtonStyle.primary
    )
    async def subzone(self, interaction, button):
        await interaction.response.send_modal(
            SubzoneModal(self.name)
        )

    @discord.ui.button(
        label="✏️ Rename",
        style=discord.ButtonStyle.secondary
    )
    async def rename(self, interaction, button):
        await interaction.response.send_modal(
            RenameModal(self.name)
        )

    @discord.ui.button(
        label="🗑 Delete",
        style=discord.ButtonStyle.danger
    )
    async def delete(self, interaction, button):
        await interaction.response.send_message(
            f"Delete {self.name}?",
            view=ConfirmDelete(self.name),
            ephemeral=True
        )



# ========================
# SELECTS
# ========================


class SearchModal(discord.ui.Modal, title="Search Generator"):
    query = discord.ui.TextInput(
        label="Generator Name",
        placeholder="Type part of the generator name...",
        required=True
    )

    def __init__(self, view):
        super().__init__()
        self.view_ref = view

    async def on_submit(self, interaction):
        await interaction.response.defer(ephemeral=True)

        data = await api_get(API_GET)

        # Apply server filter if selected
        if self.view_ref.server_filter:
            data = [
                g for g in data
                if str(g.get("server", "")).strip()
                == str(self.view_ref.server_filter).strip()
            ]

        query = self.query.value.lower().strip()

        results = [
            g for g in data
            if query in g["name"].lower()
        ]

        if not results:
            return await interaction.followup.send(
                "❌ No matching generators found.",
                ephemeral=True
            )

        results.sort(key=lambda g: float(g["days"]))

        total_pages = max(
            1,
            (len(results) - 1) // 15 + 1
        )

        await interaction.followup.send(
            (
                f"✅ Found {len(results)} matching generators.\n"
                f"📄 Page 1/{total_pages}"
            ),
            view=SearchResultsView(
                results,
                self.view_ref.server_filter,
                page=0
            ),
            ephemeral=True
        )



class SearchInputButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="🔎 Search by Name", style=discord.ButtonStyle.primary)

    async def callback(self, interaction):
        await interaction.response.send_modal(SearchModal(self.view))






class ServerSelect(discord.ui.Select):
    def __init__(self, data):
        servers = list({
            str(g.get("server")).strip()
            for g in data
            if g.get("server")
        })

        servers.sort()

        options = [
            discord.SelectOption(
                label="All Servers",
                value="ALL"
            )
        ]

        for s in servers:
            options.append(
                discord.SelectOption(
                    label=s,
                    value=s
                )
            )

        super().__init__(
            placeholder="Filter by server...",
            options=options
        )

    async def callback(self, interaction):
        view = self.view

        selected = self.values[0]

        view.server_filter = (
            None if selected == "ALL"
            else selected
        )

        view.subzone_filter = None

        await interaction.response.edit_message(
            embed=build_embed(
                view.data,
                view.page,
                view.server_filter,
                None
            ),
            view=MainView(
                view.data,
                view.page,
                view.tab,
                view.server_filter,
                None
            )
        )



class SubzoneSelect(discord.ui.Select):
    def __init__(self, data, server_filter=None):
        subzones = sorted({
            str(g.get("subzone")).strip()
            for g in data
            if g.get("subzone")
            and (
                not server_filter
                or str(g.get("server")) == str(server_filter)
            )
        })

        options = [
            discord.SelectOption(
                label="All Subzones",
                value="ALL"
            )
        ]

        for s in subzones:
            options.append(
                discord.SelectOption(
                    label=s,
                    value=s
                )
            )

        super().__init__(
            placeholder="Filter by subzone...",
            options=options
        )

    async def callback(self, interaction):
        view = self.view

        selected = self.values[0]

        view.subzone_filter = (
            None if selected == "ALL"
            else selected
        )

        await interaction.response.edit_message(
            embed=build_embed(
                view.data,
                view.page,
                view.server_filter,
                view.subzone_filter
            ),
            view=MainView(
                view.data,
                view.page,
                view.tab,
                view.server_filter,
                view.subzone_filter
            )
        )






class GeneratorSelect(discord.ui.Select):
    def __init__(self, data, page=0):
        start = page * PER_PAGE
        end = start + PER_PAGE
        page_data = data[start:end]

        options = [discord.SelectOption(label=g["name"]) for g in page_data]

        if not options:
            options = [discord.SelectOption(label="No generators")]

        super().__init__(placeholder="Select generator", options=options)

    async def callback(self, interaction):
        name = self.values[0]

        await interaction.response.send_message(
            f"⚡ {name}",
            view=ActionView(name),
            ephemeral=True
        )







class SearchSelect(discord.ui.Select):
    def __init__(self, data):
        options = [discord.SelectOption(label=g["name"]) for g in data]

        if not options:
            options = [discord.SelectOption(label="No generators")]

        super().__init__(
            placeholder="Search generator...",
            options=options
        )

        self.data = data

    async def callback(self, interaction):
        name = self.values[0]

        result = [g for g in self.data if g["name"] == name]

        if not result:
            return await interaction.response.send_message(
                "❌ Not found",
                ephemeral=True
            )

        msg = "\n".join([
            f"{g['name']} → {format_time(float(g['days']))}"
            for g in result
        ])

        await interaction.response.send_message(msg, ephemeral=True)



# ========================
# SEARCH BUTTONS
# ========================


class CriticalButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="🚨 Critical")

    async def callback(self, interaction):
        await interaction.response.defer(ephemeral=True)

        data = await api_get(API_GET)

        view = self.view

        if view.server_filter:
            data = [
                g for g in data
                if str(g.get("server")).strip() == str(view.server_filter).strip()
            ]

        crit = [g for g in data if float(g["days"]) <= 1]

        if not crit:
            return await interaction.followup.send(
                "✅ No critical generators",
                ephemeral=True
            )

        msg = "\n".join([
            f"{g['name']} → {g['days']}d"
            for g in crit
        ])

        await interaction.followup.send(msg, ephemeral=True)





class ShowAllButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="📋 Show All")

    async def callback(self, interaction):
        await interaction.response.defer(ephemeral=True)

        data = await api_get(API_GET)
        view = self.view

        # ✅ Apply server filter
        if view.server_filter:
            data = [
                g for g in data
                if str(g.get("server")).strip() == str(view.server_filter).strip()
            ]

        if not data:
            return await interaction.followup.send(
                "❌ No generators found",
                ephemeral=True
            )

        data.sort(key=lambda g: float(g["days"]))

        lines = [
            f"{g['name']} → {g['days']}d"
            for g in data
        ]

        # ✅ Split into 2000-char chunks
        chunks = []
        current = ""

        for line in lines:
            if len(current) + len(line) + 1 > 1900:
                chunks.append(current)
                current = line
            else:
                current += ("\n" if current else "") + line

        if current:
            chunks.append(current)

        # ✅ Send first chunk
        await interaction.followup.send(chunks[0], ephemeral=True)

        # ✅ Send remaining chunks if any
        for chunk in chunks[1:]:
            await interaction.followup.send(chunk, ephemeral=True)


# ========================
# TOOLS (UNCHANGED)
# ========================
class AddButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="➕ Add")

    async def callback(self, interaction):
        await interaction.response.send_modal(AddModal())

class UndoButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="♻️ Undo")

    async def callback(self, interaction):
        global last_deleted

        await interaction.response.defer(ephemeral=True)

        if not last_deleted:
            return await interaction.followup.send("Nothing to undo", ephemeral=True)

        await api_get(API_RESTORE, {"name": last_deleted})

        await log_action(interaction.user, "undo", last_deleted)
        await interaction.followup.send("✅ Restored", ephemeral=True)

        await refresh_dashboard()

class BackupButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="💾 Backup")

    async def callback(self, interaction):
        await interaction.response.defer(ephemeral=True)

        data = await api_get(API_GET)

        with open("backup.json", "w") as f:
            json.dump(data, f)

        await interaction.followup.send(file=discord.File("backup.json"), ephemeral=True)
        os.remove("backup.json")

class CSVButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="📊 CSV")

    async def callback(self, interaction):
        await interaction.response.defer(ephemeral=True)

        data = await api_get(API_GET)

        with open("gens.csv", "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["Name", "Days"])

            for g in data:
                writer.writerow([g["name"], g["days"]])

        await interaction.followup.send(file=discord.File("gens.csv"), ephemeral=True)
        os.remove("gens.csv")

class ResetAlertsButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="🔔 Alert Reset")

    async def callback(self, interaction):
        await interaction.response.defer(ephemeral=True)

        last_alerts.clear()
        await interaction.followup.send("✅ Alerts reset", ephemeral=True)

class HelpButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="❓ Help")

    async def callback(self, interaction):
        await interaction.response.defer(ephemeral=True)

        msg = """
📘 Generator Bot Help

Dashboard → Select → Refuel/Delete  
Search → Find / Critical / Show All  
Tools → Add / Undo / Backup / CSV / Reset  

Alerts auto-track + resolve with user info ✅
"""
        await interaction.followup.send(msg, ephemeral=True)

# ========================
# TABS (SAFE FIX)
# ========================


class TabButton(discord.ui.Button):
    def __init__(self, label, tab):
        super().__init__(label=label)
        self.tab = tab

    async def callback(self, interaction):
        data = await api_get(API_GET)

        await interaction.response.edit_message(
            embed=build_embed(
                data,
                0,
                None,
                None
            ),
            view=MainView(
                data,
                0,
                self.tab,
                None,
                None
            )
        )






class MainView(discord.ui.View):
    def __init__(
        self,
        data,
        page=0,
        tab="dashboard",
        server_filter=None,
        subzone_filter=None
    ):
        super().__init__(timeout=None)

        self.data = data
        self.page = page
        self.tab = tab
        self.server_filter = server_filter
        self.subzone_filter = subzone_filter

        # =========================
        # TABS
        # =========================
        self.add_item(TabButton("⚡ Dashboard", "dashboard"))
        self.add_item(TabButton("🔍 Search", "search"))
        self.add_item(TabButton("📊 Tools", "tools"))

        # =========================
        # DASHBOARD TAB
        # =========================
        if tab == "dashboard":

            self.add_item(ServerSelect(data))

            self.add_item(
                SubzoneSelect(
                    data,
                    self.server_filter
                )
            )

            self.add_item(PrevButton())
            self.add_item(NextButton())

            filtered = data

            if self.server_filter:
                filtered = [
                    g for g in filtered
                    if g.get("server") == self.server_filter
                ]

            if self.subzone_filter:
                filtered = [
                    g for g in filtered
                    if g.get("subzone") == self.subzone_filter
                ]

            self.add_item(
                GeneratorSelect(
                    filtered,
                    self.page
                )
            )

        # =========================
        # SEARCH TAB
        # =========================
        elif tab == "search":

            self.add_item(ServerSelect(data))

            self.add_item(
                SubzoneSelect(
                    data,
                    self.server_filter
                )
            )

            filtered = data

            if self.server_filter:
                filtered = [
                    g for g in filtered
                    if g.get("server") == self.server_filter
                ]

            if self.subzone_filter:
                filtered = [
                    g for g in filtered
                    if g.get("subzone") == self.subzone_filter
                ]

            start = self.page * PER_PAGE
            end = start + PER_PAGE
            page_data = filtered[start:end]

            self.add_item(PrevButton())
            self.add_item(NextButton())

            self.add_item(SearchSelect(page_data))
            self.add_item(SearchInputButton())
            self.add_item(CriticalButton())
            self.add_item(ShowAllButton())

        # =========================
        # TOOLS TAB
        # =========================
        elif tab == "tools":

            self.add_item(AddButton())
            self.add_item(UndoButton())
            self.add_item(BackupButton())
            self.add_item(CSVButton())
            self.add_item(ResetAlertsButton())
            self.add_item(HelpButton())



# ========================
# COMMAND
# ========================





@bot.tree.command(name="gen_dashboard")
async def gen_dashboard(interaction):

    await interaction.response.defer()

    global dashboard_message
    dashboard_message = None

    await interaction.followup.send(
        "🌍 Select Server",
        view=ServerSelectionView()
    )




# ========================
# READY
# ========================

@bot.event
async def on_ready():
    await bot.tree.sync()
    check_alerts.start()
    auto_refresh.start()
    print(f"✅ Logged in as {bot.user}")

import time

if __name__ == "__main__":
    while True:
        try:
            bot.run(TOKEN)
        except Exception as e:
            print(f"⚠️ Bot crashed: {e}")
            print("🔁 Restarting in 10 seconds...")
            time.sleep(10)



