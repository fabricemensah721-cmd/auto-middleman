import os
from flask import Flask
from threading import Thread
import discord
from discord.ext import commands

# 1. Setup Web Server for Render
app = Flask('')

@app.route('/')
def home():
    return "Bot is online!"

def run():
    # Gets the port from Render or uses 8080 as default
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.start()

# 2. Setup Discord Bot
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}')

# Your Mercy Command
@bot.command()
async def mercy(ctx):
    await ctx.send("Mercy comes to the rescue!")

# 3. Start the Bot
keep_alive()
# Safely fetches your token from Render's Environment Variables
token = os.environ.get("DISCORD_TOKEN")
bot.run(token)

