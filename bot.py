import os
import json
import time
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
        # Default values if nothing is saved yet
        return {
            "verify_title": "🔐 Server Verification",
            "verify_text": "Welcome to the server, {member}!\n\nTo gain full access to the channels and start trading safely, please verify your account by clicking the **Accept** button below.\n\n⚠️ *By clicking accept, you agree to our server rules.*"
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
        # Checks if the interacting user is the target person
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
        
        embed = discord.Embed(color=discord.Color.green())
        embed.description = f"✅ Success! {interaction.user.mention} has been successfully verified."
        await interaction.response.edit_message(content="", embed=embed, view=None)

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.danger, custom_id="verify_decline")
    async def decline_button(self, interaction: discord.Interaction, button: Button):
        embed = discord.Embed(color=discord.Color.red())
        embed.description = f"❌ {interaction.user.mention} has declined the verification process."
        await interaction.response.edit_message(content="", embed=embed, view=None)

# --- 3. Ticket Controls (Claim only for Middlemen) ---
class TicketControlsView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Claim Ticket", style=discord.ButtonStyle.primary, custom_id="claim_ticket")
    async def claim_button(self, interaction: discord.Interaction, button: Button):
        # Check if the user has the Middleman role or Admin permissions
        has_mm_role = any(role.id == MIDDLEMAN_ROLE_ID for role in interaction.user.roles)
        is_admin = interaction.user.guild_permissions.administrator

        if not has_mm_role and not is_admin:
            await interaction.response.send_message("❌ Only Middlemen can claim this ticket!", ephemeral=True)
            return

        await interaction.channel.set_permissions(interaction.user, read_messages=True, send_messages=True)
        button.disabled = True
        await interaction.message.edit(view=self)
        
        embed = discord.Embed(color=discord.Color.blue())
        embed.description = f"🛡️ {interaction.user.mention} has claimed this ticket and is your middleman."
        await interaction.response.send_message(embed=embed)

    @discord.ui.button(label="Close Ticket", style=discord.ButtonStyle.danger, custom_id="close_ticket")
    async def close_button(self, interaction: discord.Interaction, button: Button):
        embed = discord.Embed(color=discord.Color.red())
        embed.description = "🔒 This ticket will be closed and deleted in 5 seconds..."
        await interaction.response.send_message(embed=embed)
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
            name=f"mm-ticket-{interaction.user.name}",
            category=category,
            overwrites=overwrites
        )

        await interaction.response.send_message(f"Your ticket has been created: {ticket_channel.mention}", ephemeral=True)

        await ticket_channel.send(
            f"Welcome to your middleman ticket, {interaction.user.mention}!\n"
            f"<@&{MIDDLEMAN_ROLE_ID}> - A new ticket has been opened.\n\n"
            f"**Commands:**\n"
            f"`!add @user` - Adds your trading partner to the ticket.",
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
                embed = discord.Embed(title="🚨 ANTI-NUKE TRIGGERED", color=discord.Color.red())
                embed.description = (
                    f"**Server:** {guild.name}\n"
                    f"**Action:** The bot banned {user.mention} (`{user.id}`).\n"
                    f"**Reason:** Limit for `{action_type}` exceeded within {TIME_WINDOW}s."
                )
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
    embed.set_footer(text="Trade Assistant")
    await ctx.send(embed=embed, view=TicketView())

@bot.command()
@commands.has_permissions(administrator=True)
async def setverifytext(ctx, *, new_text: str):
    """Changes the text of the verify message. Use {member} to mention the user."""
    config = load_config()
    config["verify_text"] = new_text
    save_config(config)
    
    embed = discord.Embed(color=discord.Color.green())
    embed.description = f"✅ The verify text has been updated!\n\n**Preview:**\n{new_text}"
    await ctx.send(embed=embed)

@bot.command()
@commands.has_permissions(administrator=True)
async def setverifytitle(ctx, *, new_title: str):
    """Changes the title of the verify message."""
    config = load_config()
    config["verify_title"] = new_title
    save_config(config)
    
    embed = discord.Embed(color=discord.Color.green())
    embed.description = f"✅ The verify title has been updated to:\n**{new_title}**"
    await ctx.send(embed=embed)

@bot.command()
@commands.has_permissions(administrator=True)
async def verify(ctx, member: discord.Member):
    config = load_config()
    
    # Load title and text from the config
    title = config.get("verify_title", "🔐 Server Verification")
    raw_text = config.get("verify_text", "Welcome to the server, {member}!\n\nTo gain full access to the channels and start trading safely, please verify your account by clicking the **Accept** button below.\n\n⚠️ *By clicking accept, you agree to our server rules.*")
    
    # Replace {member} with the actual user ping
    formatted_text = raw_text.replace("{member}", member.mention)

    embed = discord.Embed(title=title, color=0x2b2d31)
    embed.description = formatted_text
    embed.set_footer(text="Security & Verification System")
    
    await ctx.send(
        content=f"👋 Hello {member.mention}, action required:", 
        embed=embed, 
        view=VerifyView(target_user_id=member.id)
    )

@bot.command()
async def add(ctx, member: discord.Member):
    if "mm-ticket" in ctx.channel.name:
        await ctx.channel.set_permissions(member, read_messages=True, send_messages=True)
        embed = discord.Embed(color=discord.Color.green())
        embed.description = f"✅ {member.mention} has been added to the ticket!"
        await ctx.send(embed=embed)
    else:
        embed = discord.Embed(color=discord.Color.red())
        embed.description = "❌ This command can only be used inside a ticket channel!"
        await ctx.send(embed=embed)

@bot.command()
async def close(ctx):
    if "mm-ticket" in ctx.channel.name:
        embed = discord.Embed(color=discord.Color.red())
        embed.description = "🔒 The ticket will be closed and deleted in 5 seconds..."
        await ctx.send(embed=embed)
        await asyncio.sleep(5)
        await ctx.channel.delete()

# --- 8. Slash Commands (Vouches, Fill, Temp) ---

@bot.tree.command(name="vouchadd", description="Adds vouches to a user")
@app_commands.default_permissions(administrator=True) 
async def vouchadd(interaction: discord.Interaction, member: discord.Member, amount: int):
    vouch_data = load_vouches()
    user_id = str(member.id)
    current_vouches = vouch_data.get(user_id, 0)
    new_vouches = current_vouches + amount
    vouch_data[user_id] = new_vouches
    save_vouches(vouch_data)

    embed = discord.Embed(color=discord.Color.green())
    embed.set_author(name=member.name, icon_url=member.display_avatar.url)
    embed.add_field(name="Vouches added", value=f"+{amount} for {member.mention}", inline=False)
    embed.add_field(name="Total Vouches", value=str(new_vouches), inline=True)
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

    embed = discord.Embed(color=discord.Color.orange(), title="⏳ Assigning roles...")
    embed.description = f"🛠️ Assigning **{len(roles_to_add)}** roles to {member.mention}..."
    await interaction.response.send_message(embed=embed)

    async def process_fill():
        try:
            await member.add_roles(*roles_to_add, reason="Fill command executed")
            embed.title = "✅ Roles assigned"
            embed.color = discord.Color.green()
            embed.description = f"🛠️ **{len(roles_to_add)}** role(s) were assigned to {member.mention}."
            await interaction.edit_original_response(embed=embed)
        except discord.Forbidden:
            embed.title = "❌ Error"
            embed.color = discord.Color.red()
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

        embed = discord.Embed(color=discord.Color.orange(), title="⏳ Restoring roles...")
        await interaction.response.send_message(embed=embed)

        async def process_restore():
            try:
                await member.add_roles(*roles_to_add, reason="Temp command executed")
                del temp_data[user_id]
                save_temp_roles(temp_data)
                embed.title = "✅ Roles restored"
                embed.color = discord.Color.blue()
                embed.description = f"🛠️ **{len(roles_to_add)}** role(s) restored."
                await interaction.edit_original_response(embed=embed)
            except discord.Forbidden:
                embed.title = "❌ Error"
                embed.color = discord.Color.red()
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

        embed = discord.Embed(color=discord.Color.orange(), title="⏳ Removing roles...")
        await interaction.response.send_message(embed=embed)

        async def process_temp_remove():
            try:
                await member.remove_roles(*roles_to_remove, reason="Temp command executed")
                embed.title = "✅ Roles removed"
                embed.color = discord.Color.red()
                embed.description = f"🛠️ **{len(roles_to_remove)}** role(s) temporarily removed."
                await interaction.edit_original_response(embed=embed)
            except discord.Forbidden:
                embed.title = "❌ Error"
                embed.color = discord.Color.red()
                embed.description = "Missing permissions to remove roles."
                await interaction.edit_original_response(embed=embed)

        bot.loop.create_task(process_temp_remove())

# --- 9. Start the Bot ---
keep_alive()
token = os.environ.get("DISCORD_TOKEN")
bot.run(token)
