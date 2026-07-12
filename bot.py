import discord
from discord.ext import commands
from discord import app_commands
import time
import asyncio
import random
import datetime
import os  # Wichtig für Render Port-Abfrage
from flask import Flask
from threading import Thread

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

# ─── SPAM TRACKER ───────────────────────────────────────────
spam_tracker = {}
SPAM_LIMIT = 5
SPAM_ZEITRAUM = 5

# ─── WARN TRACKER ───────────────────────────────────────────
warnings = {}

# ─── AUTO-MOD SETTINGS ──────────────────────────────────────
BAD_WORDS = ["badword1", "badword2", "badword3"]  # Add your bad words here
MAX_MENTIONS = 5
MAX_CAPS_PERCENT = 70
INVITE_PATTERN = "discord.gg"

# ════════════════════════════════════════════════════════════
#  OWNER-ONLY CHECK
# ════════════════════════════════════════════════════════════

def is_owner():
    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.guild is None:
            await interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
            return False
        if interaction.user.id != interaction.guild.owner_id:
            await interaction.response.send_message("❌ Only the server owner can use this command!", ephemeral=True)
            return False
        return True
    return app_commands.check(predicate)

# ════════════════════════════════════════════════════════════
#  EVENTS
# ════════════════════════════════════════════════════════════

@bot.event
async def on_ready():
    await tree.sync()
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="the server 👀"))
    print(f"Bot is online: {bot.user}")

@bot.event
async def on_member_join(member):
    channel = discord.utils.get(member.guild.text_channels, name="welcome")
    if channel:
        embed = discord.Embed(
            title=f"👋 Welcome {member.name}!",
            description=f"Welcome to **{member.guild.name}**! You are member #{member.guild.member_count}.",
            color=discord.Color.green()
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        await channel.send(embed=embed)

@bot.event
async def on_member_remove(member):
    channel = discord.utils.get(member.guild.text_channels, name="welcome")
    if channel:
        embed = discord.Embed(
            title=f"👋 {member.name} left the server.",
            color=discord.Color.red()
        )
        await channel.send(embed=embed)

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # Owner bypasses all auto-mod
    if message.author.id == message.guild.owner_id:
        await bot.process_commands(message)
        return

    user_id = message.author.id
    jetzt = time.time()
    content = message.content

    # ── Auto-Mod: Bad Words ──────────────────────────────────
    if any(word in content.lower() for word in BAD_WORDS):
        await message.delete()
        await message.channel.send(f"⚠️ {message.author.mention} Bad language is not allowed!", delete_after=5)
        return

    # ── Auto-Mod: Discord Invites ────────────────────────────
    if INVITE_PATTERN in content.lower():
        await message.delete()
        await message.channel.send(f"⚠️ {message.author.mention} Posting invite links is not allowed!", delete_after=5)
        return

    # ── Auto-Mod: Mass Mentions ──────────────────────────────
    if len(message.mentions) >= MAX_MENTIONS:
        await message.delete()
        await message.channel.send(f"⚠️ {message.author.mention} Mass mentioning is not allowed!", delete_after=5)
        return

    # ── Auto-Mod: Caps Lock ──────────────────────────────────
    if len(content) > 10:
        caps = sum(1 for c in content if c.isupper())
        if (caps / len(content)) * 100 >= MAX_CAPS_PERCENT:
            await message.delete()
            await message.channel.send(f"⚠️ {message.author.mention} Please don't use excessive caps!", delete_after=5)
            return

    # ── Anti-Spam ────────────────────────────────────────────
    if user_id not in spam_tracker:
        spam_tracker[user_id] = []
    spam_tracker[user_id] = [t for t in spam_tracker[user_id] if jetzt - t < SPAM_ZEITRAUM]
    spam_tracker[user_id].append(jetzt)
    if len(spam_tracker[user_id]) > SPAM_LIMIT:
        await message.delete()
        await message.channel.send(f"⚠️ {message.author.mention} Please do not spam!", delete_after=5)
        mute_role = discord.utils.get(message.guild.roles, name="Muted")
        if mute_role and mute_role not in message.author.roles:
            await message.author.add_roles(mute_role)
            await message.channel.send(f"🔇 {message.author.mention} has been auto-muted for spamming (5 minutes).", delete_after=10)
            await asyncio.sleep(300)
            await message.author.remove_roles(mute_role)
        return

    await bot.process_commands(message)

# ════════════════════════════════════════════════════════════
#  VERIFY SYSTEM (everyone can use)
# ════════════════════════════════════════════════════════════

@tree.command(name="verify", description="Verify yourself on the server")
async def verify(interaction: discord.Interaction):
    view = discord.ui.View()
    yes_button = discord.ui.Button(label="✅ Yes", style=discord.ButtonStyle.green)
    no_button = discord.ui.Button(label="❌ No", style=discord.ButtonStyle.red)

    async def yes_callback(i):
        await i.response.send_message("✅ You have been verified! Welcome!", ephemeral=True)

    async def no_callback(i):
        await i.response.send_message("❌ Verification cancelled.", ephemeral=True)

    yes_button.callback = yes_callback
    no_button.callback = no_callback
    view.add_item(yes_button)
    view.add_item(no_button)

    await interaction.response.send_message(
        "👋 **Welcome!**\nDo you agree to the server rules and want to verify yourself?",
        view=view,
        ephemeral=True
    )

# ════════════════════════════════════════════════════════════
#  TICKET SYSTEM — FIXED
# ════════════════════════════════════════════════════════════

class CloseTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="👤 Claim", style=discord.ButtonStyle.green, custom_id="claim_ticket")
    async def claim_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        button.label = f"✅ Claimed by {interaction.user.name}"
        button.disabled = True
        await interaction.message.edit(view=self)
        await interaction.response.send_message(f"👤 {interaction.user.mention} has claimed this ticket!")

    @discord.ui.button(label="🔒 Close Ticket", style=discord.ButtonStyle.red, custom_id="close_ticket")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("🔒 Closing ticket in 5 seconds...")
        await asyncio.sleep(5)
        await interaction.channel.delete()


class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🎫 Open Ticket", style=discord.ButtonStyle.blurple, custom_id="open_ticket")
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        user = interaction.user

        existing = discord.utils.get(guild.text_channels, name=f"ticket-{user.name.lower()}")
        if existing:
            await interaction.response.send_message(f"❌ You already have an open ticket: {existing.mention}", ephemeral=True)
            return

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.owner: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        }

        category = discord.utils.get(guild.categories, name="TICKETS")
        if not category:
            category = await guild.create_category("TICKETS")

        channel = await guild.create_text_channel(
            f"ticket-{user.name}",
            overwrites=overwrites,
            category=category
        )

        close_view = CloseTicketView()
        embed = discord.Embed(
            title="🎫 New Ticket",
            description=f"Hello {user.mention}! 👋\nSupport will be with you shortly.\n\nPlease describe your issue below.",
            color=discord.Color.blurple()
        )
        embed.set_footer(text="Click 'Close Ticket' when your issue is resolved.")
        await channel.send(embed=embed, view=close_view)
        await interaction.response.send_message(f"✅ Your ticket has been created: {channel.mention}", ephemeral=True)


@tree.command(name="ticket", description="Send the ticket panel to this channel")
@is_owner()
async def ticket(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🎫 Support Tickets",
        description="Need help? Click the button below to open a ticket!\nOur support team will assist you as soon as possible.",
        color=discord.Color.blurple()
    )
    embed.set_footer(text="Please only open a ticket if you have a real issue.")
    await interaction.channel.send(embed=embed, view=TicketView())
    await interaction.response.send_message("✅ Ticket panel sent!", ephemeral=True)

# ════════════════════════════════════════════════════════════
#  HIT COMMAND — SCAM REPORT
# ════════════════════════════════════════════════════════════

class HitConfirmView(discord.ui.View):
    def __init__(self, target: discord.Member):
        super().__init__(timeout=60)
        self.target = target

    @discord.ui.button(label="✅ Yes, I'm in!", style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        for item in self.children:
            item.disabled = True
        await interaction.message.edit(view=self)
        embed = discord.Embed(
            title="💰 Welcome to the Team!",
            description=f"✅ {interaction.user.mention} is **in**!\n\nYou will be contacted soon with further instructions. Get ready to make some serious profit. 💵",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed)

    @discord.ui.button(label="❌ No, I'm not interested", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        for item in self.children:
            item.disabled = True
        await interaction.message.edit(view=self)
        embed = discord.Embed(
            title="😔 Maybe next time...",
            description=f"❌ {interaction.user.mention} declined the offer.\n\nIf you change your mind, you know where to find us. 💸",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed)


@tree.command(name="hit", description="Send someone a special business offer")
async def hit(interaction: discord.Interaction, member: discord.Member):
    embed = discord.Embed(
        title="💸 EXCLUSIVE BUSINESS OFFER 💸",
        color=discord.Color.gold()
    )
    embed.add_field(name="📩 Hey there!", value=(
        f"👋 **01** — Hey {member.mention}, we noticed you!\n"
        f"💰 **02** — We have a very special offer for you\n"
        f"📈 **03** — You could be making way more money\n"
        f"🤑 **04** — Our team earns big profits every single day\n"
        f"💵 **05** — No special skills required to join us\n"
        f"🔥 **06** — This is a limited opportunity, don't miss it\n"
        f"📊 **07** — Our members make profit on every deal\n"
        f"🎯 **08** — You only need a few minutes per day\n"
        f"💎 **09** — The more you participate, the more you earn\n"
        f"🚀 **10** — We have been doing this for a long time\n"
        f"🧠 **11** — Our strategy is simple but very effective\n"
        f"👑 **12** — Top earners in our team make thousands\n"
        f"📦 **13** — We handle everything, you just collect profit\n"
        f"🤝 **14** — This is a trusted and proven method\n"
        f"💬 **15** — Many people have already joined and succeeded\n"
    ), inline=False)
    embed.add_field(name="🔐 Why Join Us?", value=(
        f"✅ **16** — 100% profit on every operation\n"
        f"✅ **17** — You stay anonymous, no one will know\n"
        f"✅ **18** — We work fast and smart, not hard\n"
        f"✅ **19** — Payouts are quick and reliable\n"
        f"✅ **20** — We protect all members of our team\n"
        f"✅ **21** — No investment needed to get started\n"
        f"✅ **22** — You can quit anytime you want\n"
        f"✅ **23** — We operate across multiple platforms\n"
        f"✅ **24** — Trusted by hundreds of members worldwide\n"
        f"✅ **25** — You will never run out of opportunities\n"
        f"✅ **26** — Daily payouts, no waiting around\n"
        f"✅ **27** — We teach you everything from scratch\n"
        f"✅ **28** — Join now and get a bonus on your first hit\n"
        f"✅ **29** — The team grows stronger with every member\n"
        f"✅ **30** — So... are you ready to make real money? 💰\n"
    ), inline=False)
    embed.set_footer(text=f"Offer sent by {interaction.user} • React below to accept or decline")

    view = HitConfirmView(target=member)
    await interaction.response.send_message(f"{member.mention}", embed=embed, view=view)

# ════════════════════════════════════════════════════════════
#  MODERATION COMMANDS (owner only)
# ════════════════════════════════════════════════════════════

@tree.command(name="ban", description="Ban a member")
@is_owner()
async def ban(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
    await member.ban(reason=reason)
    await interaction.response.send_message(f"🔨 **{member}** has been banned. Reason: {reason}")

@tree.command(name="unban", description="Unban a user by ID")
@is_owner()
async def unban(interaction: discord.Interaction, user_id: str, reason: str = "No reason provided"):
    user = await bot.fetch_user(int(user_id))
    await interaction.guild.unban(user, reason=reason)
    await interaction.response.send_message(f"✅ **{user}** has been unbanned.")

@tree.command(name="kick", description="Kick a member")
@is_owner()
async def kick(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
    await member.kick(reason=reason)
    await interaction.response.send_message(f"👢 **{member}** has been kicked. Reason: {reason}")

@tree.command(name="mute", description="Mute a member")
@is_owner()
async def mute(interaction: discord.Interaction, member: discord.Member, minutes: int = 10, reason: str = "No reason provided"):
    mute_role = discord.utils.get(interaction.guild.roles, name="Muted")
    if not mute_role:
        mute_role = await interaction.guild.create_role(name="Muted")
        for channel in interaction.guild.channels:
            await channel.set_permissions(mute_role, send_messages=False, speak=False)
    await member.add_roles(mute_role, reason=reason)
    await interaction.response.send_message(f"🔇 **{member}** has been muted for {minutes} minutes. Reason: {reason}")
    await asyncio.sleep(minutes * 60)
    await member.remove_roles(mute_role)

@tree.command(name="unmute", description="Unmute a member")
@is_owner()
async def unmute(interaction: discord.Interaction, member: discord.Member):
    mute_role = discord.utils.get(interaction.guild.roles, name="Muted")
    if mute_role in member.roles:
        await member.remove_roles(mute_role)
        await interaction.response.send_message(f"🔊 **{member}** has been unmuted.")
    else:
        await interaction.response.send_message(f"❌ **{member}** is not muted.", ephemeral=True)

@tree.command(name="warn", description="Warn a member")
@is_owner()
async def warn(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
    uid = str(member.id)
    if uid not in warnings:
        warnings[uid] = []
    warnings[uid].append({"reason": reason, "time": str(datetime.datetime.now())})
    count = len(warnings[uid])
    await interaction.response.send_message(f"⚠️ **{member}** has been warned. Reason: {reason} (Total warnings: {count})")
    if count >= 3:
        await interaction.channel.send(f"🔨 **{member}** has reached 3 warnings and has been automatically banned!")
        await member.ban(reason="3 warnings reached")

@tree.command(name="warnings", description="Check warnings of a member")
@is_owner()
async def check_warnings(interaction: discord.Interaction, member: discord.Member):
    uid = str(member.id)
    if uid not in warnings or not warnings[uid]:
        await interaction.response.send_message(f"✅ **{member}** has no warnings.", ephemeral=True)
        return
    embed = discord.Embed(title=f"⚠️ Warnings for {member}", color=discord.Color.orange())
    for i, w in enumerate(warnings[uid], 1):
        embed.add_field(name=f"Warning {i}", value=f"Reason: {w['reason']}\nTime: {w['time']}", inline=False)
    await interaction.response.send_message(embed=embed)

@tree.command(name="clearwarnings", description="Clear all warnings of a member")
@is_owner()
async def clearwarnings(interaction: discord.Interaction, member: discord.Member):
    warnings[str(member.id)] = []
    await interaction.response.send_message(f"✅ Warnings cleared for **{member}**.")

@tree.command(name="purge", description="Delete multiple messages")
@is_owner()
async def purge(interaction: discord.Interaction, amount: int):
    await interaction.response.defer(ephemeral=True)
    await interaction.channel.purge(limit=amount)
    await interaction.followup.send(f"🗑️ Deleted {amount} messages.", ephemeral=True)

@tree.command(name="slowmode", description="Set slowmode in the current channel")
@is_owner()
async def slowmode(interaction: discord.Interaction, seconds: int):
    await interaction.channel.edit(slowmode_delay=seconds)
    await interaction.response.send_message(f"🐢 Slowmode set to {seconds} seconds.")

@tree.command(name="lock", description="Lock the current channel")
@is_owner()
async def lock(interaction: discord.Interaction):
    await interaction.channel.set_permissions(interaction.guild.default_role, send_messages=False)
    await interaction.response.send_message("🔒 Channel locked!")

@tree.command(name="unlock", description="Unlock the current channel")
@is_owner()
async def unlock(interaction: discord.Interaction):
    await interaction.channel.set_permissions(interaction.guild.default_role, send_messages=True)
    await interaction.response.send_message("🔓 Channel unlocked!")

@tree.command(name="nickname", description="Change nickname of a member")
@is_owner()
async def nickname(interaction: discord.Interaction, member: discord.Member, nickname: str):
    await member.edit(nick=nickname)
    await interaction.response.send_message(f"✅ Nickname of **{member}** changed to **{nickname}**.")

@tree.command(name="addrole", description="Add a role to a member")
@is_owner()
async def addrole(interaction: discord.Interaction, member: discord.Member, role: discord.Role):
    await member.add_roles(role)
    await interaction.response.send_message(f"✅ Role **{role.name}** added to **{member}**.")

@tree.command(name="removerole", description="Remove a role from a member")
@is_owner()
async def removerole(interaction: discord.Interaction, member: discord.Member, role: discord.Role):
    await member.remove_roles(role)
    await interaction.response.send_message(f"✅ Role **{role.name}** removed from **{member}**.")

# ════════════════════════════════════════════════════════════
#  SERVER MANAGEMENT COMMANDS (owner only)
# ════════════════════════════════════════════════════════════

@tree.command(name="revamp", description="Setup Grow a Garden 2 channel structure")
@is_owner()
async def revamp(interaction: discord.Interaction):
    await interaction.response.send_message("🏗️ **Starting Server Revamp for 'Grow a Garden 2'...**\nDeleting old layout and building the garden structure...", ephemeral=True)
    guild = interaction.guild

    # Delete existing channels (except the current one)
    for channel in guild.channels:
        if channel != interaction.channel:
            try:
                await channel.delete()
            except Exception:
                pass

    # Structure Data for Grow a Garden 2
    structure = {
        "📌 ▬▬ INFO & NEWS ▬▬": [
            ("👋-welcome", discord.ChannelType.text),
            ("📜-rules", discord.ChannelType.text),
            ("📢-announcements", discord.ChannelType.text),
            ("🎁-giveaways", discord.ChannelType.text)
        ],
        "💬 ▬▬ COMMUNITY ▬▬": [
            ("🌿-garden-chat", discord.ChannelType.text),
            ("🤖-bot-commands", discord.ChannelType.text),
            ("🌌-memes", discord.ChannelType.text),
            ("🔊 Lounge", discord.ChannelType.voice),
            ("🔊 Gaming", discord.ChannelType.voice)
        ],
        "🌻 ▬▬ GARDEN GAMEPLAY ▬▬": [
            ("🌾-flex-your-garden", discord.ChannelType.text),
            ("🫘-seed-market", discord.ChannelType.text),
            ("🤝-trading", discord.ChannelType.text),
            ("💡-garden-tips", discord.ChannelType.text)
        ],
        "🎫 ▬▬ SUPPORT ▬▬": [
            ("🎫-open-ticket", discord.ChannelType.text)
        ]
    }

    # Create Categories and Channels
    for cat_name, channels in structure.items():
        category = await guild.create_category(cat_name)
        for ch_name, ch_type in channels:
            if ch_type == discord.ChannelType.text:
                await guild.create_text_channel(ch_name, category=category)
            elif ch_type == discord.ChannelType.voice:
                await guild.create_voice_channel(ch_name, category=category)

    try:
        await interaction.channel.send("✅ **Server Revamp complete!** 'Grow a Garden 2' theme has been fully applied. 🌱")
    except Exception:
        pass

@tree.command(name="deleteallchannels", description="⚠️ Delete ALL channels in the server")
@is_owner()
async def deleteallchannels(interaction: discord.Interaction):
    await interaction.response.send_message("⚠️ Deleting all channels in 5 seconds... (This cannot be undone!)")
    await asyncio.sleep(5)
    for channel in interaction.guild.channels:
        try:
            await channel.delete()
        except Exception:
            pass

@tree.command(name="createchannel", description="Create a new text channel")
@is_owner()
async def createchannel(interaction: discord.Interaction, name: str):
    channel = await interaction.guild.create_text_channel(name)
    await interaction.response.send_message(f"✅ Channel {channel.mention} created!")

@tree.command(name="deletechannel", description="Delete a channel")
@is_owner()
async def deletechannel(interaction: discord.Interaction, channel: discord.TextChannel):
    await channel.delete()
    await interaction.response.send_message(f"✅ Channel **{channel.name}** deleted!", ephemeral=True)

@tree.command(name="createrole", description="Create a new role")
@is_owner()
async def createrole(interaction: discord.Interaction, name: str):
    role = await interaction.guild.create_role(name=name)
    await interaction.response.send_message(f"✅ Role **{role.name}** created!")

@tree.command(name="deleterole", description="Delete a role")
@is_owner()
async def deleterole(interaction: discord.Interaction, role: discord.Role):
    await role.delete()
    await interaction.response.send_message(f"✅ Role **{role.name}** deleted!")

@tree.command(name="serverinfo", description="Show server information")
@is_owner()
async def serverinfo(interaction: discord.Interaction):
    guild = interaction.guild
    embed = discord.Embed(title=f"📊 {guild.name}", color=discord.Color.blurple())
    embed.add_field(name="Members", value=guild.member_count)
    embed.add_field(name="Channels", value=len(guild.channels))
    embed.add_field(name="Roles", value=len(guild.roles))
    embed.add_field(name="Owner", value=guild.owner)
    embed.add_field(name="Created At", value=guild.created_at.strftime("%Y-%m-%d"))
    embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
    await interaction.response.send_message(embed=embed)

@tree.command(name="userinfo", description="Show info about a user")
@is_owner()
async def userinfo(interaction: discord.Interaction, member: discord.Member):
    embed = discord.Embed(title=f"👤 {member}", color=discord.Color.blurple())
    embed.add_field(name="ID", value=member.id)
    embed.add_field(name="Joined Server", value=member.joined_at.strftime("%Y-%m-%d"))
    embed.add_field(name="Account Created", value=member.created_at.strftime("%Y-%m-%d"))
    embed.add_field(name="Roles", value=", ".join([r.name for r in member.roles[1:]]) or "None")
    embed.set_thumbnail(url=member.display_avatar.url)
    await interaction.response.send_message(embed=embed)

@tree.command(name="membercount", description="Show the member count")
@is_owner()
async def membercount(interaction: discord.Interaction):
    await interaction.response.send_message(f"👥 This server has **{interaction.guild.member_count}** members!")

# ════════════════════════════════════════════════════════════
#  FUN COMMANDS (owner only)
# ════════════════════════════════════════════════════════════

@tree.command(name="ping", description="Check bot latency")
@is_owner()
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message(f"🏓 Pong! `{round(bot.latency * 1000)}ms`")

@tree.command(name="coinflip", description="Flip a coin")
@is_owner()
async def coinflip(interaction: discord.Interaction):
    result = random.choice(["Heads 🪙", "Tails 🪙"])
    await interaction.response.send_message(f"🪙 The coin landed on: **{result}**!")

@tree.command(name="dice", description="Roll a dice")
@is_owner()
async def dice(interaction: discord.Interaction, sides: int = 6):
    result = random.randint(1, sides)
    await interaction.response.send_message(f"🎲 You rolled a **{result}** (1-{sides})!")

@tree.command(name="8ball", description="Ask the magic 8ball a question")
@is_owner()
async def eightball(interaction: discord.Interaction, question: str):
    responses = [
        "Yes! ✅", "No ❌", "Maybe 🤔", "Definitely! 🎯",
        "Ask again later ⏳", "I don't think so 🚫", "Absolutely! 🌟",
        "Very doubtful 😐", "Signs point to yes 👍", "Don't count on it 👎"
    ]
    await interaction.response.send_message(f"🎱 **Question:** {question}\n**Answer:** {random.choice(responses)}")

@tree.command(name="choose", description="Let the bot choose between options (separate with commas)")
@is_owner()
async def choose(interaction: discord.Interaction, options: str):
    choices = [o.strip() for o in options.split(",")]
    await interaction.response.send_message(f"🎯 I choose: **{random.choice(choices)}**!")

@tree.command(name="poll", description="Create a poll")
@is_owner()
async def poll(interaction: discord.Interaction, question: str):
    embed = discord.Embed(title=f"📊 Poll: {question}", color=discord.Color.blurple())
    embed.set_footer(text=f"Poll by {interaction.user}")
    msg = await interaction.channel.send(embed=embed)
    await msg.add_reaction("👍")
    await msg.add_reaction("👎")
    await interaction.response.send_message("✅ Poll created!", ephemeral=True)

@tree.command(name="say", description="Make the bot say something")
@is_owner()
async def say(interaction: discord.Interaction, message: str):
    await interaction.response.send_message("✅ Sent!", ephemeral=True)
    await interaction.channel.send(message)

@tree.command(name="embed", description="Send an embed message")
@is_owner()
async def embed_cmd(interaction: discord.Interaction, title: str, description: str):
    embed = discord.Embed(title=title, description=description, color=discord.Color.blurple())
    await interaction.channel.send(embed=embed)
    await interaction.response.send_message("✅ Embed sent!", ephemeral=True)

@tree.command(name="avatar", description="Get the avatar of a user")
@is_owner()
async def avatar(interaction: discord.Interaction, member: discord.Member = None):
    member = member or interaction.user
    embed = discord.Embed(title=f"🖼️ Avatar of {member}", color=discord.Color.blurple())
    embed.set_image(url=member.display_avatar.url)
    await interaction.response.send_message(embed=embed)

@tree.command(name="announce", description="Send an announcement")
@is_owner()
async def announce(interaction: discord.Interaction, channel: discord.TextChannel, message: str):
    embed = discord.Embed(
        title="📢 Announcement",
        description=message,
        color=discord.Color.gold()
    )
    embed.set_footer(text=f"Announced by {interaction.user}")
    await channel.send(embed=embed)
    await interaction.response.send_message("✅ Announcement sent!", ephemeral=True)

@tree.command(name="uptime", description="Show bot uptime")
@is_owner()
async def uptime(interaction: discord.Interaction):
    now = datetime.datetime.utcnow()
    delta = now - bot.start_time
    hours, remainder = divmod(int(delta.total_seconds()), 3600)
    minutes, seconds = divmod(remainder, 60)
    await interaction.response.send_message(f"⏱️ Uptime: **{hours}h {minutes}m {seconds}s**")

@tree.command(name="botinfo", description="Show info about the bot")
@is_owner()
async def botinfo(interaction: discord.Interaction):
    embed = discord.Embed(title="🤖 Bot Info", color=discord.Color.blurple())
    embed.add_field(name="Name", value=bot.user.name)
    embed.add_field(name="Servers", value=len(bot.guilds))
    embed.add_field(name="Ping", value=f"{round(bot.latency * 1000)}ms")
    embed.set_thumbnail(url=bot.user.display_avatar.url)
    await interaction.response.send_message(embed=embed)

# ════════════════════════════════════════════════════════════
#  WEB SERVER & AUTO-RESTART SYSTEM (Optimized for Render)
# ════════════════════════════════════════════════════════════

app = Flask('')

@app.route('/')
def home():
    return "Bot läuft 24/7 auf Render!"

def run():
    # Zieht sich den Port dynamisch von Render, um Timeout-Fehler zu vermeiden
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.start()

def run_bot():
    while True:
        try:
            bot.start_time = datetime.datetime.utcnow()
            # Startet den Flask-Server, den Render zum Überleben braucht
            keep_alive() 
            # Startet deinen Bot
            bot.run("MTUxNzgyMDg2MTQzNDgyMjc2Nw.GAsk4F.obcBkeeiTMG9fAXMnhypyVBAUJPmmhR4AP2URw")
        except Exception as e:
            print(f"Bot crashed: {e}")
            print("Restarting in 5 seconds...")
            time.sleep(5)

run_bot()