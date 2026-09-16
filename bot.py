import os
import io
import json
import time
import random
import logging
import asyncio
from datetime import datetime
from collections import defaultdict
from typing import Literal, Optional, Any, Dict
from threading import Thread

import discord
from discord.ext import commands, tasks
from discord.ui import Button, View
from discord import app_commands
from flask import Flask

# Logging Setup
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("IMSBot")

# Configuration Constants
MIDDLEMAN_ROLE_ID = 1411386035551867044
TICKET_CATEGORY_ID = 1415896804024651908
MEMBER_ROLE_ID = 1411088611926868168
AUTO_VOUCH_CHANNEL_ID = 1546151910199922719
TRANSCRIPT_CHANNEL_ID = 0  # Replace with transcript log channel ID

BRAND_NAME = "IMS Helper Bot"
GIF_FILE_PATH = "IMG_1153_2.gif"
GIF_URL = None

DEFAULT_VERIFY_TEXT = (
    "**Target:** {member}\n\n"
    "If you're seeing this, you've likely just been scammed — but this doesn't end how you think.\n\n"
    "Most people in this server started out the same way. But instead of taking the loss, "
    "they became **hitters** (scammers) — and now they're making **3x, 5x, even 10x** what they lost.\n\n"
    "This is your chance to turn a setback into serious profit.\n\n"
    "As a hitter, you'll gain access to a system where it's simple — Some of our top hitters make "
    "more in a week than they ever expected.\n\n"
    "**You now have access to the staff chat and other hitter channels.** Head to the main guide channel to learn how to start.\n\n"
    "⏰ Every minute you wait is profit missed.\n\n"
    "Need help getting started? Ask in the support system channel.\n\n"
    "You've already been pulled in — now it's time to flip the script and come out ahead."
)

# Web Service Keep-Alive
app = Flask('')

@app.route('/')
def home():
    return "IMS Helper Bot - Operational"

def run_webserver():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    Thread(target=run_webserver, daemon=True).start()

# State Manager
class JSONStore:
    def __init__(self, filename: str, default: Any = None):
        self.filename = filename
        self.default = default if default is not None else {}

    def get_all(self) -> Dict[str, Any]:
        if not os.path.exists(self.filename):
            return self.default.copy()
        try:
            with open(self.filename, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error reading {self.filename}: {e}")
            return self.default.copy()

    def set_all(self, data: Dict[str, Any]) -> None:
        try:
            with open(self.filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            logger.error(f"Error writing to {self.filename}: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        return self.get_all().get(key, default)

    def set(self, key: str, value: Any) -> None:
        data = self.get_all()
        data[str(key)] = value
        self.set_all(data)

    def delete(self, key: str) -> None:
        data = self.get_all()
        if str(key) in data:
            del data[str(key)]
            self.set_all(data)

# Store Instances
vouches_store = JSONStore("vouches.json", {})
blacklist_store = JSONStore("blacklist.json", {})
tickets_store = JSONStore("tickets.json", {})
config_store = JSONStore("config.json", {"verify_text": DEFAULT_VERIFY_TEXT})

# Utility Helpers
def apply_gif(embed: discord.Embed, as_thumbnail: bool = True) -> None:
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

def build_gif_file() -> Optional[discord.File]:
    if not GIF_URL and os.path.exists(GIF_FILE_PATH):
        return discord.File(GIF_FILE_PATH, filename=GIF_FILE_PATH)
    return None

async def create_transcript(channel: discord.TextChannel) -> io.BytesIO:
    lines = []
    async for msg in channel.history(limit=None, oldest_first=True):
        ts = msg.created_at.strftime("%Y-%m-%d %H:%M:%S")
        author = f"{msg.author} ({msg.author.id})"
        content = msg.content
        if msg.attachments:
            content += " [Attachments: " + ", ".join([a.url for a in msg.attachments]) + "]"
        lines.append(f"[{ts}] {author}: {content}")
    
    return io.BytesIO("\n".join(lines).encode('utf-8'))

# Views
class VerifyView(View):
    def __init__(self, target_user_id: int):
        super().__init__(timeout=300)
        self.target_user_id = target_user_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.target_user_id:
            return True
        await interaction.response.send_message("❌ This interaction is not assigned to you.", ephemeral=True)
        return False

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.green, custom_id="verify_accept")
    async def accept(self, interaction: discord.Interaction, button: Button):
        role = interaction.guild.get_role(MEMBER_ROLE_ID)
        if role:
            try:
                await interaction.user.add_roles(role)
            except discord.Forbidden:
                logger.warning(f"Insufficient permissions to assign role {MEMBER_ROLE_ID}")

        embed = discord.Embed(color=0x2b2d31, description=f"✅ {interaction.user.mention} has been successfully verified.")
        embed.set_footer(text=BRAND_NAME)
        apply_gif(embed, as_thumbnail=True)

        gif_file = build_gif_file()
        kwargs = {"content": "", "embed": embed, "view": None}
        if gif_file:
            kwargs["attachments"] = [gif_file]
        await interaction.response.edit_message(**kwargs)

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.danger, custom_id="verify_decline")
    async def decline(self, interaction: discord.Interaction, button: Button):
        embed = discord.Embed(color=0x2b2d31, description=f"❌ {interaction.user.mention} declined verification.")
        embed.set_footer(text=BRAND_NAME)
        apply_gif(embed, as_thumbnail=True)

        gif_file = build_gif_file()
        kwargs = {"content": "", "embed": embed, "view": None}
        if gif_file:
            kwargs["attachments"] = [gif_file]
        await interaction.response.edit_message(**kwargs)

class TicketControlsView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Claim", style=discord.ButtonStyle.green, custom_id="claim_ticket")
    async def claim(self, interaction: discord.Interaction, button: Button):
        has_role = any(r.id == MIDDLEMAN_ROLE_ID for r in interaction.user.roles)
        if not has_role and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Only Middlemen can claim tickets.", ephemeral=True)
            return

        creator_id = tickets_store.get(str(interaction.channel.id))
        if creator_id and interaction.user.id == int(creator_id):
            await interaction.response.send_message("❌ You cannot claim your own ticket.", ephemeral=True)
            return

        await interaction.channel.set_permissions(interaction.user, read_messages=True, send_messages=True)
        
        button.disabled = True
        for child in self.children:
            if child.custom_id == "unclaim_ticket":
                child.disabled = False
        await interaction.response.edit_message(view=self)

        embed = discord.Embed(color=0x2b2d31, description=f"🛡️ {interaction.user.mention} claimed this ticket.")
        embed.set_footer(text=BRAND_NAME)
        apply_gif(embed, as_thumbnail=True)

        gif_file = build_gif_file()
        if gif_file:
            await interaction.channel.send(embed=embed, file=gif_file)
        else:
            await interaction.channel.send(embed=embed)

    @discord.ui.button(label="Unclaim", style=discord.ButtonStyle.secondary, custom_id="unclaim_ticket")
    async def unclaim(self, interaction: discord.Interaction, button: Button):
        has_role = any(r.id == MIDDLEMAN_ROLE_ID for r in interaction.user.roles)
        if not has_role and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Only Middlemen can unclaim tickets.", ephemeral=True)
            return

        button.disabled = True
        for child in self.children:
            if child.custom_id == "claim_ticket":
                child.disabled = False
        await interaction.response.edit_message(view=self)

        embed = discord.Embed(color=0x2b2d31, description=f"🔓 {interaction.user.mention} unclaimed this ticket.")
        embed.set_footer(text=BRAND_NAME)
        apply_gif(embed, as_thumbnail=True)

        gif_file = build_gif_file()
        if gif_file:
            await interaction.channel.send(embed=embed, file=gif_file)
        else:
            await interaction.channel.send(embed=embed)

    @discord.ui.button(label="Close", style=discord.ButtonStyle.danger, custom_id="close_ticket")
    async def close(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()

        for child in self.children:
            child.disabled = True
        await interaction.message.edit(view=self)

        embed = discord.Embed(color=0x2b2d31, description="🔒 Generating transcript... Closing channel in 5 seconds...")
        embed.set_footer(text=BRAND_NAME)
        await interaction.channel.send(embed=embed)

        try:
            buffer = await create_transcript(interaction.channel)
            buffer.seek(0)
            file_obj = discord.File(buffer, filename=f"transcript-{interaction.channel.name}.txt")

            if TRANSCRIPT_CHANNEL_ID:
                t_channel = interaction.guild.get_channel(TRANSCRIPT_CHANNEL_ID)
                if t_channel:
                    t_embed = discord.Embed(
                        title="📁 Ticket Transcript",
                        color=0x2b2d31,
                        timestamp=discord.utils.utcnow(),
                        description=f"Transcript for **{interaction.channel.name}** closed by {interaction.user.mention}."
                    )
                    t_embed.set_footer(text=BRAND_NAME)
                    apply_gif(t_embed, as_thumbnail=True)

                    gif_file = build_gif_file()
                    files = [file_obj]
                    if gif_file and not GIF_URL:
                        files.append(gif_file)

                    await t_channel.send(embed=t_embed, files=files)
        except Exception as e:
            logger.error(f"Failed to compile transcript for {interaction.channel.id}: {e}")

        tickets_store.delete(str(interaction.channel.id))
        await asyncio.sleep(5)
        
        try:
            await interaction.channel.delete()
        except discord.NotFound:
            pass

class TicketMainView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Request Middleman", style=discord.ButtonStyle.green, custom_id="request_middleman_main")
    async def create_ticket(self, interaction: discord.Interaction, button: Button):
        bl_entry = blacklist_store.get(str(interaction.user.id))
        if bl_entry:
            reason = bl_entry.get("reason", "No reason specified.")
            await interaction.response.send_message(f"❌ You are blacklisted from opening tickets.\n**Reason:** {reason}", ephemeral=True)
            return

        mm_role = interaction.guild.get_role(MIDDLEMAN_ROLE_ID)
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            interaction.guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        if mm_role:
            overwrites[mm_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

        category = interaction.guild.get_channel(TICKET_CATEGORY_ID)
        ticket_channel = await interaction.guild.create_text_channel(
            name=f"ticket-{interaction.user.name}",
            category=category,
            overwrites=overwrites
        )

        tickets_store.set(str(ticket_channel.id), interaction.user.id)
        await interaction.response.send_message(f"Ticket opened: {ticket_channel.mention}", ephemeral=True)

        e1 = discord.Embed(
            title=f"💠 {BRAND_NAME} — Trade Ticket",
            color=0x3498db,
            description="Thank you for using our middleman services.\nPlease wait for an available middleman."
        )
        e1.set_footer(text=BRAND_NAME)
        apply_gif(e1, as_thumbnail=True)

        e2 = discord.Embed(title="Trade Parties", color=0x2b2d31, description=f"**Requester:**\n{interaction.user.mention}")
        e2.set_footer(text=BRAND_NAME)

        gif_file = build_gif_file()
        content = f"{interaction.user.mention} <@&{MIDDLEMAN_ROLE_ID}>"
        
        kwargs = {"content": content, "embeds": [e1, e2], "view": TicketControlsView()}
        if gif_file:
            kwargs["file"] = gif_file
        await ticket_channel.send(**kwargs)

# Client Initialization
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    bot.add_view(TicketMainView())
    bot.add_view(TicketControlsView())
    if not auto_vouch_loop.is_running():
        auto_vouch_loop.start()
    logger.info(f"Connected as {bot.user} (ID: {bot.user.id})")

# Anti-Nuke Architecture
nuke_tracker = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
TIME_WINDOW = 60
LIMITS = {'channel_delete': 3, 'channel_create': 5, 'role_delete': 3, 'role_create': 5, 'ban': 4}

async def fetch_audit_executor(guild: discord.Guild, action: discord.AuditLogAction) -> Optional[discord.User]:
    try:
        async for entry in guild.audit_logs(limit=1, action=action):
            return entry.user
    except discord.Forbidden:
        return None

async def evaluate_nuke(guild: discord.Guild, user: Optional[discord.User], action_key: str):
    if not user or user.id in (bot.user.id, guild.owner_id):
        return

    now = time.time()
    history = [t for t in nuke_tracker[guild.id][user.id][action_key] if now - t < TIME_WINDOW]
    history.append(now)
    nuke_tracker[guild.id][user.id][action_key] = history

    if len(history) > LIMITS[action_key]:
        try:
            await guild.ban(user, reason=f"Anti-Nuke Triggered: {action_key} threshold breached.")
            if guild.owner:
                embed = discord.Embed(title="🚨 ANTI-NUKE TRIGGERED", color=0x2b2d31)
                embed.description = f"**Server:** {guild.name}\n**Banned User:** {user.mention} (`{user.id}`)\n**Reason:** Exceeded {action_key} limits."
                embed.set_footer(text=BRAND_NAME)
                apply_gif(embed, as_thumbnail=True)
                
                gif_file = build_gif_file()
                kwargs = {"embed": embed}
                if gif_file:
                    kwargs["file"] = gif_file
                await guild.owner.send(**kwargs)
        except discord.Forbidden:
            logger.warning(f"Failed to auto-ban nuke suspect {user.id} due to hierarchy/permissions.")

@bot.event
async def on_guild_channel_delete(channel):
    actor = await fetch_audit_executor(channel.guild, discord.AuditLogAction.channel_delete)
    await evaluate_nuke(channel.guild, actor, 'channel_delete')

@bot.event
async def on_guild_channel_create(channel):
    actor = await fetch_audit_executor(channel.guild, discord.AuditLogAction.channel_create)
    await evaluate_nuke(channel.guild, actor, 'channel_create')

@bot.event
async def on_guild_role_delete(role):
    actor = await fetch_audit_executor(role.guild, discord.AuditLogAction.role_delete)
    await evaluate_nuke(role.guild, actor, 'role_delete')

@bot.event
async def on_guild_role_create(role):
    actor = await fetch_audit_executor(role.guild, discord.AuditLogAction.role_create)
    await evaluate_nuke(role.guild, actor, 'role_create')

@bot.event
async def on_member_ban(guild, user):
    actor = await fetch_audit_executor(guild, discord.AuditLogAction.ban)
    await evaluate_nuke(guild, actor, 'ban')

# Auto-Vouch Loop
def generate_vouch_embed(guild: discord.Guild) -> discord.Embed:
    eligible = [m for m in guild.members if not m.bot and (any(r.id == MIDDLEMAN_ROLE_ID for r in m.roles) or m.guild_permissions.administrator)]
    selected_mm = random.choice(eligible) if eligible else guild.owner

    if selected_mm:
        mm_mention = selected_mm.mention
        v_count = vouches_store.get(str(selected_mm.id), 0) + 1
        vouches_store.set(str(selected_mm.id), v_count)
    else:
        mm_mention = f"<@{guild.owner_id}>"

    traders = [m for m in guild.members if not m.bot and m.id != getattr(selected_mm, 'id', None)]
    trader_mention = random.choice(traders).mention if traders and random.choice([True, False, False]) else f"<@{random.randint(10**17, 10**18 - 1)}>"

    methods = ["PayPal", "CashApp", "Crypto", "Bank Transfer", "Apple Pay", "Venmo"]
    reviews = [
        "Trustworthy mm, will definitely request again for big deals.",
        "Very friendly and made the trade super easy, tysm!",
        "Super quick and answered all my questions patiently, vouch!",
        "Smooth transaction, no issues at all. +rep",
        "Fast and reliable as always.",
        "Best middleman ever! Kept everything secure.",
        "100% legit, guided me through the whole process."
    ]

    embed = discord.Embed(color=0x2ecc71)
    embed.description = (
        "✅ **new vouch**\n\n"
        f"**In-Game Items ↔ {random.choice(methods)}**\n\n"
        f"**trader**\n{trader_mention}\n\n"
        f"**middleman**\n{mm_mention}\n\n"
        f"**trader review**\n{random.choice(['⭐⭐⭐⭐⭐', '⭐⭐⭐⭐'] philosophy := True)}\n*{random.choice(reviews)}*"
    )
    embed.set_footer(text=f"{BRAND_NAME} • trade #{random.randint(100000, 999999)} | {datetime.now().strftime('%Y/%m/%d, %H:%M')}")
    apply_gif(embed, as_thumbnail=True)
    return embed

@tasks.loop(minutes=14)
async def auto_vouch_loop():
    channel = bot.get_channel(AUTO_VOUCH_CHANNEL_ID)
    if channel:
        embed = generate_vouch_embed(channel.guild)
        gif_file = build_gif_file()
        kwargs = {"embed": embed}
        if gif_file:
            kwargs["file"] = gif_file
        await channel.send(**kwargs)

@auto_vouch_loop.before_loop
async def prepare_vouch_loop():
    await bot.wait_until_ready()

# Commands
@bot.command()
@commands.has_permissions(administrator=True)
async def sync(ctx):
    bot.tree.copy_global_to(guild=ctx.guild)
    synced = await bot.tree.sync(guild=ctx.guild)
    await ctx.send(f"✅ Synced {len(synced)} command(s).")

@bot.command()
@commands.has_permissions(administrator=True)
async def setup_ticket(ctx):
    embed = discord.Embed(
        title="Middleman Service",
        color=0x2b2d31,
        description=(
            "• Click **Request Middleman** below to initialize a secure transaction channel.\n\n"
            "**How it works:**\n"
            "1. Parties agree to terms in the ticket.\n"
            "2. Middleman secures assets from seller/trader.\n"
            "3. Buyer transfers payment/assets.\n"
            "4. Middleman verifies receipt and releases held assets.\n\n"
            "⚠️ Do not open troll tickets."
        )
    )
    embed.set_footer(text=BRAND_NAME)
    await ctx.send(embed=embed, view=TicketMainView())

@bot.command()
@commands.has_permissions(administrator=True)
async def verify(ctx, member: discord.Member):
    raw_text = config_store.get("verify_text", DEFAULT_VERIFY_TEXT)
    embed = discord.Embed(color=0x2b2d31, description=raw_text.replace("{member}", member.mention))
    embed.set_footer(text=BRAND_NAME)
    apply_gif(embed, as_thumbnail=False)

    gif_file = build_gif_file()
    kwargs = {"embed": embed, "view": VerifyView(target_user_id=member.id)}
    if gif_file:
        kwargs["file"] = gif_file
    await ctx.send(**kwargs)

@bot.command()
async def add(ctx, member: discord.Member):
    if "ticket" in ctx.channel.name:
        await ctx.channel.set_permissions(member, read_messages=True, send_messages=True)
        await ctx.send(embed=discord.Embed(color=0x2b2d31, description=f"✅ {member.mention} added."))
    else:
        await ctx.send(embed=discord.Embed(color=0x2b2d31, description="❌ Usable only in ticket channels."))

@bot.command()
async def close(ctx):
    if "ticket" not in ctx.channel.name:
        await ctx.send(embed=discord.Embed(color=0x2b2d31, description="❌ Usable only in ticket channels."))
        return

    await ctx.send(embed=discord.Embed(color=0x2b2d31, description="🔒 Generating transcript... Channel closing in 5s..."))
    
    try:
        buffer = await create_transcript(ctx.channel)
        buffer.seek(0)
        file_obj = discord.File(buffer, filename=f"transcript-{ctx.channel.name}.txt")

        if TRANSCRIPT_CHANNEL_ID:
            t_channel = ctx.guild.get_channel(TRANSCRIPT_CHANNEL_ID)
            if t_channel:
                t_embed = discord.Embed(
                    title="📁 Ticket Transcript",
                    color=0x2b2d31,
                    timestamp=discord.utils.utcnow(),
                    description=f"Transcript for **{ctx.channel.name}** closed by {ctx.author.mention}."
                )
                t_embed.set_footer(text=BRAND_NAME)
                apply_gif(t_embed, as_thumbnail=True)

                gif_file = build_gif_file()
                files = [file_obj]
                if gif_file and not GIF_URL:
                    files.append(gif_file)

                await t_channel.send(embed=t_embed, files=files)
    except Exception as e:
        logger.error(f"Error handling transcript command: {e}")

    tickets_store.delete(str(ctx.channel.id))
    await asyncio.sleep(5)
    
    try:
        await ctx.channel.delete()
    except discord.NotFound:
        pass

# Slash Commands
@bot.tree.command(name="blacklist", description="Manage user ticket permissions")
@app_commands.default_permissions(administrator=True)
async def blacklist(interaction: discord.Interaction, action: Literal["add", "remove"], member: discord.Member, reason: Optional[str] = "Unspecified"):
    if action == "add":
        blacklist_store.set(str(member.id), {"reason": reason, "timestamp": int(time.time())})
        await interaction.response.send_message(f"✅ Blacklisted {member.mention}.\nReason: {reason}", ephemeral=True)
    else:
        blacklist_store.delete(str(member.id))
        await interaction.response.send_message(f"✅ Removed {member.mention} from blacklist.", ephemeral=True)

@bot.tree.command(name="vouch", description="Submit feedback for a middleman")
async def vouch(interaction: discord.Interaction, member: discord.Member, review: str = "Smooth transaction!"):
    if member.id == interaction.user.id:
        await interaction.response.send_message("❌ Self-vouching is disabled.", ephemeral=True)
        return

    v_count = vouches_store.get(str(member.id), 0) + 1
    vouches_store.set(str(member.id), v_count)

    embed = discord.Embed(color=0x2ecc71, timestamp=discord.utils.utcnow())
    embed.description = (
        f"✅ **new vouch**\n\n"
        f"**User Vouched:** {member.mention}\n"
        f"**Vouched By:** {interaction.user.mention}\n\n"
        f"**Review**\n⭐⭐⭐⭐⭐\n*{review}*"
    )
    embed.set_footer(text=f"{BRAND_NAME} • Total Vouches: {v_count}")
    apply_gif(embed, as_thumbnail=True)

    channel = bot.get_channel(AUTO_VOUCH_CHANNEL_ID)
    if channel:
        gif_file = build_gif_file()
        kwargs = {"embed": embed}
        if gif_file:
            kwargs["file"] = gif_file
        await channel.send(**kwargs)

    await interaction.response.send_message(f"✅ Vouch registered for {member.mention}.", ephemeral=True)

if __name__ == "__main__":
    keep_alive()
    token = os.getenv("DISCORD_TOKEN")
    if token:
        bot.run(token)
    else:
        logger.critical("Missing DISCORD_TOKEN environment variable.")
