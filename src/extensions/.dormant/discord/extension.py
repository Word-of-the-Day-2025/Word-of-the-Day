import asyncio
import colorama
import datetime
from dateutil import tz
import discord
from discord.ext import commands
from dotenv import load_dotenv
import json
import math
import os
import pytz
import re
import shlex
import sqlite3
import threading

from databases import add_word, WORDS_DB
from .subscribers import is_subscribed_discord_guild, is_subscribed_discord_private, subscribe_discord, unsubscribe_discord, SUBSCRIBERS_DB
from wotd import query_queued, query_wotd


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ADMINS_JSON = os.path.join(BASE_DIR, 'admins.json')

# Get the list of admins who are allowed to use special commands from the json file
with open(ADMINS_JSON, 'r') as f:
    ADMINS = json.load(f)
ADMINS = set(ADMINS['admins'])  # Reusing the variable here

# Load the bot token
DOTENV_PATH = os.path.join(BASE_DIR, '.env')
load_dotenv(DOTENV_PATH)
TOKEN = os.getenv('DISCORD_TOKEN')

# Create a bot instance
intents = discord.Intents.default()
intents.message_content = True
client = commands.Bot(command_prefix='! ', intents=intents)
client.remove_command('help')

# TODO: Make all commands slash commands

subscribe_private_embed = discord.Embed(
    title='<:steamhappy:1322121693510242314> **Subscribed** to Word of the Day!',
    description='''You will now receive the Word of the Day every day at <t:0:t>.
    To configure settings, send `! config`.
    To unsubscribe, send `! unsubscribe`.''',
    color=discord.Color.gold()
)
subscribe_guild_embed = discord.Embed(
    title='<:steamhappy:1322121693510242314> **Subscribed** to Word of the Day!',
    description='''This channel will now receive the Word of the Day every day at <t:0:t>.
    To configure settings, send `! config`.
    To unsubscribe, send `! unsubscribe`.''',
    color=discord.Color.gold()
)
unsubscribe_private_embed = discord.Embed(
    title='<:steamsad:1322121721649561682> **Unsubscribed** from Word of the Day.',
    description='''You will no longer receive the Word of the Day.
    To subscribe again, send `! subscribe`.''',
    color=discord.Color.blue()
)
unsubscribe_guild_embed = discord.Embed(
    title='<:steamsad:1322121721649561682> **Unsubscribed** from Word of the Day.',
    description='''This channel will no longer receive the Word of the Day.
    To subscribe again, send `! subscribe`.''',
    color=discord.Color.blue()
)
subscribed_already_private_embed = discord.Embed(
    title='<:steamdance:1322121672224145438> You\'re already subscribed!',
    description='''You are already subscribed to the Word of the Day.
    To configure settings, send `! config`.
    To unsubscribe, send `! unsubscribe`.''',
    color=discord.Color.pink()
)
subscribed_already_guild_embed = discord.Embed(
    title='<:steamdance:1322121672224145438> This channel is already subscribed!',
    description='''This channel is already subscribed to the Word of the Day.
    To configure settings, send `! config`.
    To unsubscribe, send `! unsubscribe`.''',
    color=discord.Color.pink()
)
unsubscribed_already_private_embed = discord.Embed(
    title='<:steamdeadpan:1322121678712737872> You\'re already unsubscribed.',
    description='''You are already unsubscribed from the Word of the Day.
    To subscribe again, send `! subscribe`.''',
    color=discord.Color.dark_purple()
)
unsubscribed_already_guild_embed = discord.Embed(
    title='<:steamdeadpan:1322121678712737872> This channel is already unsubscribed.',
    description='''This channel is already unsubscribed from the Word of the Day.
    To subscribe again, send `! subscribe`.''',
    color=discord.Color.dark_purple()
)

@client.event
async def on_ready():
    client.loop.create_task(update_activity())
    client.loop.create_task(send_wotd())

async def unsubscribe_button_callback(interaction: discord.Interaction):
    if interaction.channel.type == discord.ChannelType.private:
        if is_subscribed_discord_private(interaction.user.id):
            unsubscribe_discord('private', interaction.user.id)
            await interaction.response.send_message(embed=unsubscribe_private_embed)
        else:
            await interaction.response.send_message(embed=unsubscribed_already_private_embed)
    elif interaction.user.guild_permissions.administrator:
        if is_subscribed_discord_guild(interaction.guild.id, interaction.channel.id):
            unsubscribe_discord('guild', None, interaction.guild.id, interaction.channel.id)
            await interaction.response.send_message(embed=unsubscribe_guild_embed)
        else:
            await interaction.response.send_message(embed=unsubscribed_already_guild_embed)
    else:
        await interaction.response.send_message('You do not have permission to do this.', ephemeral=True)

# Define the callback for the configure button
async def configure_button_callback(interaction: discord.Interaction):
    if not interaction.channel.type == discord.ChannelType.private and not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message('You do not have permission to do this.', ephemeral=True)
    await interaction.response.send_message('Configuration options will be available soon.')

@client.command()
async def subscribe(ctx):
    '''Subscribe to the Word of the Day.'''

    if ctx.channel.type == discord.ChannelType.private:  # If the command was sent in a DM
        await ctx.channel.typing()  # Show that the bot is typing
        if is_subscribed_discord_private(ctx.author.id):
            embed = subscribed_already_private_embed
        else:
            subscribe_discord('private', ctx.author.id, None, None, '00:00', 'MDY')
            embed = subscribe_private_embed
    elif ctx.channel.type == discord.ChannelType.text or ctx.channel.type == discord.ChannelType.news:  # If the command was sent in a guild
        if not ctx.author.guild_permissions.administrator:
            return
        await ctx.channel.typing()  # Show that the bot is typing
        if is_subscribed_discord_guild(ctx.guild.id, ctx.channel.id):
            embed = subscribed_already_guild_embed
        else:
            subscribe_discord('guild', None, ctx.guild.id, ctx.channel.id, '00:00', 'MDY')
            embed = subscribe_guild_embed
    else:
        return

    view = discord.ui.View()
    unsubscribe_button = discord.ui.Button(
        style=discord.ButtonStyle.gray,
        label='Unsubscribe',
        custom_id='unsubscribe',
    )
    configure_button = discord.ui.Button(
        style=discord.ButtonStyle.gray,
        label='Configure',
        custom_id='configure',
    )
    unsubscribe_button.callback = unsubscribe_button_callback
    view.add_item(unsubscribe_button)
    configure_button.callback = configure_button_callback
    view.add_item(configure_button)

    await ctx.send(embed=embed, view=view)

@client.command()
async def unsubscribe(ctx):
    '''Unsubscribe from the Word of the Day.'''

    if ctx.channel.type == discord.ChannelType.private:
        await ctx.channel.typing()  # Show that the bot is typing
        if not is_subscribed_discord_private(ctx.author.id):
            await ctx.send(embed=unsubscribed_already_private_embed)
        else:
            unsubscribe_discord('private', ctx.author.id, None, None)
            await ctx.send(embed=unsubscribe_private_embed)
    elif ctx.channel.type == discord.ChannelType.text or ctx.channel.type == discord.ChannelType.news:
        if not ctx.author.guild_permissions.administrator:
            return
        await ctx.channel.typing()  # Show that the bot is typing
        if not is_subscribed_discord_guild(ctx.guild.id, ctx.channel.id):
            await ctx.send(embed=unsubscribed_already_guild_embed)
        else:
            unsubscribe_discord('guild', None, ctx.guild.id, ctx.channel.id)
            await ctx.send(embed=unsubscribe_guild_embed)
    else:
        return

@client.command()
async def query(ctx):
    '''Send the Word of the Day to the user.'''

    # Query the word of the day
    word, ipa, type, definition, date = query_wotd()

    # If the word of the day has not been set yet, return
    if not word:
        await ctx.send('The Word of the Day has not been set yet.')
        return

    # Send the Word of the Day to every subscriber
    date = date.split('-')
    month = date[1]
    month = datetime.date(2000, int(month), 1).strftime('%B')  # Convert the month number to the month name
    day = date[0].lstrip('0')
    year = date[2]
    if day[-1] == '1' and day != '11':
        day += 'st'
    elif day[-1] == '2' and day != '12':
        day += 'nd'
    elif day[-1] == '3' and day != '13':
        day += 'rd'
    else:
        day += 'th'
    date = f'{month} {day}, {year}'
    message = f'Today is {date}, and the Word of the Day is "{word}" ({ipa}), which is defined as: ({type}) {definition}'

    # Send the message to the user
    await ctx.send(message)
    

@client.command()
async def config(ctx):
    '''Configure the Word of the Day settings.'''

    await ctx.channel.typing()  # Show that the bot is typing
    await ctx.send('Configuration options will be available soon.')

@client.command()
async def nuke(ctx):
    if ctx.author.id not in ADMINS:
        return
    else:
        # Delete all messages in the channel sent by the bot
        async for message in ctx.channel.history(limit=None):
            if message.author == client.user:
                await message.delete()

@client.command()
async def append(ctx, *, args: str):
    '''Append a word to the database.'''

    if ctx.author.id not in ADMINS:
        return

    # Regular expression to match arguments surrounded by quotes
    pattern = r'(["\'])(?:(?=(\\?))\2.)*?\1'
    matches = re.findall(pattern, args)

    if len(matches) != 4:
        await ctx.send('Invalid arguments. Please provide the word, IPA, type, and definition surrounded by quotes.')
        return

    lexer = shlex.shlex(args, posix=True)
    lexer.whitespace_split = True
    lexer.quotes = '"\''
    lexer.escapedquotes = '"\''
    word, ipa, type, definition = list(lexer)
    print(word, ipa, type, definition)

    # Check for if the word already exists in the database
    conn = sqlite3.connect(WORDS_DB)
    c = conn.cursor()
    c.execute('SELECT * FROM words WHERE word = ?', (word,))
    if c.fetchone():
        await ctx.send(f'The word "{word}" already exists in the database.')
        return
    conn.close()

    # Append the word to the database
    add_word(word, ipa, type, definition, False)

    # Inform the user that the word was successfully appended
    await ctx.send(f'''
The word "{word}" has been successfully appended to the database:
- Word: {word}
- IPA: {ipa}
- Type: {type}
- Definition: {definition}
    ''')

@client.command()
async def query_next(ctx):
    '''Query the next word in the queue.'''

    if ctx.author.id not in ADMINS:
        return

    queued_word, queued_ipa, queued_type, queued_definition, queued_date = query_queued()
    await ctx.send(f'The next word in the queue is "{queued_word}" ({queued_ipa}), which is defined as: ({queued_type}) {queued_definition}')

async def update_activity():
    while True:
        await client.wait_until_ready()  # Wait for the bot to be ready

        # Calculate current time and PST timezone
        now = datetime.datetime.now(datetime.timezone.utc)
        pst = datetime.timezone(datetime.timedelta(hours=-8))

        # Determine the next 8:00 AM PST
        current_pst = now.astimezone(pst)
        next_8am_pst = current_pst.replace(hour=8, minute=0, second=0, microsecond=0)
        if current_pst >= next_8am_pst:
            next_8am_pst += datetime.timedelta(days=1)

        # Calculate the sleep duration until the next minute and the total duration until 8:00 AM PST
        sleep_duration = (next_8am_pst - now).total_seconds()
        countdown = math.ceil(sleep_duration / 60)
        countdown = '{:,}'.format(countdown)
        if countdown == '1':
            activity_state = f'Next word in {countdown} minute.'
        elif countdown == '1,440':
            activity_state = f'Word of the Day: {query_queued()[0]}'
        else:
            activity_state = f'Next word in {countdown} minutes.'
        activity = discord.Activity(
            name='WOTD',
            type=discord.ActivityType.custom,
            state=activity_state
        )
        await client.change_presence(activity=activity)  # Update the bot's activity status

        # Sleep until the next second is 00
        await asyncio.sleep(60 - now.second)

async def send_wotd():
    '''Send the Word of the Day to every subscriber.'''

    while True:
        await client.wait_until_ready()  # Wait for the bot to be ready

        # Wait for 8:00 AM PST
        now = datetime.datetime.now(datetime.timezone.utc)
        pst = tz.gettz('America/Los_Angeles')
        current_pst = now.astimezone(pst)
        next_8am_pst = current_pst.replace(hour=8, minute=0, second=0, microsecond=0)
        if current_pst >= next_8am_pst:
            next_8am_pst += datetime.timedelta(days=1)
        sleep_duration = (next_8am_pst - now).total_seconds()
        await asyncio.sleep(sleep_duration)

        # Query the word of the day
        queued_word, queued_ipa, queued_type, queued_definition, queued_date = query_queued()

        # Send the Word of the Day to every subscriber
        utc_now = datetime.datetime.now(pytz.utc)
        month = utc_now.strftime('%B')
        day = utc_now.strftime('%d').lstrip('0')
        year = utc_now.strftime('%Y')
        if day[-1] == '1' and day != '11':
            day += 'st'
        elif day[-1] == '2' and day != '12':
            day += 'nd'
        elif day[-1] == '3' and day != '13':
            day += 'rd'
        else:
            day += 'th'
        date = f'{month} {day}, {year}'
        message = f'Today is {date}, and the Word of the Day is "{queued_word}" ({queued_ipa}), which is defined as: ({queued_type}) {queued_definition}'

        conn = sqlite3.connect(SUBSCRIBERS_DB)
        c = conn.cursor()
        c.execute('SELECT * FROM subscribers')
        subscribers = c.fetchall()
        conn.close()
        for subscriber in subscribers:
            try:
                if subscriber[1] == 'private':
                    user = await client.fetch_user(subscriber[2])
                    dm_channel = await user.create_dm()
                    await dm_channel.send(message)
                elif subscriber[1] == 'guild':
                    guild = client.get_guild(subscriber[3])
                    channel = guild.get_channel(subscriber[4])
                    await channel.send(message)
            except:  # Catch all exceptions
                await asyncio.sleep(5)
                # Retry sending the message
                if subscriber[1] == 'private':
                    user = await client.fetch_user(subscriber[2])
                    dm_channel = await user.create_dm()
                    await dm_channel.send(message)
                elif subscriber[1] == 'guild':
                    guild = client.get_guild(subscriber[3])
                    channel = guild.get_channel(subscriber[4])
                    await channel.send(message)
            '''
            except discord.HTTPException as e:
                if e.code == 40003:
                    retry_after = e.retry_after if hasattr(e, 'retry_after') else 5
                    await asyncio.sleep(retry_after)
                    # Retry sending the message
                    if subscriber[1] == 'private':
                        user = await client.fetch_user(subscriber[2])
                        dm_channel = await user.create_dm()
                        await dm_channel.send(message)
                    elif subscriber[1] == 'guild':
                        guild = client.get_guild(subscriber[3])
                        channel = guild.get_channel(subscriber[4])
                        await channel.send(message)
                else:
                    print(e)
            '''

def run_client():
    client.run(TOKEN)

client_thread = threading.Thread(target=run_client)
client_thread.daemon = True
client_thread.start()