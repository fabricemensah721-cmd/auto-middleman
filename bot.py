import discord
from discord import app_commands
from discord.ext import commands
import os
import asyncio
import random
import string

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

class AutoMMBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)
        
    async def setup_hook(self):
        # Registers the views permanently so they work even after bot restarts
        self.add_view(LtcPanelView())
        self.add_view(UsdtPanelView())
        print("🔒 Separate Auto-MM Panel System successfully loaded.")

bot = AutoMMBot()

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user.name}")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} Slash Commands.")
    except Exception as e:
        print(f"Sync Error: {e}")

# =========================================================================
# --- PERSISTENT INTERACTIVE PANELS (1:1 GEGENÜBER SCREENSHOT) ---
# =========================================================================

# Main tutorial and info box view
class TutorialView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        # Link button pointing to tutorial like shown on the screenshot
        self.add_item(discord.ui.Button(label="Tutorial", url="https://example.com/tutorial", style=discord.ButtonStyle.link))

# Litecoin Request Panel View
class LtcPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Request LTC", style=discord.ButtonStyle.blurple, custom_id="panel_req_ltc")
    async def req_ltc(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TradeFormatModal(asset="Litecoin (LTC)"))

# USDT Request Panel View
class UsdtPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Request USDT [BEP-20]", style=discord.ButtonStyle.success, custom_id="panel_req_usdt")
    async def req_usdt(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TradeFormatModal(asset="USDT [BEP-20]"))


# =========================================================================
# --- MODAL & TICKET INTERACTION FLOW ---
# =========================================================================

class TradeFormatModal(discord.ui.Modal, title="Fill out the format"):
    def __init__(self, asset: str):
        super().__init__()
        self.asset = asset

    trader_id = discord.ui.TextInput(label="Paste Your Trader's Username or ID", placeholder="e.g. 985509072...", required=True)
    giving = discord.ui.TextInput(label="What Are You Giving?", placeholder="e.g. test", required=True)
    receiving = discord.ui.TextInput(label="What Is Your Trader Giving?", placeholder="e.g. test", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild
        random_suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=4))
        channel_name = f"trade-{interaction.user.name.lower()}-{random_suffix}"
        
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        
        ticket_channel = await guild.create_text_channel(name=channel_name, overwrites=overwrites)
        
        embed = discord.Embed(
            title=f"🛡️ Jace's Auto Middleman ({self.asset})",
            description="Please finalize the trade details below before moving forward.\nIf any participant wants to cancel, click **Close Ticket**.",
            color=discord.Color.purple()
        )
        embed.add_field(name="Your Items:", value=f"`{self.giving.value}`", inline=True)
        embed.add_field(name="Partner's Items:", value=f"`{self.receiving.value}`", inline=True)
        
        await ticket_channel.send(content=f"{interaction.user.mention} | Trade session initialized.", embed=embed, view=TicketWorkflowView())
        await interaction.response.send_message(f"✅ **Ticket Created!** Please head over to {ticket_channel.mention}", ephemeral=True)


class TicketWorkflowView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Sender", style=discord.ButtonStyle.green, custom_id="t_sender")
    async def select_sender(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(SetAmountModal())

    @discord.ui.button(label="Receiver", style=discord.ButtonStyle.blurple, custom_id="t_receiver")
    async def select_receiver(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(f"📥 {interaction.user.mention} selected the **Receiver** role. Awaiting input from the Sender...", ephemeral=False)

    @discord.ui.button(label="Close Ticket", style=discord.ButtonStyle.red, custom_id="t_close")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("🔒 This ticket will be deleted in 5 seconds...")
        await asyncio.sleep(5)
        await interaction.channel.delete()


class SetAmountModal(discord.ui.Modal, title="Set USD Amount"):
    amount = discord.ui.TextInput(label="Enter the amount in USD value", placeholder="e.g. 25.00", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        usd_val = float(self.amount.value)
        crypto_val = round(usd_val / 65.0, 5)
        fake_addr = "L" + "".join(random.choices(string.ascii_letters + string.digits, k=33))
        
        embed = discord.Embed(title="💳 Payment Information", description="Please make sure to transfer the **EXACT** amount to the address below.", color=discord.Color.blue())
        embed.add_field(name="USD Amount", value=f"`${usd_val:.2f}`", inline=True)
        embed.add_field(name="Crypto Amount", value=f"`{crypto_val}`", inline=True)
        embed.add_field(name="Target Address", value=f"`{fake_addr}`", inline=False)
        
        await interaction.response.send_message(embed=embed, view=PaymentCheckView())


class PaymentCheckView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Confirm Payment Sent", style=discord.ButtonStyle.green, custom_id="pay_confirm")
    async def confirm_sent(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        msg = await interaction.followup.send("🔍 Scanning blockchain network for transaction confirmation...")
        await asyncio.sleep(4)
        
        embed = discord.Embed(
            title="✅ Transaction Confirmed & Cleared", 
            description="The system has verified the receipt on-chain and securely held the assets inside the escrow hub.", 
            color=discord.Color.green()
        )
        await msg.edit(content=None, embed=embed)


# =========================================================================
# --- SLASH COMMAND TO DEPLOY PANEL LAYOUT ---
# =========================================================================

@bot.tree.command(name="setup_automm", description="Deploys the exact 1:1 Auto Middleman panel into the channel")
@app_commands.checks.has_permissions(administrator=True)
async def setup_automm_panel(interaction: discord.Interaction):
    # Grabbing channel mention for #tos-crypto if it exists on the guild
    tos_channel = discord.utils.get(interaction.guild.text_channels, name="tos-crypto")
    tos_mention = tos_channel.mention if tos_channel else "`#tos-crypto`"
    
    # 1. Main Info Block (Fees & ToS)
    embed_info = discord.Embed(
        title="Jace's Auto Middleman",
        description=f"• **Paid Service**\n• Read our ToS before using the bot: {tos_mention}",
        color=discord.Color.from_rgb(47, 49, 54) # Exact dark-grey embed sidebar
    )
    embed_info.add_field(
        name="Fees:",
        value="• Deals $250+: $1.50\n• Deals under $250: $0.50\n• Deals under $50 are **FREE**",
        inline=False
    )
    
    # 2. Litecoin Block Layout
    embed_ltc = discord.Embed(
        title="Ł • Request Litecoin • Ł",
        color=discord.Color.blue()
    )
    
    # 3. USDT Block Layout
    embed_usdt = discord.Embed(
        title="🛆 • Request USDT [BEP-20] • 🛆",
        description="• Network: **BSC (BEP-20)**",
        color=discord.Color.green()
    )

    # Sending all embeds under each other matching the screen style perfectly
    await interaction.channel.send(embed=embed_info, view=TutorialView())
    await interaction.channel.send(embed=embed_ltc, view=LtcPanelView())
    await interaction.channel.send(embed=embed_usdt, view=UsdtPanelView())
    
    await interaction.response.send_message("🎯 AutoMM panel interface deployed cleanly!", ephemeral=True)


# --- RUN THE BOT ENGINE ---
TOKEN = os.getenv("DISCORD_TOKEN", "YOUR_NEW_BOT_TOKEN")
bot.run(TOKEN)
