
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

async def api_get(url, params=None):
    params = params or {}
    params["key"] = API_KEY

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as r:
                text = await r.text()

                if not text.strip():
                    return {}

                try:
                    return json.loads(text)
                except:
                    print("⚠️ Non-JSON:", text)
                    return {"raw": text}

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

    data = await api_get(API_GET)

    try:
        await dashboard_message.edit(
            embed=build_embed(data, 0, None),
            view=MainView(data, 0, "dashboard", None)


        )
    except Exception as e:
        print("Dashboard update failed:", e)



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

            if state == "critical":
                msg = await ch.send(f"🚨 <@&{ROLE_ID}> {name} CRITICAL ({format_time(days)})")
                last_alerts[name] = {"state": state, "message": msg}

            elif state == "very_low":
                msg = await ch.send(f"⚠️ {name} VERY LOW ({format_time(days)})")
                last_alerts[name] = {"state": state, "message": msg}

            elif state == "low":
                msg = await ch.send(f"⚠️ {name} LOW ({format_time(days)})")
                last_alerts[name] = {"state": state, "message": msg}

            else:
                if prev:
                    user = last_refuel_user.get(name, "Unknown")

                    try:
                        await prev["message"].edit(
                            content=f"✅ {name} resolved by **{user}** ({format_time(days)})"
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


def build_embed(data, page=0, server_filter=None):
    
    if server_filter:
        data = [g for g in data if g.get("server") == server_filter]

    embed = discord.Embed(title="⚡ Generator Dashboard", color=0x00ff99)

    if not data:
        embed.description = "No generators found"
        return embed

    # ✅ SORT LOWEST FIRST
    data.sort(key=lambda g: float(g["days"]))

    start = page * PER_PAGE
    end = start + PER_PAGE
    slice_data = data[start:end]

    for g in slice_data:
        days = float(g["days"])

        name_text = g["name"]

        if days <= 1:
            name_text = f"🚨 {g['name']} 🚨"
            value = f"**{format_time(days)} CRITICAL 🚨**"
        elif days <= 3:
            name_text = f"⚠️ {g['name']}"
            value = f"**{format_time(days)} LOW ⚠️**"
        else:
            value = f"{format_time(days)} ✅"

        embed.add_field(
            name=name_text,
            value=value,
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
        await interaction.response.defer()

        view = self.view
        new_page = max(view.page - 1, 0)

        await interaction.message.edit(
            embed=build_embed(view.data, new_page, view.server_filter),
            view=MainView(view.data, new_page, view.tab, view.server_filter)
        )



class NextButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="➡️")

    
    async def callback(self, interaction):
        await interaction.response.defer()

        view = self.view
        new_page = max(view.page - 1, 0)

        await interaction.message.edit(
            embed=build_embed(view.data, new_page, view.server_filter),
            view=MainView(view.data, new_page, view.tab, view.server_filter)
        )




# ========================
# MODALS
# ========================

class AddModal(discord.ui.Modal, title="Add Generator"):
    name = discord.ui.TextInput(label="Name")
    days = discord.ui.TextInput(label="Days")
    server = discord.ui.TextInput(label="Server")

    async def on_submit(self, interaction):
        await interaction.response.defer(ephemeral=True)

        try:
            val = float(self.days.value)
        except:
            return await interaction.followup.send("❌ Invalid number", ephemeral=True)

        # ✅ FIXED INDENTATION
        await api_get(API_ADD, {
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

        # ✅ FIXED INDENT
        await api_get(API_UPDATE, {
            "name": self.name,
            "days": val
        })

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

        await api_get(API_DELETE, {"name": self.name})
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


class ServerSelect(discord.ui.Select):
    def __init__(self, data):
        servers = list(set(g.get("server", "Unknown") for g in data))
        servers.sort()

        options = [discord.SelectOption(label="All Servers", value="ALL")]
        options += [discord.SelectOption(label=s, value=s) for s in servers]

        super().__init__(placeholder="Filter by server...", options=options)

    async def callback(self, interaction):
        view = self.view
        selected = self.values[0]

        view.server_filter = selected if selected != "ALL" else None

        
        await interaction.response.edit_message(
            embed=build_embed(view.data, view.page, view.server_filter),
            view=MainView(view.data, view.page, view.tab, view.server_filter)
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
        await interaction.response.defer()  # ✅ ADD THIS LINE

        name = self.values[0]

        await log_action(interaction.user, "select", name)

        await interaction.followup.send(
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

        msg = "\n".join([f"{g['name']} → {format_time(float(g['days']))}" for g in result])

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

        data = await api_get(API_GET)
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

        data = await api_get(API_GET)

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
        await interaction.response.defer()

        data = await api_get(API_GET)

        await interaction.message.edit(
            embed=build_embed(data, 0, None),
            view=MainView(data, 0, self.tab, None)

        )



class MainView(discord.ui.View):
    def __init__(self, data, page=0, tab="dashboard", server_filter=None):
        self.server_filter = server_filter
        super().__init__(timeout=None)

        self.data = data
        self.page = page
        self.tab = tab

        self.add_item(TabButton("⚡ Dashboard", "dashboard"))
        self.add_item(TabButton("🔍 Search", "search"))
        self.add_item(TabButton("📊 Tools", "tools"))

        
        
        if tab == "dashboard":
            self.add_item(ServerSelect(data))

            self.add_item(PrevButton())
            self.add_item(NextButton())

            # ✅ Apply server filter BEFORE giving to dropdown
            filtered = data
            if self.server_filter:
                filtered = [g for g in data if g.get("server") == self.server_filter]

            self.add_item(GeneratorSelect(filtered, self.page))



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
    await interaction.response.defer(ephemeral=True)

    global dashboard_message

    data = await api_get(API_GET)
    ch = bot.get_channel(GEN_CHANNEL_ID)

    dashboard_message = await ch.send(
        embed=build_embed(data, 0, None),
        view=MainView(data, 0)
    )

    await interaction.followup.send("✅ Dashboard ready", ephemeral=True)


# ========================
# READY
# ========================

@bot.event
async def on_ready():
    await bot.tree.sync()
    check_alerts.start()
    auto_refresh.start()
    print(f"✅ Logged in as {bot.user}")


bot.run(TOKEN)
