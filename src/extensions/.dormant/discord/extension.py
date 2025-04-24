import asyncio
import colorama
import datetime
from dateutil import tz
import discord
from discord import app_commands
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
from .subscribers import is_subscribed_guild, is_subscribed_private, subscribe_discord, unsubscribe_discord, SUBSCRIBERS_DB
from wotd import query_queued, query_wotd, word, ipa, type, definition, date

colorama.init()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_JSON = os.path.join(BASE_DIR, 'config.json')
RATE_LIMIT = 45  # Requests allowed per second (slightly below the 50 requests per second limit)
semaphore = asyncio.Semaphore(RATE_LIMIT)
send_wotd_count = 0

# Get the list of admins who are allowed to use special commands from the json file
with open(CONFIG_JSON, 'r') as f:
    CONFIG_JSON = json.load(f)  # Reusing the variable lol
ADMINS = set(CONFIG_JSON['admins'])
MAX_SUBSCRIPTIONS_PER_GUILD = CONFIG_JSON['maxSubscriptionsPerGuild']

# Load the bot token
DOTENV_PATH = os.path.join(BASE_DIR, '.env')
load_dotenv(DOTENV_PATH)
TOKEN = os.getenv('DISCORD_TOKEN')

# Create a bot instance
intents = discord.Intents.default()
intents.message_content = True
client = commands.Bot(command_prefix='! ', intents=intents)
client.remove_command('help')

subscribe_private_embed = discord.Embed(
    title='<:steamhappy:1322121693510242314> **Subscribed** to Word of the Day!',
    description='''You will now receive the Word of the Day every day at <t:0:t>.
    To configure settings, send `/config`.
    To unsubscribe, send `/unsubscribe`.''',
    color=discord.Color.gold()
)
subscribe_guild_embed = discord.Embed(
    title='<:steamhappy:1322121693510242314> **Subscribed** to Word of the Day!',
    description='''This channel will now receive the Word of the Day every day at <t:0:t>.
    To configure settings, send `/config`.
    To unsubscribe, send `/unsubscribe`.''',
    color=discord.Color.gold()
)
unsubscribe_private_embed = discord.Embed(
    title='<:steamsad:1322121721649561682> **Unsubscribed** from Word of the Day.',
    description='''You will no longer receive the Word of the Day.
    To subscribe again, send `/subscribe`.''',
    color=discord.Color.blue()
)
unsubscribe_guild_embed = discord.Embed(
    title='<:steamsad:1322121721649561682> **Unsubscribed** from Word of the Day.',
    description='''This channel will no longer receive the Word of the Day.
    To subscribe again, send `/subscribe`.''',
    color=discord.Color.blue()
)
subscribed_already_private_embed = discord.Embed(
    title='<:steamdance:1322121672224145438> You\'re already subscribed!',
    description='''You are already subscribed to the Word of the Day.
    To configure settings, send `/config`.
    To unsubscribe, send `/unsubscribe`.''',
    color=discord.Color.pink()
)
subscribed_already_guild_embed = discord.Embed(
    title='<:steamdance:1322121672224145438> This channel is already subscribed!',
    description='''This channel is already subscribed to the Word of the Day.
    To configure settings, send `/config`.
    To unsubscribe, send `/unsubscribe`.''',
    color=discord.Color.pink()
)
unsubscribed_already_private_embed = discord.Embed(
    title='<:steamdeadpan:1322121678712737872> You\'re already unsubscribed.',
    description='''You are already unsubscribed from the Word of the Day.
    To subscribe again, send `/subscribe`.''',
    color=discord.Color.dark_purple()
)
unsubscribed_already_guild_embed = discord.Embed(
    title='<:steamdeadpan:1322121678712737872> This channel is already unsubscribed.',
    description='''This channel is already unsubscribed from the Word of the Day.
    To subscribe again, send `/subscribe`.''',
    color=discord.Color.dark_purple()
)

@client.event
async def on_ready():
    await client.tree.sync()  # Sync the slash commands
    client.loop.create_task(update_activity())
    client.loop.create_task(send_wotd())

async def unsubscribe_button_callback(interaction: discord.Interaction):
    if interaction.channel.type == discord.ChannelType.private:
        if is_subscribed_private(interaction.user.id):
            unsubscribe_discord('private', interaction.user.id)
            await interaction.response.send_message(embed=unsubscribe_private_embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=unsubscribed_already_private_embed, ephemeral=True)
    elif interaction.user.guild_permissions.administrator:
        if is_subscribed_guild(interaction.guild.id, interaction.channel.id):
            unsubscribe_discord('guild', None, interaction.guild.id, interaction.channel.id)
            await interaction.response.send_message(embed=unsubscribe_guild_embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=unsubscribed_already_guild_embed, ephemeral=True)
    else:
        await interaction.response.send_message('You do not have permission to do this.', ephemeral=True)

async def subscribe_button_callback(interaction: discord.Interaction):
    if interaction.channel.type == discord.ChannelType.private:
        if is_subscribed_private(interaction.user.id):
            await interaction.response.send_message(embed=subscribed_already_private_embed, ephemeral=True)
        else:
            subscribe_discord('private', interaction.user.id, None, None, '00:00', 'MDY')
            await interaction.response.send_message(embed=subscribe_private_embed, ephemeral=True)
    elif interaction.user.guild_permissions.administrator:
        if is_subscribed_guild(interaction.guild.id, interaction.channel.id):
            await interaction.response.send_message(embed=subscribed_already_guild_embed, ephemeral=True)
        else:
            subscribe_discord('guild', None, interaction.guild.id, interaction.channel.id, '00:00', 'MDY')
            await interaction.response.send_message(embed=subscribe_guild_embed, ephemeral=True)
    else:
        await interaction.response.send_message('You do not have permission to do this.', ephemeral=True)

# Define the callback for the configure button
async def configure_button_callback(interaction: discord.Interaction):
    if not interaction.channel.type == discord.ChannelType.private and not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message('You do not have permission to do this.', ephemeral=True)
    await interaction.response.send_message('Configuration options will be available soon.', ephemeral=True)

@client.tree.command(name='subscribe', description='Subscribe to the Word of the Day.')
async def subscribe(interaction: discord.Interaction):
    if interaction.channel.type == discord.ChannelType.private:  # If the command was sent in a DM
        if is_subscribed_private(interaction.user.id):
            embed = subscribed_already_private_embed
        else:
            subscribe_discord('private', interaction.user.id, None, None, '00:00', 'MDY')
            embed = subscribe_private_embed
    elif interaction.channel.type == discord.ChannelType.text or interaction.channel.type == discord.ChannelType.news:  # If the command was sent in a guild
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message('You do not have permission to do this.', ephemeral=True)
            return
        if is_subscribed_guild(interaction.guild.id, interaction.channel.id):
            embed = subscribed_already_guild_embed
        else:
            # Check if the guild has reached the maximum number of channels subscribed to the Word of the Day
            conn = sqlite3.connect(SUBSCRIBERS_DB)
            c = conn.cursor()
            c.execute('SELECT * FROM subscribers WHERE guild_id = ?', (interaction.guild.id,))
            channels = c.fetchall()
            conn.close()
            if len(channels) >= MAX_SUBSCRIPTIONS_PER_GUILD:
                await interaction.response.send_message('This server has reached the maximum number of channels subscribed to the Word of the Day.', ephemeral=True)
                return
            subscribe_discord('guild', None, interaction.guild.id, interaction.channel.id, '00:00', 'MDY')
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

    if interaction.channel.type == discord.ChannelType.private or interaction.channel.type == discord.ChannelType.text or interaction.channel.type == discord.ChannelType.news:
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    else:
        await interaction.response.send_message(f'You cannot use this command in a {interaction.channel.type} channel.', ephemeral=True)

@client.tree.command(name='unsubscribe', description='Unsubscribe from the Word of the Day.')
async def unsubscribe(interaction: discord.Interaction):
    if interaction.channel.type == discord.ChannelType.private:  # If the command was sent in a DM
        if not is_subscribed_private(interaction.user.id):
            embed = unsubscribed_already_private_embed
        else:
            unsubscribe_discord('private', interaction.user.id, None, None)
            embed = unsubscribe_private_embed
    elif interaction.channel.type == discord.ChannelType.text or interaction.channel.type == discord.ChannelType.news:  # If the command was sent in a guild
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message('You do not have permission to do this.', ephemeral=True)
            return
        if not is_subscribed_guild(interaction.guild.id, interaction.channel.id):
            embed = unsubscribed_already_guild_embed
        else:
            unsubscribe_discord('guild', None, interaction.guild.id, interaction.channel.id)
            embed = unsubscribe_guild_embed
    else:
        return

    view = discord.ui.View()
    subscribe_button = discord.ui.Button(
        style=discord.ButtonStyle.gray,
        label='Subscribe',
        custom_id='subscribe',
    )
    subscribe_button.callback = subscribe_button_callback
    view.add_item(subscribe_button)

    if interaction.channel.type == discord.ChannelType.private or interaction.channel.type == discord.ChannelType.text or interaction.channel.type == discord.ChannelType.news:
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    else:
        await interaction.response.send_message(f'You cannot use this command in a {interaction.channel.type} channel.', ephemeral=True)

@client.tree.command(name='query', description='Query the current Word of the Day.')
async def query(interaction: discord.Interaction):
    # Query the word of the day
    word, ipa, type, definition, date = query_wotd()

    # If the word of the day has not been set yet, return
    if not word:
        await interaction.response.send_message('The Word of the Day has not been set yet.', ephemeral=True)
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

    await interaction.response.send_message(message, ephemeral=True)

@client.tree.command(name='config', description='Configure your Word of the Day settings.')
async def config(interaction: discord.Interaction):
    await interaction.response.send_message('Configuration options will be available soon.', ephemeral=True)

# Commands for bot administrators use prefix commands instead of slash commands

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
async def set_wotd(ctx, *, args: str):
    '''Set the Word of the Day.'''

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
    new_word, new_ipa, new_type, new_definition = list(lexer)
    print(new_word, new_ipa, new_type, new_definition)

    # Set the word of the day variables in wotd.py
    global word, ipa, type, definition, date
    word = new_word
    ipa = new_ipa
    type = new_type
    definition = new_definition

    # Inform the user that the word was successfully set
    await ctx.send(f'The Word of the Day has been successfully set to "{new_word}" ({new_ipa}), which is defined as: ({new_type}) {new_definition}')

@client.command()
async def query_next(ctx):
    '''Query the next word in the queue.'''

    if ctx.author.id not in ADMINS:
        return

    queued_word, queued_ipa, queued_type, queued_definition, queued_date = query_queued()
    if not queued_word:
        await ctx.send('The next Word of the Day has not been set yet.')
        return
    else:
        message = f'The next word in the queue is "{queued_word}" ({queued_ipa}), which is defined as: ({queued_type}) {queued_definition}'
    await ctx.send(message)

@client.command()
async def send_all(ctx):
    '''Send a test message to all subscribers.'''

    if ctx.author.id not in ADMINS:
        return

    message = 'This is a test message.'
    conn = sqlite3.connect(SUBSCRIBERS_DB)
    c = conn.cursor()
    c.execute('SELECT * FROM subscribers')
    subscribers = c.fetchall()
    conn.close()
    sent_places = []  # This is the solution to the problem of the bot sending the same message multiple times
    async with semaphore:
        for subscriber in subscribers:
            if subscriber in sent_places:
                continue
            if subscriber[1] == 'private':
                try:
                    print(colorama.Fore.GREEN + f'Sending message to user {subscriber[2]}' + colorama.Style.RESET_ALL)
                    user = await client.fetch_user(subscriber[2])
                    dm_channel = await user.create_dm()
                    await dm_channel.send(message)
                    sent_places.append(subscriber)
                except discord.errors.Forbidden:
                    # The user blocked the bot, disabled DMs, or is no longer in the same guild
                    print(colorama.Fore.RED + f'Unsubscribing user {subscriber[2]} due to Forbidden error' + colorama.Style.RESET_ALL)
                    unsubscribe_discord('private', subscriber[2])
                    continue
                except discord.errors.NotFound:
                    # The user no longer exists
                    print(colorama.Fore.RED + f'Unsubscribing user {subscriber[2]} due to not existing' + colorama.Style.RESET_ALL)
                    unsubscribe_discord('private', subscriber[2])
                    continue
                except discord.errors.RateLimited:
                    # Sleep for 1 second and try again
                    retry_after = getattr(e, 'retry_after', None)
                    print(colorama.Fore.YELLOW + f'Sleeping for {retry_after} seconds' + colorama.Style.RESET_ALL)
                    if retry_after:
                        await asyncio.sleep(retry_after)
                        try:
                            await channel.send(message)  # Retry sending message
                        except Exception as e:
                            # Skip the user if an error occurs again
                            continue
                except Exception as e:
                    # Skip the user if an error occurs
                    continue
            elif subscriber[1] == 'guild':
                # Guild subscribers in sent_places are "{guild_id}/{channel_id}"
                if f'{subscriber[3]}/{subscriber[4]}' in sent_places:
                    continue
                if not client.get_guild(subscriber[3]):
                    # The guild no longer exists
                    print(colorama.Fore.RED + f'Unsubscribing guild {subscriber[3]} due to not existing' + colorama.Style.RESET_ALL)
                    unsubscribe_discord('guild', None, subscriber[3])
                    continue
                if not client.get_guild(subscriber[3]).get_channel(subscriber[4]):
                    # The channel no longer exists
                    print(colorama.Fore.RED + f'Unsubscribing guild {subscriber[3]} due to channel {subscriber[4]} not existing' + colorama.Style.RESET_ALL)
                    unsubscribe_discord('guild', None, subscriber[3], subscriber[4])
                    continue
                try:
                    print(colorama.Fore.GREEN + f'Sending message to guild {subscriber[3]}' + colorama.Style.RESET_ALL)
                    guild = client.get_guild(subscriber[3])
                    channel = guild.get_channel(subscriber[4])
                    await channel.send(message)
                    sent_places.append(f'{subscriber[3]}/{subscriber[4]}')
                except discord.errors.NotFound:
                    # The guild no longer exists
                    print(colorama.Fore.RED + f'Unsubscribing guild {subscriber[3]} due to not existing' + colorama.Style.RESET_ALL)
                    unsubscribe_discord('guild', None, subscriber[3], subscriber[4])
                    continue
                except discord.errors.Forbidden:
                    # The bot no longer has permission to send messages in the channel
                    print(colorama.Fore.RED + f'Unsubscribing guild {subscriber[3]} due to Forbidden error' + colorama.Style.RESET_ALL)
                    unsubscribe_discord('guild', None, subscriber[3], subscriber[4])
                    continue
                except discord.errors.RateLimited:
                    # Sleep for 1 second and try again
                    retry_after = getattr(e, 'retry_after', None)
                    print(colorama.Fore.YELLOW + f'Sleeping for {retry_after} seconds' + colorama.Style.RESET_ALL)
                    if retry_after:
                        await asyncio.sleep(retry_after)
                        try:
                            await channel.send(message)  # Retry sending message
                        except Exception as e:
                            # Skip the user if an error occurs again
                            continue
                except Exception as e:
                    # Skip the guild if an error occurs
                    continue

async def update_activity():
    while True:
        await client.wait_until_ready()  # Wait for the bot to be ready

        # Calculate current time and PST timezone
        now = datetime.datetime.now(datetime.timezone.utc)
        pst = tz.gettz('America/Los_Angeles')
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

    global send_wotd_count
    send_wotd_count += 1

    # Send to every admin that the bot is starting to send the Word of the Day
    for admin in ADMINS:
        try:
            user = await client.fetch_user(admin)
            dm_channel = await user.create_dm()
            await dm_channel.send(f'The bot is starting to send the Word of the Day. Instances: {send_wotd_count}')
        except:
            continue

    if send_wotd_count > 1:
        return

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
        sent_places = []  # This is the solution to the problem of the bot sending the same message multiple times
        async with semaphore:
            for subscriber in subscribers:
                if subscriber[1] == 'private':
                    if subscriber in sent_places:
                        continue
                    try:
                        user = await client.fetch_user(subscriber[2])
                        dm_channel = await user.create_dm()
                        await dm_channel.send(message)
                        sent_places.append(subscriber)
                    except discord.errors.Forbidden:
                        # The user blocked the bot, disabled DMs, or is no longer in the same guild
                        unsubscribe_discord('private', subscriber[2])
                        continue
                    except discord.errors.NotFound:
                        # The user no longer exists
                        unsubscribe_discord('private', subscriber[2])
                        continue
                    except discord.errors.RateLimited:
                        # Sleep for 1 second and try again
                        retry_after = getattr(e, 'retry_after', None)
                        if retry_after:
                            await asyncio.sleep(retry_after)
                            try:
                                await channel.send(message)  # Retry sending message
                            except Exception as e:
                                # Skip the user if an error occurs again
                                continue
                    except Exception as e:
                        # Skip the user if an error occurs
                        continue
                elif subscriber[1] == 'guild':
                    # Guild subscribers in sent_places are "{guild_id}/{channel_id}"
                    if f'{subscriber[3]}/{subscriber[4]}' in sent_places:
                        continue
                    if not client.get_guild(subscriber[3]):
                        # The guild no longer exists
                        unsubscribe_discord('guild', None, subscriber[3])
                        continue
                    try:
                        guild = client.get_guild(subscriber[3])
                        channel = guild.get_channel(subscriber[4])
                        await channel.send(message)
                        sent_places.append(f'{subscriber[3]}/{subscriber[4]}')
                    except discord.errors.NotFound:
                        # The guild no longer exists
                        unsubscribe_discord('guild', None, subscriber[3], subscriber[4])
                        continue
                    except discord.errors.RateLimited:
                        # Sleep for 1 second and try again
                        retry_after = getattr(e, 'retry_after', None)
                        if retry_after:
                            await asyncio.sleep(retry_after)
                            try:
                                await channel.send(message)  # Retry sending message
                            except Exception as e:
                                # Skip the user if an error occurs again
                                continue
                    except Exception as e:
                        # Skip the guild if an error occurs
                        continue

def run_client():
    client.run(TOKEN)

client_thread = threading.Thread(target=run_client)
client_thread.daemon = True
client_thread.start()

'''
async def run_client():
    await client.start(TOKEN)

def start_client():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.create_task(run_client())

client_thread = threading.Thread(target=start_client)
client_thread.daemon = True
client_thread.start()
'''
