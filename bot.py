
import discord
from discord.ext import commands, tasks
import requests
import json
import os
import csv
import datetime

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
DAILY_API = "https://www.t-doc.co.za/discord/decrease.php"
ROLE_ID = 1133565753409425408  # replace with your role ID
GEN_CHANNEL_ID = 1516131475312087160   # ✅ ark-generator channel
LOG_CHANNEL_ID = 1516132183293563010   # ✅ log channel
ALERT_CHANNEL_ID = 1516171257421500537  # ⚠️ your alerts channel


dashboard_message = None
last_deleted = None
last_alerts = {}
last_refuel_user = {}     # ✅ NEW: tracks who refueled



API_KEY = "SUPER_SECRET_KEY"  # ✅ MUST MATCH PHP

PER_PAGE = 25





# ========================
# BOT
# ========================
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ========================
# SAFE API
# ========================
def api_get(url, params=None):
    params = params or {}
    params["key"] = API_KEY

    try:
        r = requests.get(url, params=params)

        if not r.text.strip():
            return {}

        try:
            return r.json()
        except:
            print("⚠️ Non-JSON:", r.text)
            return {"raw": r.text}

    except Exception as e:
        print("❌ API ERROR:", e)
        return {}

# ========================
# LOGGING
# ========================
async def log_action(user, action, target=""):
    ch = bot.get_channel(LOG_CHANNEL_ID)
    if ch:
        await ch.send(f"📋 {user} → {action} → {target}")

# ========================
# REFRESH DASHBOARD
# ========================
async def refresh_dashboard():
    global dashboard_message

    if not dashboard_message:
        return

    data = api_get(API_GET)

    try:
        await dashboard_message.edit(
            embed=build_embed(data, 0),
            view=MainView(data, 0)

        )
    except Exception as e:
        print("Dashboard update failed:", e)

# ========================
# ALERT SYSTEM ✅ UPDATED
# ========================
@tasks.loop(minutes=10)
async def check_alerts():
    data = api_get(API_GET)
    ch = bot.get_channel(ALERT_CHANNEL_ID)

    if not ch:
        return

    for g in data:
        name = g["name"]
        days = float(g["days"])

        prev = last_alerts.get(name)

        # 🚨 CRITICAL
        if days <= 1:
            if not prev or prev["state"] != "critical":
                msg = await ch.send(f"🚨 <@&{ROLE_ID}> {name} CRITICAL ({days:.1f}d)")
                last_alerts[name] = {"state": "critical", "message": msg}

        # ⚠️ LOW
        elif days <= 3:
            if not prev or prev["state"] != "low":
                msg = await ch.send(f"⚠️ {name} LOW ({days:.1f}d)")
                last_alerts[name] = {"state": "low", "message": msg}

        # ✅ RESOLVED
        else:
            if prev:
                user = last_refuel_user.get(name, "Unknown")

                try:
                    await prev["message"].edit(
                        content=f"✅ {name} resolved by **{user}** ({days:.1f}d)"
                    )
                except:
                    pass

                del last_alerts[name]

                if name in last_refuel_user:
                    del last_refuel_user[name]

# ========================
# EMBED
# ========================

def build_embed(data, page=0):
    embed = discord.Embed(title="⚡ Generator Dashboard", color=0x00ff99)

    if not data:
        embed.description = "No generators found"
        return embed

    start = page * PER_PAGE
    end = start + PER_PAGE
    slice_data = data[start:end]

    for g in slice_data:
        days = float(g["days"])
        status = "✅"

        if days <= 1:
            status = "🚨"
        elif days <= 3:
            status = "⚠️"

        embed.add_field(
            name=g["name"],
            value=f"{days:.1f} days {status}",
            inline=False
        )

    total_pages = max(1, (len(data) - 1) // PER_PAGE + 1)
    embed.set_footer(text=f"Page {page+1}/{total_pages}")

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
            embed=build_embed(view.data, new_page),
            view=MainView(view.data, new_page, view.tab)
        )



class NextButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="➡️")

   (view.data) - 1) // PER_PAGE    async def callback(self, interaction):
        new_page = min(view.page + 1, max_page)

        await interaction.response.edit_message(
            embed=build_embed(view.data, new_page),
            view=MainView(view.data, new_page, view.tab)
        )
        view = self.view






# ========================
# MODALS
# ========================
class AddModal(discord.ui.Modal, title="Add Generator"):
    name = discord.ui.TextInput(label="Name")
    days = discord.ui.TextInput(label="Days")
    server = discord.ui.TextInput(label="Server")

    async def on_submit(self, interaction):
        await interaction.response.defer(ephemeral=True)

        val = float(self.days.value)

        api_get(API_ADD, {
            "name": self.name.value,
            "days": val,
            "server": self.server.value
        })

        await log_action(interaction.user, "add", f"{self.name.value} → {val}d")
        await interaction.followup.send("✅ Generator added", ephemeral=True)
        await refresh_dashboard()

class RefuelModal(discord.ui.Modal, title="Refuel Generator"):
    days = discord.ui.TextInput(label="Set Days")

    def __init__(self, name):
        self.name = name
        super().__init__()

    async def on_submit(self, interaction):
        await interaction.response.defer(ephemeral=True)

        try:
            val = float(self.days.value)
        except:
            return await interaction.followup.send("❌ Invalid number", ephemeral=True)

        api_get(API_UPDATE, {"name": self.name, "days": val})

        # ✅ STORE USER FOR ALERT SYSTEM
        last_refuel_user[self.name] = interaction.user.name

        await log_action(interaction.user, "refuel", f"{self.name} → {val}d")

        await interaction.followup.send(
            f"✅ {self.name} updated to {val:.1f} days",
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

        api_get(API_DELETE, {"name": self.name})
        last_deleted = self.name

        await log_action(interaction.user, "delete", self.name)
        await interaction.followup.send("✅ Deleted", ephemeral=True)

        await refresh_dashboard()

# ========================
# ACTION VIEW
# ========================
class ActionView(discord.ui.View):
    def __init__(self, name):
        super().__init__()
        self.name = name

    @discord.ui.button(label="⛽ Refuel", style=discord.ButtonStyle.success)
    async def refuel(self, interaction, button):
        await interaction.response.send_modal(RefuelModal(self.name))

    @discord.ui.button(label="🗑 Delete", style=discord.ButtonStyle.danger)
    async def delete(self, interaction, button):
        await interaction.response.send_message(
            f"Delete {self.name}?",
            view=ConfirmDelete(self.name),
            ephemeral=True
        )

# ========================
# SELECTS
# ========================



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

        await log_action(interaction.user, "select", name)

        await interaction.response.send_message(
            f"⚡ {name}",
            view=ActionView(name),
            ephemeral=True
        )


class SearchSelect(discord.ui.Select):
    def __init__(self, data):
        options = [discord.SelectOption(label=g["name"]) for g in data[:25]]

        if not options:
            options = [discord.SelectOption(label="No generators")]

        super().__init__(placeholder="Search generator...", options=options)
        self.data = data

    async def callback(self, interaction):
        name = self.values[0]

        result = [g for g in self.data if g["name"] == name]

        if not result:
            return await interaction.response.send_message("❌ Not found", ephemeral=True)

        msg = "\n".join([f"{g['name']} → {g['days']}d" for g in result])

        await log_action(interaction.user, "search", name)
        await interaction.response.send_message(msg, ephemeral=True)

# ========================
# SEARCH BUTTONS
# ========================
class CriticalButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="🚨 Critical")

    async def callback(self, interaction):
        await interaction.response.defer(ephemeral=True)

        data = api_get(API_GET)
        crit = [g for g in data if float(g["days"]) <= 1]

        if not crit:
            return await interaction.followup.send("✅ No critical generators", ephemeral=True)

        msg = "\n".join([f"{g['name']} → {g['days']}d" for g in crit])
        await interaction.followup.send(msg, ephemeral=True)

class ShowAllButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="📋 Show All")

    async def callback(self, interaction):
        await interaction.response.defer(ephemeral=True)

        data = api_get(API_GET)

        if not data:
            return await interaction.followup.send("❌ No generators", ephemeral=True)

        data.sort(key=lambda g: float(g["days"]))
        msg = "\n".join([f"{g['name']} → {g['days']}d" for g in data])

        await interaction.followup.send(msg, ephemeral=True)

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

        api_get(API_RESTORE, {"name": last_deleted})

        await log_action(interaction.user, "undo", last_deleted)
        await interaction.followup.send("✅ Restored", ephemeral=True)

        await refresh_dashboard()

class BackupButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="💾 Backup")

    async def callback(self, interaction):
        await interaction.response.defer(ephemeral=True)

        data = api_get(API_GET)

        with open("backup.json", "w") as f:
            json.dump(data, f)

        await interaction.followup.send(file=discord.File("backup.json"), ephemeral=True)
        os.remove("backup.json")

class CSVButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="📊 CSV")

    async def callback(self, interaction):
        await interaction.response.defer(ephemeral=True)

        data = api_get(API_GET)

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
        await interaction.response.defer()

        data = api_get(API_GET)

        await interaction.message.edit(
            embed=build_embed(data, 0),
            view=MainView(data, 0, self.tab)

        )


class MainView(discord.ui.View):
    def __init__(self, data, page=0, tab="dashboard"):
        super().__init__(timeout=None)

        self.data = data
        self.page = page
        self.tab = tab

        self.add_item(TabButton("⚡ Dashboard", "dashboard"))
        self.add_item(TabButton("🔍 Search", "search"))
        self.add_item(TabButton("📊 Tools", "tools"))

        if tab == "dashboard":
            self.add_item(PrevButton())
            self.add_item(NextButton())
            self.add_item(GeneratorSelect(data, self.page))

        elif tab == "search":
            self.add_item(SearchSelect(data))
            self.add_item(CriticalButton())
            self.add_item(ShowAllButton())

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
    global dashboard_message

    data = api_get(API_GET)
    ch = bot.get_channel(GEN_CHANNEL_ID)

    dashboard_message = await ch.send(
        embed=build_embed(data, 0),
        view=MainView(data, 0)

    )

    await interaction.response.send_message("✅ Dashboard ready", ephemeral=True)

# ========================
# READY
# ========================
@bot.event
async def on_ready():
    await bot.tree.sync()
    check_alerts.start()
    print(f"✅ Logged in as {bot.user}")

bot.run(TOKEN)
