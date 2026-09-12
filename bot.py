import os
import json
import time
import random
from datetime import datetime
from collections import defaultdict
from typing import Literal, Optional
from flask import Flask
from threading import Thread
import discord
from discord.ext import commands, tasks
from discord.ui import Button, View
import asyncio
from discord import app_commands

# --- ID & Asset Configurations ---
MIDDLEMAN_ROLE_ID = 1411386035551867044
TICKET_CATEGORY_ID = 1415896804024651908
MEMBER_ROLE_ID = 1411088611926868168
AUTO_VOUCH_CHANNEL_ID = 1546151910199922719

BRAND_NAME = "IMS Helper Bot"
GIF_FILE_PATH = "IMG_1153_2.gif"
GIF_URL = None

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

def apply_gif_to_embed(embed: discord.Embed, as_thumbnail: bool = True):
    if GIF_URL:
        if as_thumbnail:
            embed.set_thumbnail(url=GIF_URL)
        else:
            embed.set_image(url=GIF_URL)
    elif os.path.exists(GIF_FILE_PATH):
        if as_thumbnail:
            embed.set_thumbnail(url=f"attachment://{GIF_FILE_PATH}")
        else:
            embed.set_image(url=f"attachment://{GIF_FILE_PATH}")

def create_gif_file():
    if not GIF_URL and os.path.exists(GIF_FILE_PATH):
        return discord.File(GIF_FILE_PATH, filename=GIF_FILE_PATH)
    return None

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
        embed.set_footer(text=BRAND_NAME)
        apply_gif_to_embed(embed, as_thumbnail=True)
        
        gif_file = create_gif_file()
        if gif_file:
            await interaction.response.edit_message(content="", embed=embed, view=None, attachments=[gif_file])
        else:
            await interaction.response.edit_message(content="", embed=embed, view=None)

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.danger, custom_id="verify_decline")
    async def decline_button(self, interaction: discord.Interaction, button: Button):
        embed = discord.Embed(color=0x2b2d31)
        embed.description = f"❌ {interaction.user.mention} has declined the verification process."
        embed.set_footer(text=BRAND_NAME)
        apply_gif_to_embed(embed, as_thumbnail=True)
        
        gif_file = create_gif_file()
        if gif_file:
            await interaction.response.edit_message(content="", embed=embed, view=None, attachments=[gif_file])
        else:
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
        embed.set_footer(text=BRAND_NAME)
        apply_gif_to_embed(embed, as_thumbnail=True)
        
        gif_file = create_gif_file()
        if gif_file:
            await interaction.channel.send(embed=embed, file=gif_file)
        else:
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
        embed.set_footer(text=BRAND_NAME)
        apply_gif_to_embed(embed, as_thumbnail=True)

        gif_file = create_gif_file()
        if gif_file:
            await interaction.channel.send(embed=embed, file=gif_file)
        else:
            await interaction.channel.send(embed=embed)

    @discord.ui.button(label="Close", style=discord.ButtonStyle.danger, custom_id="close_ticket")
    async def close_button(self, interaction: discord.Interaction, button: Button):
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)

        embed = discord.Embed(color=0x2b2d31)
        embed.description = "🔒 This ticket will be closed and deleted in 5 seconds..."
        embed.set_footer(text=BRAND_NAME)
        await interaction.channel.send(embed=embed)
        await asyncio.sleep(5)
        await interaction.channel.delete()

# --- 4. Ticket Panel System (Dropdown Removed) ---
class TicketMainView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Request Middleman", style=discord.ButtonStyle.green, custom_id="request_middleman_main")
    async def request_middleman_button(self, interaction: discord.Interaction, button: Button):
        middleman_role = interaction.guild.get_role(MIDDLEMAN_ROLE_ID)

        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False, send_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            interaction.guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }

        if middleman_role:
            overwrites[middleman_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

        category = interaction.guild.get_channel(TICKET_CATEGORY_ID)

        ticket_channel = await interaction.guild.create_text_channel(
            name=f"ticket-{interaction.user.name}",
            category=category,
            overwrites=overwrites
        )

        await interaction.response.send_message(f"Your ticket has been created: {ticket_channel.mention}", ephemeral=True)

        embed1 = discord.Embed(title=f"💠 {BRAND_NAME} — Trade Ticket", color=0x3498db)
        embed1.description = (
            f"Thank you for using our middleman services.\n\n"
            "Please wait for a middleman to assist you.\n"
            "If you have any questions, please let a staff member know."
        )
        embed1.set_footer(text=BRAND_NAME)
        apply_gif_to_embed(embed1, as_thumbnail=True)

        embed2 = discord.Embed(title="Trade Parties", color=0x2b2d31)
        embed2.description = f"**Requester:**\n{interaction.user.mention}"
        embed2.set_footer(text=BRAND_NAME)

        gif_file = create_gif_file()
        if gif_file:
            await ticket_channel.send(
                content=f"{interaction.user.mention} <@&{MIDDLEMAN_ROLE_ID}>",
                embeds=[embed1, embed2],
                view=TicketControlsView(),
                file=gif_file
            )
        else:
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
    bot.add_view(TicketMainView())
    bot.add_view(TicketControlsView())
    print(f'Logged in as {bot.user.name}')

def create_vouch_embed(guild: discord.Guild):
    middlemen = [m for m in guild.members if not m.bot and (any(r.id == MIDDLEMAN_ROLE_ID for r in m.roles) or m.guild_permissions.administrator)]
    
    if not middlemen:
        mm_user = guild.owner
    else:
        mm_user = random.choice(middlemen)

    if mm_user:
        mm_mention = mm_user.mention
        vouch_data = load_vouches()
        uid = str(mm_user.id)
        vouch_data[uid] = vouch_data.get(uid, 0) + 1
        save_vouches(vouch_data)
    else:
        mm_mention = f"<@{guild.owner_id}>"

    traders = [m for m in guild.members if not m.bot and m.id != getattr(mm_user, 'id', None)]
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
    embed.set_footer(text=f"{BRAND_NAME} • trade #{trade_id} | {current_time}")
    apply_gif_to_embed(embed, as_thumbnail=True)
    
    return embed

@tasks.loop(minutes=14)
async def auto_vouch_loop():
    channel = bot.get_channel(AUTO_VOUCH_CHANNEL_ID)
    if not channel:
        return
    
    embed = create_vouch_embed(channel.guild)
    gif_file = create_gif_file()
    if gif_file:
        await channel.send(embed=embed, file=gif_file)
    else:
        await channel.send(embed=embed)

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
                embed.set_footer(text=BRAND_NAME)
                apply_gif_to_embed(embed, as_thumbnail=True)
                
                gif_file = create_gif_file()
                if gif_file:
                    await guild.owner.send(embed=embed, file=gif_file)
                else:
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
    msg = await ctx.send("🔄 Syncing commands...")
    try:
        bot.tree.copy_global_to(guild=ctx.guild)
        synced = await bot.tree.sync(guild=ctx.guild)
        await msg.edit(content=f"✅ {len(synced)} Slash Commands were **instantly** synced!")
    except Exception as e:
        await msg.edit(content=f"❌ Error during sync: {e}")

@bot.command()
@commands.has_permissions(administrator=True)
async def setup_ticket(ctx):
    embed = discord.Embed(color=0x2b2d31)
    embed.title = "Middleman Service"
    embed.description = (
        "• To request a middleman from this server, click the blue \"Request Middleman\"\n"
        "button on this message.\n\n"
        "**How does middleman work?**\n"
        "• Example: Trade is Frost Dragon for Corrupt.\n"
        "• Trader #1 gives Frost Dragon to middleman.\n"
        "• Trader #2 gives Corrupt to middleman.\n"
        "• Middleman gives the respective pets to each trader.\n\n"
        "⚠️ **DISCLAIMER!**\n"
        "You must both agree on the deal before using a middleman. Troll tickets will have\n"
        "consequences.\n\n"
        f"{BRAND_NAME}"
    )
    await ctx.send(embed=embed, view=TicketMainView())

@bot.command()
@commands.has_permissions(administrator=True)
async def setverifytext(ctx, *, new_text: str):
    config = load_config()
    config["verify_text"] = new_text
    save_config(config)
    
    embed = discord.Embed(color=0x2b2d31)
    embed.description = f"✅ The verify text has been updated!\n\n**Preview:**\n{new_text}"
    embed.set_footer(text=BRAND_NAME)
    apply_gif_to_embed(embed, as_thumbnail=True)

    gif_file = create_gif_file()
    if gif_file:
        await ctx.send(embed=embed, file=gif_file)
    else:
        await ctx.send(embed=embed)

@bot.command()
@commands.has_permissions(administrator=True)
async def verify(ctx, member: discord.Member):
    config = load_config()
    raw_text = config.get("verify_text", "**Target:** {member}\n\nIf you're seeing this, you've likely just been scammed...")
    formatted_text = raw_text.replace("{member}", member.mention)

    embed = discord.Embed(color=0x2b2d31)
    embed.description = formatted_text
    embed.set_footer(text=BRAND_NAME)
    apply_gif_to_embed(embed, as_thumbnail=False)

    gif_file = create_gif_file()
    if gif_file:
        await ctx.send(embed=embed, view=VerifyView(target_user_id=member.id), file=gif_file)
    else:
        await ctx.send(embed=embed, view=VerifyView(target_user_id=member.id))

@bot.command()
async def add(ctx, member: discord.Member):
    if "ticket" in ctx.channel.name:
        await ctx.channel.set_permissions(member, read_messages=True, send_messages=True)
        embed = discord.Embed(color=0x2b2d31)
        embed.description = f"✅ {member.mention} has been added to the ticket!"
        embed.set_footer(text=BRAND_NAME)
        await ctx.send(embed=embed)
    else:
        embed = discord.Embed(color=0x2b2d31)
        embed.description = "❌ This command can only be used inside a ticket channel!"
        embed.set_footer(text=BRAND_NAME)
        await ctx.send(embed=embed)

@bot.command()
async def close(ctx):
    if "ticket" in ctx.channel.name:
        embed = discord.Embed(color=0x2b2d31)
        embed.description = "🔒 The ticket will be closed and deleted in 5 seconds..."
        embed.set_footer(text=BRAND_NAME)
        await ctx.send(embed=embed)
        await asyncio.sleep(5)
        await ctx.channel.delete()

# --- 8. Slash Commands ---

@bot.tree.command(name="tos", description="Displays the Middleman Terms of Service")
async def tos(interaction: discord.Interaction):
    embed = discord.Embed(
        title=f"📋 {BRAND_NAME} — Terms of Service",
        color=0x3498db,
        timestamp=discord.utils.utcnow()
    )
    embed.description = (
        "**1. 🚫 No Refunds Once Confirmed**\n\nOnce a trade is confirmed and processed by both parties, all deals are final.\n\n"
        "**2. 📸 Proof & Record Keeping Required**\n\nValid proof may be requested at any point.\n\n"
        "**3. ⚖️ Prohibited Goods & Services**\n\nTrading illegal goods or violating Discord ToS is strictly forbidden.\n\n"
        "**4. ⏰ Time Limits & Readiness**\n\nInactivity exceeding 15 minutes will result in ticket termination.\n\n"
        "**5. 🛡️ Disputes, Impersonation & Safety**\n\nAlways verify staff user IDs.\n\n"
        "**6. 💰 Middleman Service Fees**\n\nStandard service fee is 5%.\n\n"
        "**7. 📜 Liability & Risk Disclaimer**\n\nWe are not liable for post-trade issues.\n\n"
        "**8. ✅ Binding Agreement**\n\nBy using our service you agree to these terms."
    )
    embed.set_footer(text=f"Powered by {BRAND_NAME}")
    apply_gif_to_embed(embed, as_thumbnail=True)

    gif_file = create_gif_file()
    if gif_file:
        await interaction.response.send_message(embed=embed, file=gif_file)
    else:
        await interaction.response.send_message(embed=embed)

@bot.tree.command(name="manageban", description="Ban or unban a user from the server")
@app_commands.describe(action="Choose whether to ban or unban the user", user_id="The Discord User ID to ban or unban", reason="Reason")
@app_commands.default_permissions(ban_members=True)
async def manageban(interaction: discord.Interaction, action: Literal["ban", "unban"], user_id: str, reason: Optional[str] = "No reason provided"):
    try:
        target_id = int(user_id.strip())
    except ValueError:
        await interaction.response.send_message("❌ Invalid User ID provided.", ephemeral=True)
        return

    timestamp_str = f"<t:{int(time.time())}:f>"

    if action == "ban":
        try:
            user = await bot.fetch_user(target_id)
            await interaction.guild.ban(user, reason=reason)
            embed = discord.Embed(title="User Banned 🔨", color=0x2b2d31)
            embed.add_field(name="Actioned By", value=f"{interaction.user.name} ({interaction.user.id})", inline=False)
            embed.add_field(name="Target User", value=f"{user.name} ({user.id})", inline=False)
            embed.add_field(name="Reason", value=reason, inline=False)
            embed.add_field(name="Time", value=timestamp_str, inline=False)
            embed.set_footer(text=BRAND_NAME)
        except Exception as e:
            embed = discord.Embed(description=f"❌ Error: {e}", color=0x2b2d31)
    elif action == "unban":
        try:
            user = await bot.fetch_user(target_id)
            await interaction.guild.unban(user, reason=reason)
            embed = discord.Embed(title="User Unbanned 🔓", color=0x2b2d31)
            embed.add_field(name="Actioned By", value=f"{interaction.user.name} ({interaction.user.id})", inline=False)
            embed.add_field(name="Target User", value=f"{user.name} ({user.id})", inline=False)
            embed.add_field(name="Reason", value=reason, inline=False)
            embed.add_field(name="Time", value=timestamp_str, inline=False)
            embed.set_footer(text=BRAND_NAME)
        except Exception as e:
            embed = discord.Embed(description=f"❌ Error: {e}", color=0x2b2d31)

    apply_gif_to_embed(embed, as_thumbnail=True)
    gif_file = create_gif_file()
    if gif_file:
        await interaction.response.send_message(embed=embed, file=gif_file)
    else:
        await interaction.response.send_message(embed=embed)

@bot.tree.command(name="managerole", description="Add or remove a role from a user")
@app_commands.describe(action="add or remove", member="Member", role="Role name or ID", reason="Reason")
@app_commands.default_permissions(manage_roles=True)
async def managerole(interaction: discord.Interaction, action: Literal["add", "remove"], member: discord.Member, role: str, reason: Optional[str] = "No reason provided"):
    embed = discord.Embed(color=0x2b2d31)
    embed.set_footer(text=BRAND_NAME)

    clean_role_str = role.strip("<@&> ").strip()
    target_role = None

    if clean_role_str.isdigit():
        target_role = interaction.guild.get_role(int(clean_role_str))
    if not target_role:
        target_role = discord.utils.get(interaction.guild.roles, name=role)

    if not target_role:
        embed.description = f"❌ Role `{role}` not found."
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    if action == "add":
        await member.add_roles(target_role, reason=reason)
        embed.description = f"✅ Added {target_role.mention} to {member.mention}."
    else:
        await member.remove_roles(target_role, reason=reason)
        embed.description = f"❌ Removed {target_role.mention} from {member.mention}."

    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="mmexplain", description="Explains how the Middleman service works step-by-step")
async def mmexplain(interaction: discord.Interaction):
    embed = discord.Embed(
        title=f"🛡️ How {BRAND_NAME} Middleman Service Works",
        color=0x2b2d31,
        timestamp=discord.utils.utcnow()
    )
    embed.description = (
        "Wondering how our middleman (MM) service keeps you safe? Here's the rundown on how we handle trades to ensure nobody gets scammed.\n\n"
        "**1. 🎫 Open a Ticket**\n"
        "Head over to our middleman channel and click the button to open a private ticket. Make sure to ping or invite the person you're trading with so everyone is in the same channel.\n\n"
        "**2. 📝 Agree on the Deal**\n"
        "Both of you need to state exactly what the trade is. For example, 'My Frost Dragon for their $50 CashApp.' You also need to agree on who is covering any middleman fees if applicable.\n\n"
        "**3. 📥 Securing the Items**\n"
        "The person giving the in-game item or account will trade it directly to the Middleman first. The MM will hold onto it and verify that everything is correct.\n\n"
        "**4. 💸 Sending Payment**\n"
        "Once the MM confirms they have the item secured, the buyer can safely send the money directly to the seller's payment method (PayPal, CashApp, Crypto, etc.).\n\n"
        "**5. ✅ Releasing the Assets**\n"
        "After the seller confirms they've fully received the money, the Middleman will trade the secured item over to the buyer.\n\n"
        "**6. ⭐ Vouch & Close**\n"
        "Once everyone has their stuff, we ask that you drop a quick vouch for the MM, and then we'll lock and close the ticket!"
    )
    embed.set_footer(text=BRAND_NAME)
    apply_gif_to_embed(embed, as_thumbnail=True)

    gif_file = create_gif_file()
    if gif_file:
        await interaction.response.send_message(embed=embed, file=gif_file)
    else:
        await interaction.response.send_message(embed=embed)

@bot.tree.command(name="autovouch", description="Control Auto-Vouch System")
@app_commands.describe(option="on / off / now / status")
@app_commands.default_permissions(administrator=True)
async def autovouch(interaction: discord.Interaction, option: Literal["on", "off", "now", "status"]):
    if option == "on":
        if not auto_vouch_loop.is_running():
            auto_vouch_loop.start()
            await interaction.response.send_message("✅ Auto-Vouch enabled!", ephemeral=True)
        else:
            await interaction.response.send_message("⚠️ Already running.", ephemeral=True)
    elif option == "off":
        if auto_vouch_loop.is_running():
            auto_vouch_loop.cancel()
            await interaction.response.send_message("🛑 Auto-Vouch disabled!", ephemeral=True)
        else:
            await interaction.response.send_message("⚠️ Not running.", ephemeral=True)
    elif option == "now":
        embed = create_vouch_embed(interaction.guild)
        await interaction.response.send_message(embed=embed)
    elif option == "status":
        running = auto_vouch_loop.is_running()
        await interaction.response.send_message(f"Status: {'Active' if running else 'Inactive'}", ephemeral=True)

@bot.tree.command(name="vouchadd", description="Adds vouches to a user")
@app_commands.default_permissions(administrator=True) 
async def vouchadd(interaction: discord.Interaction, member: discord.Member, amount: int):
    vouch_data = load_vouches()
    user_id = str(member.id)
    current_vouches = vouch_data.get(user_id, 0)
    new_vouches = current_vouches + amount
    vouch_data[user_id] = new_vouches
    save_vouches(vouch_data)

    rank_mention = member.top_role.mention if member.top_role else "@Member"

    embed = discord.Embed(
        description="⭐ **User Vouch Profile**",
        color=0x2b2d31,
        timestamp=discord.utils.utcnow()
    )
    embed.set_author(name=member.name, icon_url=member.display_avatar.url)
    embed.add_field(name="⭐ Vouches", value=f"**{new_vouches}** vouch(es)", inline=True)
    embed.add_field(name="👑 Current Rank", value=rank_mention, inline=True)
    embed.set_footer(text=BRAND_NAME)

    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="vouchcount", description="Shows a user's vouches")
async def vouchcount(interaction: discord.Interaction, member: Optional[discord.Member] = None):
    target = member or interaction.user
    vouch_data = load_vouches()
    current_vouches = vouch_data.get(str(target.id), 0)

    rank_mention = target.top_role.mention if target.top_role else "@Member"

    embed = discord.Embed(
        description="⭐ **User Vouch Profile**",
        color=0x2b2d31,
        timestamp=discord.utils.utcnow()
    )
    embed.set_author(name=target.name, icon_url=target.display_avatar.url)
    embed.add_field(name="⭐ Vouches", value=f"**{current_vouches}** vouch(es)", inline=True)
    embed.add_field(name="👑 Current Rank", value=rank_mention, inline=True)
    embed.set_footer(text=BRAND_NAME)

    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="vouch", description="Vouch for a user and post it to the vouch channel")
@app_commands.describe(member="The user you are vouching for", review="Your review or feedback message")
async def vouch(interaction: discord.Interaction, member: discord.Member, review: str = "Smooth and secure transaction!"):
    if member.id == interaction.user.id:
        await interaction.response.send_message("❌ You cannot vouch for yourself!", ephemeral=True)
        return

    # Update vouch data
    vouch_data = load_vouches()
    uid = str(member.id)
    vouch_data[uid] = vouch_data.get(uid, 0) + 1
    save_vouches(vouch_data)

    # Build vouch embed
    embed = discord.Embed(color=0x2ecc71, timestamp=discord.utils.utcnow())
    embed.description = (
        "✅ **new vouch**\n\n"
        f"**User Vouched:** {member.mention}\n"
        f"**Vouched By:** {interaction.user.mention}\n\n"
        "**Review**\n"
        "⭐⭐⭐⭐⭐\n"
        f"*{review}*"
    )
    embed.set_footer(text=f"{BRAND_NAME} • Total Vouches: {vouch_data[uid]}")
    apply_gif_to_embed(embed, as_thumbnail=True)

    # Post to the vouch channel
    channel = bot.get_channel(AUTO_VOUCH_CHANNEL_ID)
    gif_file = create_gif_file()
    
    if channel:
        if gif_file:
            await channel.send(embed=embed, file=create_gif_file())
        else:
            await channel.send(embed=embed)

    await interaction.response.send_message(f"✅ Successfully vouched for {member.mention} and posted it to the vouch channel!", ephemeral=True)

# --- 9. Start Bot ---
if __name__ == "__main__":
    keep_alive()
    TOKEN = os.getenv("DISCORD_TOKEN")
    if TOKEN:
        bot.run(TOKEN)
    else:
        print("❌ Token not found!")
