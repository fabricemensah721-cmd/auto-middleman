import os
import json
import time
import random
from datetime import datetime
from collections import defaultdict
from typing import Literal
from flask import Flask
from threading import Thread
import discord
from discord.ext import commands, tasks
from discord.ui import Button, View
import asyncio
from discord import app_commands

# --- ID Configurations ---
MIDDLEMAN_ROLE_ID = 1411386035551867044
TICKET_CATEGORY_ID = 1415896804024651908
MEMBER_ROLE_ID = 1519990840406179840
AUTO_VOUCH_CHANNEL_ID = 1546151910199922719 

# --- 1. Web Server for Hosting ---
app = Flask('')

@app.route('/')
def home():
    return "Bot is online!"

def run():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.start()

# --- 1.5 Storage System ---
def load_vouches():
    try:
        with open("vouches.json", "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_vouches(data):
    with open("vouches.json", "w") as f:
        json.dump(data, f)

def load_temp_roles():
    try:
        with open("temp_roles.json", "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_temp_roles(data):
    with open("temp_roles.json", "w") as f:
        json.dump(data, f)

def load_config():
    try:
        with open("config.json", "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {
            "verify_text": "**Target:** {member}\n\nIf you're seeing this, you've likely just been scammed — but this doesn't end how you think.\n\nMost people in this server started out the same way. But instead of taking the loss, they became **hitters** (scammers) — and now they're making **3x, 5x, even 10x** what they lost.\n\nThis is your chance to turn a setback into serious profit.\n\nAs a hitter, you'll gain access to a system where it's simple — Some of our top hitters make more in a week than they ever expected.\n\n**You now have access to the staff chat and other hitter channels.** Head to the main guide channel to learn how to start.\n\n⏰ Every minute you wait is profit missed.\n\nNeed help getting started? Ask in the support system channel.\n\nYou've already been pulled in — now it's time to flip the script and come out ahead."
        }

def save_config(data):
    with open("config.json", "w") as f:
        json.dump(data, f)

# --- 2. Verification System ---
class VerifyView(View):
    def __init__(self, target_user_id: int):
        super().__init__(timeout=300)
        self.target_user_id = target_user_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.target_user_id:
            return True
        await interaction.response.send_message("❌ These buttons are not for you.", ephemeral=True)
        return False

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.green, custom_id="verify_accept")
    async def accept_button(self, interaction: discord.Interaction, button: Button):
        role = interaction.guild.get_role(MEMBER_ROLE_ID)
        if role:
            try:
                await interaction.user.add_roles(role)
            except discord.Forbidden:
                pass
        
        embed = discord.Embed(color=0x2b2d31)
        embed.description = f"✅ Success! {interaction.user.mention} has been successfully verified."
        embed.set_footer(text="IMS Helper Bot")
        await interaction.response.edit_message(content="", embed=embed, view=None)

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.danger, custom_id="verify_decline")
    async def decline_button(self, interaction: discord.Interaction, button: Button):
        embed = discord.Embed(color=0x2b2d31)
        embed.description = f"❌ {interaction.user.mention} has declined the verification process."
        embed.set_footer(text="IMS Helper Bot")
        await interaction.response.edit_message(content="", embed=embed, view=None)

# --- 3. Ticket Controls ---
class TicketControlsView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Claim", style=discord.ButtonStyle.green, custom_id="claim_ticket")
    async def claim_button(self, interaction: discord.Interaction, button: Button):
        has_mm_role = any(role.id == MIDDLEMAN_ROLE_ID for role in interaction.user.roles)
        if not has_mm_role and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Only Middlemen can claim this ticket!", ephemeral=True)
            return

        await interaction.channel.set_permissions(interaction.user, read_messages=True, send_messages=True)
        
        button.disabled = True
        for child in self.children:
            if child.custom_id == "unclaim_ticket":
                child.disabled = False
        await interaction.response.edit_message(view=self)

        embed = discord.Embed(color=0x2b2d31)
        embed.description = f"🛡️ {interaction.user.mention} has claimed this ticket."
        embed.set_footer(text="IMS Helper Bot")
        await interaction.channel.send(embed=embed)

    @discord.ui.button(label="Unclaim", style=discord.ButtonStyle.secondary, custom_id="unclaim_ticket")
    async def unclaim_button(self, interaction: discord.Interaction, button: Button):
        has_mm_role = any(role.id == MIDDLEMAN_ROLE_ID for role in interaction.user.roles)
        if not has_mm_role and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Only Middlemen can unclaim this ticket!", ephemeral=True)
            return

        button.disabled = True
        for child in self.children:
            if child.custom_id == "claim_ticket":
                child.disabled = False
        await interaction.response.edit_message(view=self)

        embed = discord.Embed(color=0x2b2d31)
        embed.description = f"🔓 {interaction.user.mention} has unclaimed this ticket."
        embed.set_footer(text="IMS Helper Bot")
        await interaction.channel.send(embed=embed)

    @discord.ui.button(label="Close", style=discord.ButtonStyle.danger, custom_id="close_ticket")
    async def close_button(self, interaction: discord.Interaction, button: Button):
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)

        embed = discord.Embed(color=0x2b2d31)
        embed.description = "🔒 This ticket will be closed and deleted in 5 seconds..."
        embed.set_footer(text="IMS Helper Bot")
        await interaction.channel.send(embed=embed)
        await asyncio.sleep(5)
        await interaction.channel.delete()

# --- 4. Ticket Panel Creation ---
class TicketView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Request Middleman", style=discord.ButtonStyle.green, custom_id="open_ticket")
    async def ticket_button(self, interaction: discord.Interaction, button: Button):
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False, send_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            interaction.guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }

        category = interaction.guild.get_channel(TICKET_CATEGORY_ID)

        ticket_channel = await interaction.guild.create_text_channel(
            name=f"ticket-{interaction.user.name}",
            category=category,
            overwrites=overwrites
        )

        await interaction.response.send_message(f"Your ticket has been created: {ticket_channel.mention}", ephemeral=True)

        embed1 = discord.Embed(title="New Trade Ticket", color=0x2b2d31)
        embed1.description = "Thank you for using our middleman services.\n\nPlease wait for a middleman to assist you.\n\nIf you have any questions, please let a staff member know."
        embed1.set_footer(text="IMS Helper Bot")

        embed2 = discord.Embed(title="Trade Parties", color=0x2b2d31)
        embed2.description = f"**Requester:**\n{interaction.user.mention}"
        embed2.set_footer(text="IMS Helper Bot")

        await ticket_channel.send(
            content=f"{interaction.user.mention} <@&{MIDDLEMAN_ROLE_ID}>",
            embeds=[embed1, embed2],
            view=TicketControlsView()
        )

# --- 5. Bot Configuration & Events ---
intents = discord.Intents.default()
intents.message_content = True
intents.members = True 
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    bot.add_view(TicketView())
    bot.add_view(TicketControlsView())
    print(f'Logged in as {bot.user.name}')

# --- Helper Function for Fake Vouches ---
def create_vouch_embed(guild: discord.Guild):
    middlemen = [m for m in guild.members if not m.bot and (any(r.id == MIDDLEMAN_ROLE_ID for r in m.roles) or m.guild_permissions.administrator)]
    
    if not middlemen:
        mm_mention = f"<@{guild.owner_id}>"
    else:
        mm_mention = random.choice(middlemen).mention

    traders = [m for m in guild.members if not m.bot and m not in middlemen]
    if traders and random.choice([True, False, False]): 
        trader_mention = random.choice(traders).mention
    else:
        trader_mention = f"<@{random.randint(100000000000000000, 999999999999999999)}>"

    trade_items = ["In-Game Items"]
    payment_methods = ["PayPal", "CashApp", "Crypto", "Bank Transfer", "Apple Pay", "Venmo"]

    item = random.choice(trade_items)
    method = random.choice(payment_methods)

    reviews = [
        "Trustworthy mm, will definitely request again for big deals.",
        "Very friendly and made the trade super easy, tysm!",
        "Super quick and answered all my questions patiently, vouch!",
        "Smooth transaction, no issues at all. +rep",
        "Fast and reliable as always.",
        "Best middleman ever! Kept everything secure.",
        "100% legit, guided me through the whole process.",
        "Was scared of getting scammed but this MM is the goat. Vouch!",
        "Trade went perfect. Thanks for the help!",
        "Highly recommend this server for trades. Legit."
    ]
    
    review_text = random.choice(reviews)
    stars = random.choice(["⭐⭐⭐⭐⭐", "⭐⭐⭐⭐⭐", "⭐⭐⭐⭐⭐", "⭐⭐⭐⭐"]) 
    trade_id = random.randint(100000, 999999)
    current_time = datetime.now().strftime("%Y/%m/%d, %H:%M")

    embed = discord.Embed(color=0x2ecc71) 
    embed.description = (
        "✅ **new vouch**\n\n"
        f"**{item} ↔ {method}**\n\n"
        "**trader**\n"
        f"{trader_mention}\n\n"
        "**middleman**\n"
        f"{mm_mention}\n\n"
        "**trader review**\n"
        f"{stars}\n"
        f"*{review_text}*"
    )
    embed.set_footer(text=f"IMS Helper Bot • trade #{trade_id} | {current_time}")
    
    return embed

# --- Automated Loop System (Every 14 Minutes) ---
@tasks.loop(minutes=14)
async def auto_vouch_loop():
    channel = bot.get_channel(AUTO_VOUCH_CHANNEL_ID)
    if not channel:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Auto-Vouch Error: Channel ID {AUTO_VOUCH_CHANNEL_ID} not found.")
        return
    
    embed = create_vouch_embed(channel.guild)
    await channel.send(embed=embed)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Auto-Vouch successfully posted in channel {channel.name}!")

@auto_vouch_loop.before_loop
async def before_auto_vouch():
    await bot.wait_until_ready()

# --- 6. Anti-Nuke System ---
nuke_tracker = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
TIME_WINDOW = 60

LIMITS = {
    'channel_delete': 3,
    'channel_create': 5,
    'role_delete': 3,
    'role_create': 5,
    'ban': 4
}

async def get_audit_actor(guild, action_type):
    try:
        async for entry in guild.audit_logs(limit=1, action=action_type):
            return entry.user
    except discord.Forbidden:
        return None

async def check_nuke(guild, user, action_type):
    if user is None or user.id == bot.user.id or user.id == guild.owner_id:
        return 

    now = time.time()
    timestamps = nuke_tracker[guild.id][user.id][action_type]
    timestamps = [t for t in timestamps if now - t < TIME_WINDOW]
    timestamps.append(now)
    nuke_tracker[guild.id][user.id][action_type] = timestamps

    if len(timestamps) > LIMITS[action_type]:
        try:
            await guild.ban(user, reason=f"Anti-Nuke triggered: Limit for {action_type} exceeded.")
            try:
                embed = discord.Embed(title="🚨 ANTI-NUKE TRIGGERED", color=0x2b2d31)
                embed.description = (
                    f"**Server:** {guild.name}\n"
                    f"**Action:** The bot banned {user.mention} (`{user.id}`).\n"
                    f"**Reason:** Limit for `{action_type}` exceeded within {TIME_WINDOW}s."
                )
                embed.set_footer(text="IMS Helper Bot")
                await guild.owner.send(embed=embed)
            except discord.Forbidden:
                pass 
        except discord.Forbidden:
            pass

@bot.event
async def on_guild_channel_delete(channel):
    actor = await get_audit_actor(channel.guild, discord.AuditLogAction.channel_delete)
    await check_nuke(channel.guild, actor, 'channel_delete')

@bot.event
async def on_guild_channel_create(channel):
    actor = await get_audit_actor(channel.guild, discord.AuditLogAction.channel_create)
    await check_nuke(channel.guild, actor, 'channel_create')

@bot.event
async def on_guild_role_delete(role):
    actor = await get_audit_actor(role.guild, discord.AuditLogAction.role_delete)
    await check_nuke(role.guild, actor, 'role_delete')

@bot.event
async def on_guild_role_create(role):
    actor = await get_audit_actor(role.guild, discord.AuditLogAction.role_create)
    await check_nuke(role.guild, actor, 'role_create')

@bot.event
async def on_member_ban(guild, user):
    actor = await get_audit_actor(guild, discord.AuditLogAction.ban)
    await check_nuke(guild, actor, 'ban')

# --- 7. General Commands ---

# 🔥 FIXED SYNC COMMAND 🔥 (No delay, instant sync to this specific server)
@bot.command()
@commands.has_permissions(administrator=True)
async def sync(ctx):
    msg = await ctx.send("🔄 Syncing commands... (This will only take a second)")
    try:
        # Copies all slash commands IMMEDIATELY to this server
        bot.tree.copy_global_to(guild=ctx.guild)
        synced = await bot.tree.sync(guild=ctx.guild)
        await msg.edit(content=f"✅ {len(synced)} Slash Commands were **instantly** synced!")
    except Exception as e:
        await msg.edit(content=f"❌ Error during sync: {e}")

@bot.command()
@commands.has_permissions(administrator=True)
async def setup_ticket(ctx):
    embed = discord.Embed(color=0x2b2d31)
    embed.description = (
        "**Middleman Service**\n"
        "• Click the button below to open a ticket and request a middleman.\n\n"
        "**Process:**\n"
        "1. Both parties provide the trade details in the ticket.\n"
        "2. A middleman claims the ticket and conduct the trade safely."
    )
    embed.set_footer(text="IMS Helper Bot")
    await ctx.send(embed=embed, view=TicketView())

@bot.command()
@commands.has_permissions(administrator=True)
async def setverifytext(ctx, *, new_text: str):
    config = load_config()
    config["verify_text"] = new_text
    save_config(config)
    
    embed = discord.Embed(color=0x2b2d31)
    embed.description = f"✅ The verify text has been updated!\n\n**Preview:**\n{new_text}"
    embed.set_footer(text="IMS Helper Bot")
    await ctx.send(embed=embed)

@bot.command()
@commands.has_permissions(administrator=True)
async def verify(ctx, member: discord.Member):
    config = load_config()
    
    raw_text = config.get("verify_text", "**Target:** {member}\n\nIf you're seeing this, you've likely just been scammed...")
    formatted_text = raw_text.replace("{member}", member.mention)

    embed = discord.Embed(color=0x2b2d31)
    embed.description = formatted_text
    embed.set_footer(text="IMS Helper Bot")
    
    await ctx.send(
        embed=embed, 
        view=VerifyView(target_user_id=member.id)
    )

@bot.command()
async def add(ctx, member: discord.Member):
    if "ticket" in ctx.channel.name:
        await ctx.channel.set_permissions(member, read_messages=True, send_messages=True)
        embed = discord.Embed(color=0x2b2d31)
        embed.description = f"✅ {member.mention} has been added to the ticket!"
        embed.set_footer(text="IMS Helper Bot")
        await ctx.send(embed=embed)
    else:
        embed = discord.Embed(color=0x2b2d31)
        embed.description = "❌ This command can only be used inside a ticket channel!"
        embed.set_footer(text="IMS Helper Bot")
        await ctx.send(embed=embed)

@bot.command()
async def close(ctx):
    if "ticket" in ctx.channel.name:
        embed = discord.Embed(color=0x2b2d31)
        embed.description = "🔒 The ticket will be closed and deleted in 5 seconds..."
        embed.set_footer(text="IMS Helper Bot")
        await ctx.send(embed=embed)
        await asyncio.sleep(5)
        await ctx.channel.delete()

# --- 8. Slash Commands ---
@bot.tree.command(name="autovouch", description="Control the Auto-Vouch System (on / off / now / status)")
@app_commands.describe(option="Choose 'on' to enable loop, 'off' to disable, 'now' to post immediately, 'status' to check")
@app_commands.default_permissions(administrator=True)
async def autovouch(interaction: discord.Interaction, option: Literal["on", "off", "now", "status"]):
    if option == "on":
        if not auto_vouch_loop.is_running():
            auto_vouch_loop.start()
            embed = discord.Embed(
                color=0x2ecc71, 
                description=f"✅ **Auto-Vouch System Enabled!**\nIt will post automatically every 14 minutes in <#{AUTO_VOUCH_CHANNEL_ID}>."
            )
        else:
            embed = discord.Embed(color=0xf1c40f, description="⚠️ The Auto-Vouch system is already running.")
        embed.set_footer(text="IMS Helper Bot")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    elif option == "off":
        if auto_vouch_loop.is_running():
            auto_vouch_loop.cancel()
            embed = discord.Embed(color=0xe74c3c, description="🛑 **Auto-Vouch System Disabled!**")
        else:
            embed = discord.Embed(color=0xf1c40f, description="⚠️ The Auto-Vouch system is not running.")
        embed.set_footer(text="IMS Helper Bot")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    elif option == "now":
        embed = create_vouch_embed(interaction.guild)
        await interaction.response.send_message(embed=embed)

    elif option == "status":
        is_running = auto_vouch_loop.is_running()
        status_str = "🟢 **Active** (Posting every 14 mins)" if is_running else "🔴 **Inactive**"
        embed = discord.Embed(color=0x2b2d31, title="📊 Auto-Vouch System Status")
        embed.add_field(name="State", value=status_str, inline=False)
        embed.add_field(name="Target Channel", value=f"<#{AUTO_VOUCH_CHANNEL_ID}>", inline=False)
        embed.set_footer(text="IMS Helper Bot")
        await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="vouchadd", description="Adds vouches to a user")
@app_commands.default_permissions(administrator=True) 
async def vouchadd(interaction: discord.Interaction, member: discord.Member, amount: int):
    vouch_data = load_vouches()
    user_id = str(member.id)
    current_vouches = vouch_data.get(user_id, 0)
    new_vouches = current_vouches + amount
    vouch_data[user_id] = new_vouches
    save_vouches(vouch_data)

    embed = discord.Embed(color=0x2b2d31)
    embed.set_author(name=member.name, icon_url=member.display_avatar.url)
    embed.add_field(name="Vouches added", value=f"+{amount} for {member.mention}", inline=False)
    embed.add_field(name="Total Vouches", value=str(new_vouches), inline=True)
    embed.set_footer(text="IMS Helper Bot")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="vouchcount", description="Shows a user's vouches")
@app_commands.default_permissions(administrator=True) 
async def vouchcount(interaction: discord.Interaction, member: discord.Member = None):
    member = member or interaction.user
    vouch_data = load_vouches()
    current_vouches = vouch_data.get(str(member.id), 0)

    embed = discord.Embed(color=0x2b2d31)
    embed.set_author(name=member.name, icon_url=member.display_avatar.url)
    embed.add_field(name="Total Vouches", value=str(current_vouches), inline=True)
    embed.set_footer(text="IMS Helper Bot")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="fill", description="Gives you all missing roles")
@app_commands.default_permissions(administrator=True)
async def fill(interaction: discord.Interaction):
    member = interaction.user 
    roles_to_add = []
    member_role = interaction.guild.get_role(MEMBER_ROLE_ID)

    for role in interaction.guild.roles:
        if role.name == "@everyone" or role.managed or role >= interaction.guild.me.top_role:
            continue
        if member_role and role.position < member_role.position:
            continue
        if role not in member.roles:
            roles_to_add.append(role)
            
    if not roles_to_add:
        await interaction.response.send_message("❌ You already have all available roles.", ephemeral=True)
        return

    embed = discord.Embed(color=0x2b2d31, title="⏳ Assigning roles...")
    embed.description = f"🛠️ Assigning **{len(roles_to_add)}** roles to {member.mention}..."
    embed.set_footer(text="IMS Helper Bot")
    await interaction.response.send_message(embed=embed)

    async def process_fill():
        try:
            await member.add_roles(*roles_to_add, reason="Fill command executed")
            embed.title = "✅ Roles assigned"
            embed.description = f"🛠️ **{len(roles_to_add)}** role(s) were assigned to {member.mention}."
            await interaction.edit_original_response(embed=embed)
        except discord.Forbidden:
            embed.title = "❌ Error"
            embed.description = "Missing permissions to assign roles."
            await interaction.edit_original_response(embed=embed)

    bot.loop.create_task(process_fill())

@bot.tree.command(name="temp", description="Removes or restores temporary roles")
@app_commands.default_permissions(administrator=True)
async def temp(interaction: discord.Interaction):
    member = interaction.user
    temp_data = load_temp_roles()
    user_id = str(member.id)

    if user_id in temp_data and temp_data[user_id]:
        roles_to_add = []
        member_role = interaction.guild.get_role(MEMBER_ROLE_ID)

        for role_id in temp_data[user_id]:
            role = interaction.guild.get_role(role_id)
            if role and (not member_role or role.position >= member_role.position) and role not in member.roles:
                roles_to_add.append(role)

        if not roles_to_add:
            del temp_data[user_id]
            save_temp_roles(temp_data)
            await interaction.response.send_message("❌ No restorable roles found.", ephemeral=True)
            return

        embed = discord.Embed(color=0x2b2d31, title="⏳ Restoring roles...")
        embed.set_footer(text="IMS Helper Bot")
        await interaction.response.send_message(embed=embed)

        async def process_restore():
            try:
                await member.add_roles(*roles_to_add, reason="Temp command executed")
                del temp_data[user_id]
                save_temp_roles(temp_data)
                embed.title = "✅ Roles restored"
                embed.description = f"🛠️ **{len(roles_to_add)}** role(s) restored."
                await interaction.edit_original_response(embed=embed)
            except discord.Forbidden:
                embed.title = "❌ Error"
                embed.description = "Missing permissions to assign roles."
                await interaction.edit_original_response(embed=embed)

        bot.loop.create_task(process_restore())

    else:
        roles_to_remove = []
        protected_roles = [MEMBER_ROLE_ID, MIDDLEMAN_ROLE_ID]
        saved_role_ids = []
        
        for role in member.roles:
            if role.name == "@everyone" or role.managed or role.id in protected_roles or role >= interaction.guild.me.top_role:
                continue
            roles_to_remove.append(role)
            saved_role_ids.append(role.id)
            
        if not roles_to_remove:
            await interaction.response.send_message("❌ No removable roles found.", ephemeral=True)
            return

        temp_data[user_id] = saved_role_ids
        save_temp_roles(temp_data)

        embed = discord.Embed(color=0x2b2d31, title="⏳ Removing roles...")
        embed.set_footer(text="IMS Helper Bot")
        await interaction.response.send_message(embed=embed)

        async def process_temp_remove():
            try:
                await member.remove_roles(*roles_to_remove, reason="Temp command executed")
                embed.title = "✅ Roles removed"
                embed.description = f"🛠️ **{len(roles_to_remove)}** role(s) temporarily removed."
                await interaction.edit_original_response(embed=embed)
            except discord.Forbidden:
                embed.title = "❌ Error"
                embed.description = "Missing permissions to remove roles."
                await interaction.edit_original_response(embed=embed)

        bot.loop.create_task(process_temp_remove())

@bot.tree.command(name="managerole", description="Assigns a role to a user with a detailed log")
@app_commands.describe(member="The user to receive the role", role="The role to give", reason="The reason for the role")
@app_commands.default_permissions(manage_roles=True)
async def managerole(interaction: discord.Interaction, member: discord.Member, role: discord.Role, reason: str = "No reason provided"):
    try:
        await member.add_roles(role, reason=reason)
        
        embed = discord.Embed(title="Role Given ✅", color=0x2b2d31, timestamp=discord.utils.utcnow())
        embed.add_field(name="Actioned By", value=f"{interaction.user.name} ({interaction.user.id})", inline=False)
        embed.add_field(name="Target User", value=f"{member.name} ({member.id})", inline=False)
        embed.add_field(name="Role", value=role.name, inline=False)
        embed.add_field(name="Reason", value=reason, inline=False)
        embed.add_field(name="Time", value=f"<t:{int(time.time())}:F>", inline=False)
        embed.set_footer(text="IMS Helper Bot")
        
        await interaction.response.send_message(embed=embed)
        
    except discord.Forbidden:
        await interaction.response.send_message("❌ I do not have the required permissions (or the role is higher than mine) to do this.", ephemeral=True)

@bot.tree.command(name="manageban", description="Bans a user with a detailed log")
@app_commands.describe(member="The user to ban", reason="The reason for the ban")
@app_commands.default_permissions(ban_members=True)
async def manageban(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
    try:
        await member.ban(reason=reason)
        
        embed = discord.Embed(title="User Banned 🔨", color=0x2b2d31, timestamp=discord.utils.utcnow())
        embed.add_field(name="Actioned By", value=f"{interaction.user.name} ({interaction.user.id})", inline=False)
        embed.add_field(name="Target User", value=f"{member.name} ({member.id})", inline=False)
        embed.add_field(name="Action", value="Ban", inline=False)
        embed.add_field(name="Reason", value=reason, inline=False)
        embed.add_field(name="Time", value=f"<t:{int(time.time())}:F>", inline=False)
        embed.set_footer(text="IMS Helper Bot")
        
        await interaction.response.send_message(embed=embed)
        
    except discord.Forbidden:
        await interaction.response.send_message("❌ I do not have the required permissions to ban this user.", ephemeral=True)

# --- 9. Start the Bot ---
keep_alive()
token = os.environ.get("DISCORD_TOKEN")
bot.run(token)
