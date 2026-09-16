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

BRAND_NAME = "IMS"
GIF_FILE_PATH = "IMG_1153_2.gif"
# Direct URL fallback to guarantee the large banner always displays even if local GIF file is missing
GIF_URL = "https://i.imgur.com/5V8p3m0.gif"

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
    return "IMS Bot - Operational"

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

# Permission Helpers
def is_middleman_or_admin():
    async def predicate(ctx):
        if ctx.author.guild_permissions.administrator:
            return True
        has_mm = any(r.id == MIDDLEMAN_ROLE_ID for r in getattr(ctx.author, 'roles', []))
        if not has_mm:
            raise commands.CheckFailure("❌ You need the Middleman role or Administrator permissions to use this command.")
        return True
    return commands.check(predicate)

# Utility Helpers
def apply_gif(embed: discord.Embed, as_thumbnail: bool = False) -> None:
    """Applies local file attachment or fallback URL banner to embed."""
    if os.path.exists(GIF_FILE_PATH):
        if as_thumbnail:
            embed.set_thumbnail(url=f"attachment://{GIF_FILE_PATH}")
        else:
            embed.set_image(url=f"attachment://{GIF_FILE_PATH}")
    elif GIF_URL:
        if as_thumbnail:
            embed.set_thumbnail(url=GIF_URL)
        else:
            embed.set_image(url=GIF_URL)

def build_gif_file() -> Optional[discord.File]:
    if os.path.exists(GIF_FILE_PATH):
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
                    if gif_file:
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

        embed = discord.Embed(
            title=f"🛡️ {BRAND_NAME} — Secure Middleman Session",
            color=0x2b2d31,
            timestamp=discord.utils.utcnow()
        )
        embed.description = (
            "Welcome to your trade ticket! An official Middleman will be with you shortly.\n"
            "Please follow the instructions below to ensure a smooth and safe deal."
        )

        embed.add_field(
            name="👤 Requester",
            value=f"{interaction.user.mention}\n`ID: {interaction.user.id}`",
            inline=True
        )
        embed.add_field(
            name="⏳ Status",
            value="`Waiting for Middleman...`",
            inline=True
        )
        embed.add_field(
            name="⏰ Created",
            value=f"<t:{int(time.time())}:R>",
            inline=True
        )

        embed.add_field(
            name="📋 Trade Details Template",
            value=(
                "Please copy, fill out, and send the format below in this chat:\n"
                "```yaml\n"
                "1. Trading With: @User\n"
                "2. Your Item(s): ...\n"
                "3. Their Item(s): ...\n"
                "```"
            ),
            inline=False
        )

        embed.add_field(
            name="🚨 Safety Protocol",
            value=(
                "• **Do NOT** complete trades outside of this ticket or via DMs.\n"
                "• Always verify that the Middleman holds the <@&" + str(MIDDLEMAN_ROLE_ID) + "> role.\n"
                "• Do not release payment/items until the Middleman confirms receipt."
            ),
            inline=False
        )

        guild_icon = interaction.guild.icon.url if interaction.guild.icon else None
        embed.set_footer(text=f"{BRAND_NAME} • Trade Verification System", icon_url=guild_icon)
        apply_gif(embed, as_thumbnail=False)

        gif_file = build_gif_file()
        content = f"{interaction.user.mention} <@&{MIDDLEMAN_ROLE_ID}>"
        
        kwargs = {"content": content, "embeds": [embed], "view": TicketControlsView()}
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

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ You need Administrator permissions to use this command.")
    elif isinstance(error, commands.CheckFailure):
        await ctx.send(str(error) if str(error) else "❌ You do not have permission to use this command.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Missing argument: `{error.param.name}`")
    elif isinstance(error, commands.CommandNotFound):
        pass
    else:
        logger.error(f"Command error in {ctx.command}: {error}")

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

    rating = random.choice(['⭐⭐⭐⭐⭐', '⭐⭐⭐⭐'])

    embed = discord.Embed(color=0x2ecc71)
    embed.description = (
        "✅ **new vouch**\n\n"
        f"**In-Game Items ↔ {random.choice(methods)}**\n\n"
        f"**trader**\n{trader_mention}\n\n"
        f"**middleman**\n{mm_mention}\n\n"
        f"**trader review**\n{rating}\n*{random.choice(reviews)}*"
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

# Prefix Commands (!prefix)

# --- STRICT ADMIN-ONLY COMMANDS ---

@bot.command()
@commands.has_permissions(administrator=True)
async def sync(ctx):
    """Sync application slash commands with current guild (Admin Only)."""
    bot.tree.copy_global_to(guild=ctx.guild)
    synced = await bot.tree.sync(guild=ctx.guild)
    await ctx.send(f"✅ Synced {len(synced)} command(s).")

@bot.command()
@commands.has_permissions(administrator=True)
async def setup_ticket(ctx):
    """Post the middleman ticket creation panel (Admin Only)."""
    embed = discord.Embed(
        title=f"🛡️ {BRAND_NAME} — Official Middleman Service",
        color=0x2b2d31,
        description=(
            "Welcome to our secure transaction center. Need a safe environment for your high-value trades, "
            "accounts, or digital assets? Our official Middlemen ensure a **100% safe and scam-free process**.\n\n"
            "Click **Request Middleman** below to spawn your private escrow ticket channel instantly!"
        ),
        timestamp=discord.utils.utcnow()
    )

    embed.add_field(
        name="🔄 How Escrow Works",
        value=(
            "1️⃣ **Initiate Trade** — Click the button below to open a ticket.\n"
            "2️⃣ **Confirm Terms** — State all deal details & items clearly.\n"
            "3️⃣ **Asset Deposit** — Seller transfers items directly to the Middleman.\n"
            "4️⃣ **Payment Transfer** — Buyer sends payment/assets to the Seller.\n"
            "5️⃣ **Final Release** — Middleman confirms receipt and releases assets."
        ),
        inline=False
    )

    embed.add_field(
        name="🚨 Safety Rules & Protocols",
        value=(
            "• **Never** complete deals outside of this ticket or in Direct Messages (DMs).\n"
            "• Always verify that your Middleman holds the <@&" + str(MIDDLEMAN_ROLE_ID) + "> role.\n"
            "• Troll or fake ticket creations will result in an immediate permanent blacklist."
        ),
        inline=False
    )

    guild_icon = ctx.guild.icon.url if ctx.guild.icon else None
    embed.set_footer(text=f"{BRAND_NAME} • Trusted Escrow Platform", icon_url=guild_icon)

    # Attach full-size banner image to embed
    apply_gif(embed, as_thumbnail=False)

    gif_file = build_gif_file()
    kwargs = {"embed": embed, "view": TicketMainView()}
    if gif_file:
        kwargs["file"] = gif_file

    await ctx.send(**kwargs)

@bot.command()
@commands.has_permissions(administrator=True)
async def setverify(ctx, *, text: str):
    """Configure custom verification prompt message (Admin Only)."""
    config_store.set("verify_text", text)
    await ctx.send("✅ Verification prompt message updated successfully.")

@bot.command()
@commands.has_permissions(administrator=True)
async def blacklist(ctx, action: str, member: discord.Member, *, reason: str = "Unspecified"):
    """Blacklist or unblacklist a member from ticket features (Admin Only)."""
    action_lower = action.lower()
    if action_lower in ["add", "ban"]:
        blacklist_store.set(str(member.id), {"reason": reason, "timestamp": int(time.time())})
        await ctx.send(f"✅ Blacklisted {member.mention}.\n**Reason:** {reason}")
    elif action_lower in ["remove", "unban", "delete"]:
        blacklist_store.delete(str(member.id))
        await ctx.send(f"✅ Removed {member.mention} from blacklist.")
    else:
        await ctx.send("❌ Invalid action. Use `!blacklist add <member> [reason]` or `!blacklist remove <member>`.")

@bot.command()
@commands.has_permissions(administrator=True)
async def autovouch(ctx):
    """Manually trigger a simulated vouch post in the configured auto-vouch channel (Admin Only)."""
    channel = bot.get_channel(AUTO_VOUCH_CHANNEL_ID) or ctx.channel
    embed = generate_vouch_embed(ctx.guild)
    gif_file = build_gif_file()
    kwargs = {"embed": embed}
    if gif_file:
        kwargs["file"] = gif_file
    await channel.send(**kwargs)
    if channel.id != ctx.channel.id:
        await ctx.send(f"✅ Simulated auto-vouch dispatched to {channel.mention}.")

@bot.command()
@commands.has_permissions(administrator=True)
async def tos(ctx):
    """Display the Terms of Service for trades and tickets (Admin Only)."""
    embed = discord.Embed(
        title="📜 Terms of Service",
        color=0x2b2d31,
        description=(
            "By opening a ticket or trading in this server, you agree to the following terms:\n\n"
            "1. **Follow Instructions:** Always follow the directions given by official Middlemen.\n"
            "2. **No Deal Snagging:** Do not interfere with ongoing trades or attempt to hijack tickets.\n"
            "3. **No Troll Tickets:** Opening fake or troll tickets will result in an instant blacklist.\n"
            "4. **Finality:** All middleman-mediated trades are final once items/payments are released.\n"
            "5. **Impersonation Caution:** Always verify user IDs to prevent scam attempts."
        )
    )
    embed.set_footer(text=BRAND_NAME)
    apply_gif(embed, as_thumbnail=False)

    gif_file = build_gif_file()
    kwargs = {"embed": embed}
    if gif_file:
        kwargs["file"] = gif_file
    await ctx.send(**kwargs)

@bot.command()
@commands.has_permissions(administrator=True)
async def managerole(ctx, action: str, member: discord.Member, role: discord.Role):
    """Add or remove a role from a member (Admin Only)."""
    action_lower = action.lower()
    if action_lower == "add":
        await member.add_roles(role)
        await ctx.send(f"✅ Successfully added role {role.mention} to {member.mention}.")
    elif action_lower in ["remove", "rem"]:
        await member.remove_roles(role)
        await ctx.send(f"✅ Successfully removed role {role.mention} from {member.mention}.")
    else:
        await ctx.send("❌ Invalid action. Use `!managerole add <member> <role>` or `!managerole remove <member> <role>`.")

@bot.command()
@commands.has_permissions(administrator=True)
async def addvouches(ctx, member: discord.Member, amount: int):
    """Add a specific number of vouches to a member (Admin Only)."""
    current = vouches_store.get(str(member.id), 0)
    new_total = current + amount
    vouches_store.set(str(member.id), new_total)
    await ctx.send(f"✅ Added `{amount}` vouches to {member.mention}. New total: `{new_total}` vouches.")

@bot.command()
@commands.has_permissions(administrator=True)
async def manageban(ctx, action: str, user: discord.User, *, reason: str = "No reason provided"):
    """Ban or unban a user from the guild (Admin Only)."""
    action_lower = action.lower()
    if action_lower == "ban":
        await ctx.guild.ban(user, reason=reason)
        await ctx.send(f"✅ Successfully banned {user.mention} (`{user.id}`). Reason: {reason}")
    elif action_lower == "unban":
        await ctx.guild.unban(user, reason=reason)
        await ctx.send(f"✅ Successfully unbanned {user.mention} (`{user.id}`). Reason: {reason}")
    else:
        await ctx.send("❌ Invalid action. Use `!manageban ban <user> [reason]` or `!manageban unban <user> [reason]`.")


# --- MIDDLEMAN & ADMIN ACCESSIBLE COMMANDS ---

@bot.command()
@is_middleman_or_admin()
async def verify(ctx, member: discord.Member):
    """Trigger the verification process for a user (Middleman & Admin)."""
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
@is_middleman_or_admin()
async def clearvouches(ctx, member: discord.Member):
    """Clear all vouches for a user (Middleman & Admin)."""
    vouches_store.set(str(member.id), 0)
    await ctx.send(f"✅ Cleared all vouches for {member.mention}.")


# --- GENERAL & TICKET COMMANDS ---

@bot.command()
async def add(ctx, member: discord.Member):
    """Add a member to a ticket channel."""
    if "ticket" in ctx.channel.name:
        await ctx.channel.set_permissions(member, read_messages=True, send_messages=True)
        await ctx.send(embed=discord.Embed(color=0x2b2d31, description=f"✅ {member.mention} added to ticket."))
    else:
        await ctx.send(embed=discord.Embed(color=0x2b2d31, description="❌ Usable only inside ticket channels."))

@bot.command()
async def remove(ctx, member: discord.Member):
    """Remove a member from a ticket channel."""
    if "ticket" in ctx.channel.name:
        await ctx.channel.set_permissions(member, overwrite=None)
        await ctx.send(embed=discord.Embed(color=0x2b2d31, description=f"✅ {member.mention} removed from ticket."))
    else:
        await ctx.send(embed=discord.Embed(color=0x2b2d31, description="❌ Usable only inside ticket channels."))

@bot.command()
async def close(ctx):
    """Close active ticket and compile transcript."""
    if "ticket" not in ctx.channel.name:
        await ctx.send(embed=discord.Embed(color=0x2b2d31, description="❌ Usable only inside ticket channels."))
        return

    await ctx.send(embed=discord.Embed(color=0x2b2d31, description="🔒 Generating transcript... Closing channel in 5s..."))
    
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
                if gif_file:
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

@bot.command()
async def vouch(ctx, member: discord.Member, *, review: str = "Smooth transaction!"):
    """Submit a vouch for a middleman or trader."""
    if member.id == ctx.author.id:
        await ctx.send("❌ You cannot vouch for yourself.")
        return

    v_count = vouches_store.get(str(member.id), 0) + 1
    vouches_store.set(str(member.id), v_count)

    embed = discord.Embed(color=0x2ecc71, timestamp=discord.utils.utcnow())
    embed.description = (
        f"✅ **new vouch**\n\n"
        f"**User Vouched:** {member.mention}\n"
        f"**Vouched By:** {ctx.author.mention}\n\n"
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

    await ctx.send(f"✅ Vouch submitted for {member.mention}.")

@bot.command()
async def vouches(ctx, member: Optional[discord.Member] = None):
    """View vouch count for yourself or another member."""
    target = member or ctx.author
    count = vouches_store.get(str(target.id), 0)
    embed = discord.Embed(
        color=0x2b2d31,
        description=f"👤 **User:** {target.mention}\n⭐ **Total Vouches:** `{count}`"
    )
    embed.set_footer(text=BRAND_NAME)
    apply_gif(embed, as_thumbnail=True)
    await ctx.send(embed=embed)

@bot.command()
async def mmexplain(ctx):
    """Explain how the Middleman system works."""
    embed = discord.Embed(
        title="🛡️ Middleman Service Explained",
        color=0x3498db,
        description=(
            "A **Middleman (MM)** is a verified third party who holds items safely during a trade.\n\n"
            "**How the Process Works:**\n"
            "1️⃣ **Open Ticket:** Click the **Request Middleman** button in the ticket channel.\n"
            "2️⃣ **Confirm Terms:** Both trading parties state the exact deal details in the ticket.\n"
            "3️⃣ **Secure Items:** The seller/trader transfers items to the official Middleman.\n"
            "4️⃣ **Payment Sent:** The buyer sends payment/items directly to the seller.\n"
            "5️⃣ **Release:** Middleman confirms payment receipt and releases the held assets to the buyer.\n\n"
            "⚠️ **Warning:** Never trade via Direct Messages! Always check the Middleman role badge."
        )
    )
    embed.set_footer(text=BRAND_NAME)
    apply_gif(embed, as_thumbnail=False)

    gif_file = build_gif_file()
    kwargs = {"embed": embed}
    if gif_file:
        kwargs["file"] = gif_file
    await ctx.send(**kwargs)

@bot.command()
async def ping(ctx):
    """Check bot latency."""
    latency = round(bot.latency * 1000)
    await ctx.send(f"🏓 Pong! Latency: `{latency}ms`")

if __name__ == "__main__":
    keep_alive()
    token = os.getenv("DISCORD_TOKEN")
    if token:
        bot.run(token)
    else:
        logger.critical("Missing DISCORD_TOKEN environment variable.")
