import os
import json
import time
import random
from datetime import datetime
from collections import defaultdict
from flask import Flask
from threading import Thread
import discord
from discord.ext import commands
from discord.ui import Button, View
import asyncio
from discord import app_commands

# --- ID Configurations ---
MIDDLEMAN_ROLE_ID = 1411386035551867044
TICKET_CATEGORY_ID = 1415896804024651908
MEMBER_ROLE_ID = 1519990840406179840

# --- 1. Web Server for Hosting (e.g., Render / Replit) ---
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

# --- 1.5 Storage System (Vouches, Temp Roles & Config) ---
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

# --- 2. Verification System (Clickable only by the target user) ---
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

# --- 3. Ticket Controls (Claim, Unclaim, Close) ---
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
        
        # Disable Claim, Enable Unclaim
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

        # Disable Unclaim, Enable Claim
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
        # Disable all buttons so no one can click them anymore
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

# --- 5. Bot Configuration ---
intents = discord.Intents.default()
intents.message_content = True
intents.members = True 
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    bot.add_view(TicketView())
    bot.add_view(TicketControlsView())
    print(f'Logged in as {bot.user.name}')

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

@bot.command()
@commands.has_permissions(administrator=True)
async def sync(ctx):
    try:
        bot.tree.copy_global_to(guild=ctx.guild)
        synced = await bot.tree.sync(guild=ctx.guild)
        await ctx.send(f"✅ {len(synced)} slash commands have been successfully synced!")
    except Exception as e:
        await ctx.send(f"❌ Error while syncing: {e}")

@bot.command()
@commands.has_permissions(administrator=True)
async def setup_ticket(ctx):
    embed = discord.Embed(color=0x2b2d31)
    embed.description = (
        "**Middleman Service**\n"
        "• Click the button below to open a ticket and request a middleman.\n\n"
        "**Process:**\n"
        "1. Both parties provide the trade details in the ticket.\n"
        "2. A middleman claims the ticket and conducts the trade safely."
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
    
    raw_text = config.get("verify_text", "**Target:** {member}\n\nIf you're seeing this, you've likely just been scammed — but this doesn't end how you think.\n\nMost people in this server started out the same way. But instead of taking the loss, they became **hitters** (scammers) — and now they're making **3x, 5x, even 10x** what they lost.\n\nThis is your chance to turn a setback into serious profit.\n\nAs a hitter, you'll gain access to a system where it's simple — Some of our top hitters make more in a week than they ever expected.\n\n**You now have access to the staff chat and other hitter channels.** Head to the main guide channel to learn how to start.\n\n⏰ Every minute you wait is profit missed.\n\nNeed help getting started? Ask in the support system channel.\n\nYou've already been pulled in — now it's time to flip the script and come out ahead.")
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

# --- 8. Slash Commands (Vouches, Fill, Temp, AutoVouch) ---

@bot.tree.command(name="autovouch", description="Generates a fake automatic vouch (Admin only)")
@app_commands.default_permissions(administrator=True)
async def autovouch(interaction: discord.Interaction):
    # Finde einen zufälligen Middleman aus dem Server
    middlemen = [m for m in interaction.guild.members if not m.bot and (any(r.id == MIDDLEMAN_ROLE_ID for r in m.roles) or m.guild_permissions.administrator)]
    
    if not middlemen:
        mm_mention = interaction.user.mention # Fallback, wenn es keinen MM gibt
    else:
        mm_mention = random.choice(middlemen).mention

    # Finde einen "Trader" (entweder random User oder erstelle eine echt aussehende Fake-ID wie im Screenshot)
    traders = [m for m in interaction.guild.members if not m.bot and m not in middlemen]
    if traders and random.choice([True, False]): # 50% chance auf echten User
        trader_mention = random.choice(traders).mention
    else:
        # Generiert eine zufällige ID, die im Discord wie "<@1489913447859884083>" aussieht (genau wie im Screenshot)
        trader_mention = f"<@{random.randint(100000000000000000, 999999999999999999)}>"

    # Zufällige Daten generieren
    payment_methods = ["CashApp", "Crypto", "Bank Transfer", "PayPal", "Apple Pay"]
    reviews = [
        "Trustworthy mm, will definitely request again for big deals.",
        "Very friendly and made the trade super easy, tysm!",
        "Super quick and answered all my questions patiently, vouch!",
        "Smooth transaction, no issues at all. +rep",
        "Fast and reliable as always.",
        "Best middleman ever! Kept everything secure."
    ]
    
    method = random.choice(payment_methods)
    review_text = random.choice(reviews)
    stars = random.choice(["⭐⭐⭐⭐⭐", "⭐⭐⭐⭐⭐", "⭐⭐⭐⭐⭐", "⭐⭐⭐⭐"]) # Höhere Chance auf 5 Sterne
    trade_id = random.randint(100000, 999999)
    current_time = datetime.now().strftime("%Y/%m/%d, %H:%M")

    # Erstelle den realistischen Vouch Embed
    embed = discord.Embed(color=0x2ecc71) # Grünes Embed wie im Screenshot
    embed.description = (
        "✅ **new vouch**\n\n"
        f"**In-Game Items ↔ {method}**\n\n"
        "**trader**\n"
        f"{trader_mention}\n\n"
        "**middleman**\n"
        f"{mm_mention}\n\n"
        "**trader review**\n"
        f"{stars}\n"
        f"*{review_text}*"
    )
    embed.set_footer(text=f"IMS Helper Bot • trade #{trade_id} | {current_time}")

    await interaction.response.send_message(embed=embed)

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

# --- 9. Start the Bot ---
keep_alive()
token = os.environ.get("DISCORD_TOKEN")
bot.run(token)
