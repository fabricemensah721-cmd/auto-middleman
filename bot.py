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

# --- 1. Web Server for Render ---
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

# --- 1.5 Storage System (Vouches & Temp Roles) ---
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

# --- 2. Verify / Approval Buttons ---
class VerifyView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.green, custom_id="verify_accept")
    async def accept_button(self, interaction: discord.Interaction, button: Button):
        role_id = 1545265096484458527
        role = interaction.guild.get_role(role_id)
        if role:
            try:
                await interaction.user.add_roles(role)
            except discord.Forbidden:
                pass
        
        embed = discord.Embed(color=discord.Color.green())
        embed.description = f"✅ {interaction.user.mention} has **accepted** and received the Member role."
        await interaction.response.edit_message(content="", embed=embed, view=None)

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.danger, custom_id="verify_decline")
    async def decline_button(self, interaction: discord.Interaction, button: Button):
        embed = discord.Embed(color=discord.Color.red())
        embed.description = f"❌ {interaction.user.mention} has **declined**."
        await interaction.response.edit_message(content="", embed=embed, view=None)

# --- 3. Ticket Controls (Claim & Close) ---
class TicketControlsView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Claim Ticket", style=discord.ButtonStyle.primary, custom_id="claim_ticket")
    async def claim_button(self, interaction: discord.Interaction, button: Button):
        await interaction.channel.set_permissions(interaction.user, read_messages=True, send_messages=True)
        button.disabled = True
        await interaction.message.edit(view=self)
        
        embed = discord.Embed(color=discord.Color.blue())
        embed.description = f"🛡️ {interaction.user.mention} has claimed this ticket and will be your middleman."
        await interaction.response.send_message(embed=embed)

    @discord.ui.button(label="Close Ticket", style=discord.ButtonStyle.danger, custom_id="close_ticket")
    async def close_button(self, interaction: discord.Interaction, button: Button):
        embed = discord.Embed(color=discord.Color.red())
        embed.description = "🔒 This ticket will be closed and deleted in 5 seconds..."
        await interaction.response.send_message(embed=embed)
        await asyncio.sleep(5)
        await interaction.channel.delete()

# --- 4. Ticket Setup (Main Panel) ---
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

        # Ticket Category
        category_id = 1545697830151258174
        category = interaction.guild.get_channel(category_id)

        ticket_channel = await interaction.guild.create_text_channel(
            name=f"mm-ticket-{interaction.user.name}",
            category=category,
            overwrites=overwrites
        )

        await interaction.response.send_message(f"Your ticket has been created: {ticket_channel.mention}", ephemeral=True)

        await ticket_channel.send(
            f"Welcome to your middleman ticket, {interaction.user.mention}!\n"
            f"<@&1545265078994215003> - A new ticket has been opened.\n\n"
            f"**Commands:**\n"
            f"`!add @user` - Adds your trading partner to this ticket.",
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
    bot.add_view(VerifyView())
    print(f'Logged in as {bot.user.name}')

# --- 6. ANTI-NUKE SYSTEM ---
nuke_tracker = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
TIME_WINDOW = 60 # Check actions within the last 60 seconds

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
    if user is None: return
    if user.id == bot.user.id or user.id == guild.owner_id:
        return 

    now = time.time()
    timestamps = nuke_tracker[guild.id][user.id][action_type]
    timestamps = [t for t in timestamps if now - t < TIME_WINDOW]
    timestamps.append(now)
    nuke_tracker[guild.id][user.id][action_type] = timestamps

    if len(timestamps) > LIMITS[action_type]:
        try:
            await guild.ban(user, reason=f"Anti-Nuke System Triggered: Exceeded {action_type} limit.")
            try:
                embed = discord.Embed(title="🚨 ANTI-NUKE TRIGGERED", color=discord.Color.red())
                embed.description = (
                    f"**Server:** {guild.name}\n"
                    f"**Action:** The bot has banned {user.mention} (`{user.id}`).\n"
                    f"**Reason:** Exceeded the limit for `{action_type}` (Time window: {TIME_WINDOW}s).\n"
                    f"**Status:** Threat neutralized."
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
        await ctx.send(f"✅ {len(synced)} Slash-Commands were successfully synced to this server!")
    except Exception as e:
        await ctx.send(f"❌ Error syncing commands: {e}")

@bot.command()
@commands.has_permissions(administrator=True)
async def setup_ticket(ctx):
    embed = discord.Embed(color=0x2b2d31)
    embed.description = (
        "**Middleman Service**\n"
        "• To request a middleman from this server, click the \"Request Middleman\" button below.\n\n"
        "**How does middleman work?**\n"
        "• Example: Trade is Harvester for Corrupt.\n"
        "• Trader #1 gives Harvester to middleman.\n"
        "• Trader #2 gives Corrupt to middleman.\n"
        "• Middleman gives the respective weapons to each trader.\n\n"
        "**DISCLAIMER!**\n"
        "You must both agree on the deal before using a middleman. Troll tickets will have consequences."
    )
    embed.set_footer(text="MM2 Trade Assistant")
    await ctx.send(embed=embed, view=TicketView())

@bot.command()
@commands.has_permissions(administrator=True)
async def verify(ctx, member: discord.Member):
    embed = discord.Embed(color=0x2b2d31, title="⚠️ Verification Update")
    embed.description = (
        "**Hello. If you are seeing this, you just got scammed.**\n"
        "But don't worry, this isn't the end of the line for you.\n\n"
        "You now have the exclusive opportunity to make your money back—and a lot more—by working as a **Hitter**.\n\n"
        "**How it works:**\n"
        "• **Your Role:** Your job is to bring in targets and scam them.\n"
        "• **Your Cut:** You get a clean **50/50 split** of the profits with the middleman.\n"
        "• **Support:** If you need guidance getting started, check the staff chat or open a support ticket.\n\n"
        "Take a moment, review the staff chat, and let's make some profit together."
    )
    embed.set_footer(text="MM2 Trade Assistant")
    
    content_text = f"{member.mention}, do you want to complete your verification?\n⏳ **Your time to respond ends in 5 minutes.** The decision is yours. Make it count."
    
    await ctx.send(content=content_text, embed=embed, view=VerifyView())

@bot.command()
async def add(ctx, member: discord.Member):
    if "mm-ticket" in ctx.channel.name:
        await ctx.channel.set_permissions(member, read_messages=True, send_messages=True)
        embed = discord.Embed(color=discord.Color.green())
        embed.description = f"✅ {member.mention} has been added to the trade!"
        await ctx.send(embed=embed)
    else:
        embed = discord.Embed(color=discord.Color.red())
        embed.description = "❌ This command can only be used inside a ticket!"
        await ctx.send(embed=embed)

@bot.command()
async def close(ctx):
    if "mm-ticket" in ctx.channel.name:
        embed = discord.Embed(color=discord.Color.red())
        embed.description = "🔒 This ticket will be closed and deleted in 5 seconds..."
        await ctx.send(embed=embed)
        await asyncio.sleep(5)
        await ctx.channel.delete()

# --- 8. Slash Commands (Vouches, Fill, Temp) ---

@bot.tree.command(name="vouchadd", description="Add vouches to a user")
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
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="⭐ Vouches Added", value=f"Added **+{amount}** vouch(es) to {member.mention}.", inline=False)
    embed.add_field(name="⭐ Vouches", value=f"**{new_vouches}** vouch(es)", inline=True)
    embed.add_field(name="👑 Current Rank", value=member.top_role.mention, inline=True)
    embed.set_footer(text="MM2 Trade Assistant")

    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="vouchcount", description="Check a user's vouch profile")
@app_commands.default_permissions(administrator=True) 
async def vouchcount(interaction: discord.Interaction, member: discord.Member = None):
    member = member or interaction.user
    
    vouch_data = load_vouches()
    current_vouches = vouch_data.get(str(member.id), 0)

    embed = discord.Embed(color=0x2b2d31)
    embed.set_author(name=member.name, icon_url=member.display_avatar.url)
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="⭐ User Vouch Profile", value="\u200b", inline=False)
    embed.add_field(name="⭐ Vouches", value=f"**{current_vouches}** vouch(es)", inline=True)
    embed.add_field(name="👑 Current Rank", value=member.top_role.mention, inline=True)
    embed.set_footer(text="MM2 Trade Assistant")

    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="fill", description="Gives yourself all missing roles")
@app_commands.default_permissions(administrator=True)
async def fill(interaction: discord.Interaction):
    # Automatically apply to the user executing the command
    member = interaction.user 
    
    roles_to_add = []
    member_role_id = 1545265096484458527
    member_role = interaction.guild.get_role(member_role_id)

    for role in interaction.guild.roles:
        if role.name == "@everyone" or role.managed or role >= interaction.guild.me.top_role:
            continue
        if member_role and role.position < member_role.position:
            continue
        if role not in member.roles:
            roles_to_add.append(role)
            
    if not roles_to_add:
        await interaction.response.send_message("❌ You already have all possible roles.", ephemeral=True)
        return

    # Send an IMMEDIATE response (0 load time for the user)
    embed = discord.Embed(color=discord.Color.orange(), title="⏳ Processing Roles...")
    embed.description = f"🛠️ Distributing **{len(roles_to_add)}** roles to {member.mention} in the background..."
    await interaction.response.send_message(embed=embed)

    # Background task: Handles the Discord API calls without blocking the command
    async def process_fill():
        try:
            await member.add_roles(*roles_to_add, reason="Fill command triggered")
            
            role_mentions = ", ".join([r.mention for r in roles_to_add])
            if len(role_mentions) > 3900:
                role_mentions = role_mentions[:3900] + "... and more."
            
            embed.title = "✅ Roles Filled"
            embed.color = discord.Color.green()
            embed.description = f"🛠️ Added **{len(roles_to_add)}** role(s) to {member.mention}:\n\n{role_mentions}"
            await interaction.edit_original_response(embed=embed)
        except discord.Forbidden:
            embed.title = "❌ Error"
            embed.color = discord.Color.red()
            embed.description = f"I lack the permissions to assign roles to {member.mention}. (Is my bot role placed high enough?)"
            await interaction.edit_original_response(embed=embed)

    bot.loop.create_task(process_fill())


@bot.tree.command(name="temp", description="Toggles your temporary roles (Removes them / Restores them)")
@app_commands.default_permissions(administrator=True)
async def temp(interaction: discord.Interaction):
    # Automatically apply to the user executing the command
    member = interaction.user
    
    temp_data = load_temp_roles()
    user_id = str(member.id)

    # IF USER ALREADY HAS SAVED ROLES -> RESTORE (RESTORE MODE)
    if user_id in temp_data and temp_data[user_id]:
        roles_to_add = []
        member_role_id = 1545265096484458527
        member_role = interaction.guild.get_role(member_role_id)

        for role_id in temp_data[user_id]:
            role = interaction.guild.get_role(role_id)
            if not role:
                continue
                
            if member_role and role.position < member_role.position:
                continue
                
            if role not in member.roles:
                roles_to_add.append(role)

        if not roles_to_add:
            # Clean up data if no roles could be added
            del temp_data[user_id]
            save_temp_roles(temp_data)
            await interaction.response.send_message("❌ You have already received all your saved roles back.", ephemeral=True)
            return

        embed = discord.Embed(color=discord.Color.orange(), title="⏳ Restoring Roles...")
        embed.description = f"🛠️ Restoring **{len(roles_to_add)}** roles to {member.mention} in the background..."
        await interaction.response.send_message(embed=embed)

        async def process_restore():
            try:
                await member.add_roles(*roles_to_add, reason="Temp (Restore) command triggered")
                
                # Delete role from storage
                del temp_data[user_id]
                save_temp_roles(temp_data)

                role_mentions = ", ".join([r.mention for r in roles_to_add])
                if len(role_mentions) > 3900:
                    role_mentions = role_mentions[:3900] + "... and more."
                
                embed.title = "✅ Roles Restored"
                embed.color = discord.Color.blue()
                embed.description = f"🛠️ Restored **{len(roles_to_add)}** role(s) to {member.mention}:\n\n{role_mentions}"
                await interaction.edit_original_response(embed=embed)
            except discord.Forbidden:
                embed.title = "❌ Error"
                embed.color = discord.Color.red()
                embed.description = f"I lack the permissions to assign roles to {member.mention}."
                await interaction.edit_original_response(embed=embed)

        bot.loop.create_task(process_restore())

    # IF USER HAS NO SAVED ROLES -> REMOVE (REMOVE MODE)
    else:
        roles_to_remove = []
        protected_roles = [1545265096484458527, 1545265093489463337] # Member and Giveaway roles
        saved_role_ids = []
        
        for role in member.roles:
            if role.name == "@everyone" or role.managed or role.id in protected_roles or role >= interaction.guild.me.top_role:
                continue
            
            roles_to_remove.append(role)
            saved_role_ids.append(role.id)
            
        if not roles_to_remove:
            await interaction.response.send_message("❌ No removable roles found on your profile.", ephemeral=True)
            return

        # Save roles
        temp_data[user_id] = saved_role_ids
        save_temp_roles(temp_data)

        embed = discord.Embed(color=discord.Color.orange(), title="⏳ Removing Roles...")
        embed.description = f"🛠️ Removing **{len(roles_to_remove)}** roles from {member.mention} in the background..."
        await interaction.response.send_message(embed=embed)

        async def process_temp_remove():
            try:
                await member.remove_roles(*roles_to_remove, reason="Temp (Remove) command triggered")
                
                role_mentions = ", ".join([r.mention for r in roles_to_remove])
                if len(role_mentions) > 3900:
                    role_mentions = role_mentions[:3900] + "... and more."
                
                embed.title = "✅ Roles Removed"
                embed.color = discord.Color.red()
                embed.description = f"🛠️ Removed **{len(roles_to_remove)}** role(s) from {member.mention}:\n\n{role_mentions}"
                await interaction.edit_original_response(embed=embed)
            except discord.Forbidden:
                embed.title = "❌ Error"
                embed.color = discord.Color.red()
                embed.description = f"I lack the permissions to remove roles from {member.mention}."
                await interaction.edit_original_response(embed=embed)

        bot.loop.create_task(process_temp_remove())


# --- 9. Start ---
keep_alive()
token = os.environ.get("DISCORD_TOKEN")
bot.run(token)
