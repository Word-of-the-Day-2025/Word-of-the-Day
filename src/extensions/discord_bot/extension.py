import asyncio
import colorama
import cpuinfo
import datetime
from datetime import timedelta
from dateutil import tz
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
import GPUtil
import importlib
from io import BytesIO
import json
import math
import os
from PIL import Image, ImageDraw, ImageFont
import platform
import psutil
import pytz
import re
import requests
import shlex
import sqlite3
from string import Template
import threading
import time

from logs import log_info, log_warning, log_error, log_exception
from . import subscribers
import wotd

# Attempt to import site (for advanced configuration, but if the site extension isn't present, just continue and allow errors on /config_advanced)
site = False
try:
    site = True
    from extensions.site import extension as site  # This is messy but it works
    log_info('Site extension imported successfully. Advanced configuration is available.')
except Exception as e:
    site = False
    log_warning(f'Could not import site extension. Advanced configuration will be unavailable. Error: {e}')

colorama.init()

subscribers.init_db()  # Initialize the database for subscribers

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_JSON = os.path.join(BASE_DIR, 'config.json')
RATE_LIMIT = 45  # Requests allowed per second (slightly below the 50 requests per second limit)
semaphore = asyncio.Semaphore(RATE_LIMIT)
update_activity_count = 0
wotd_loop_count = 0
last_send_time = 0

# Load config.json
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

def create_embed(title, description, color):
    return discord.Embed(title=title, description=description, color=color)

# Function to convert bytes to a human-readable format
def get_size(bytes, suffix='B'):
    factor = 1024
    for unit in ['', 'K', 'M', 'G', 'T', 'P']:
        if bytes < factor:
            return f'{bytes:.2f}{unit}{suffix}'
        bytes /= factor

# Get embeds with: create_embed(**embed_templates['subscribe']['private'])
embed_templates = {
    'subscribe': {
        'private': {
            'title': '**Subscribed** to Word of the Day!',
            'description': '''You will now receive the Word of the Day every day at <t:0:t>.
            To configure settings, send `/config`.
            To unsubscribe, send `/unsubscribe`.''',
            'color': discord.Color.gold()
        },
        'guild': {
            'title': '**Subscribed** to Word of the Day!',
            'description': '''This channel will now receive the Word of the Day every day at <t:0:t>.
            To configure settings, send `/config`.
            To unsubscribe, send `/unsubscribe`.''',
            'color': discord.Color.gold()
        },
        'already': {
            'private': {
                'title': 'You\'re already subscribed!',
                'description': '''You are already subscribed to the Word of the Day.
                To configure settings, send `/config`.
                To unsubscribe, send `/unsubscribe`.''',
                'color': discord.Color.pink()
            },
            'guild': {
                'title': 'This channel is already subscribed!',
                'description': '''This channel is already subscribed to the Word of the Day.
                To configure settings, send `/config`.
                To unsubscribe, send `/unsubscribe`.''',
                'color': discord.Color.pink()
            }
        }
    },
    'unsubscribe': {
        'private': {
            'title': '**Unsubscribed** from Word of the Day.',
            'description': '''You will no longer receive the Word of the Day.
            To subscribe again, send `/subscribe`.''',
            'color': discord.Color.blue()
        },
        'guild': {
            'title': '**Unsubscribed** from Word of the Day.',
            'description': '''This channel will no longer receive the Word of the Day.
            To subscribe again, send `/subscribe`.''',
            'color': discord.Color.blue()
        },
        'already': {
            'private': {
                'title': 'You\'re already unsubscribed.',
                'description': '''You are already unsubscribed from the Word of the Day.
                To subscribe again, send `/subscribe`.''',
                'color': discord.Color.dark_purple()
            },
            'guild': {
                'title': 'This channel is already unsubscribed.',
                'description': '''This channel is already unsubscribed from the Word of the Day.
                To subscribe again, send `/subscribe`.''',
                'color': discord.Color.dark_purple()
            }
        }
    }
}

@client.event
async def on_ready():
    try:
        log_info(f'Bot is ready. Logged in as {client.user.name} ({client.user.id})')
        await client.tree.sync()
        client.loop.create_task(send_wotd_loop())  # Start the Word of the Day loop
        client.loop.create_task(update_activity_loop())  # Start the activity update loop
    except Exception as e:
        log_exception(f'Error in on_ready: {str(e)}')

@client.tree.command(name='subscribe', description='Subscribe to the Word of the Day.')
async def subscribe(interaction: discord.Interaction):
    try:
        if interaction.channel.type == discord.ChannelType.private:  # If the command was sent in a DM
            if subscribers.query_subscribed(interaction.user.id, None, None):
                embed = create_embed(**embed_templates['subscribe']['already']['private'])
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                subscribers.subscribe(interaction.user.id, None, None)
                embed = create_embed(**embed_templates['subscribe']['private'])
                await interaction.response.send_message(embed=embed, ephemeral=True)
        elif interaction.channel.type == discord.ChannelType.text or interaction.channel.type == discord.ChannelType.news:  # If the command was sent in a text channel
            if interaction.user.guild_permissions.manage_channels:
                if subscribers.query_subscribed(None, interaction.guild.id, interaction.channel.id):
                    embed = create_embed(**embed_templates['subscribe']['already']['guild'])
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                else:
                    if subscribers.query_guild_over_limit(interaction.guild.id, MAX_SUBSCRIPTIONS_PER_GUILD):
                        embed = create_embed('Error', f'This server has reached the maximum number of subscriptions ({MAX_SUBSCRIPTIONS_PER_GUILD}).', discord.Color.red())
                        await interaction.response.send_message(embed=embed, ephemeral=True)
                        return
                    subscribers.subscribe(None, interaction.guild.id, interaction.channel.id)
                    embed = create_embed(**embed_templates['subscribe']['guild'])
                    await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                embed = create_embed('Error', 'You must have the `Manage Channels` permission to subscribe this channel.', discord.Color.red())
                await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            embed = create_embed('Error', 'This command can only be used in a DM or a text channel.', discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
    except Exception as e:
        log_exception(f'Error in subscribe command: {str(e)}')
        try:
            await interaction.response.send_message('An error occurred while processing your request.', ephemeral=True)
        except:
            pass

@client.tree.command(name='unsubscribe', description='Unsubscribe from the Word of the Day.')
async def unsubscribe(interaction: discord.Interaction):
    try:
        if interaction.channel.type == discord.ChannelType.private:  # If the command was sent in a DM
            if subscribers.query_subscribed(interaction.user.id, None, None):
                subscribers.unsubscribe(interaction.user.id, None, None)
                embed = create_embed(**embed_templates['unsubscribe']['private'])
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                embed = create_embed(**embed_templates['unsubscribe']['already']['private'])
                await interaction.response.send_message(embed=embed, ephemeral=True)
        elif interaction.channel.type == discord.ChannelType.text or interaction.channel.type == discord.ChannelType.news:  # If the command was sent in a text channel
            if interaction.user.guild_permissions.manage_channels:
                if subscribers.query_subscribed(None, interaction.guild.id, interaction.channel.id):
                    subscribers.unsubscribe(None, interaction.guild.id, interaction.channel.id)
                    embed = create_embed(**embed_templates['unsubscribe']['guild'])
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                else:
                    embed = create_embed(**embed_templates['unsubscribe']['already']['guild'])
                    await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                embed = create_embed('Error', 'You must have the `Manage Channels` permission to unsubscribe this channel.', discord.Color.red())
                await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            embed = create_embed('Error', 'This command can only be used in a DM or a text channel.', discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
    except Exception as e:
        log_exception(f'Error in unsubscribe command: {str(e)}')
        try:
            await interaction.response.send_message('An error occurred while processing your request.', ephemeral=True)
        except:
            pass

class TimeChoices(discord.app_commands.Choice):
    def __init__(self, name, value):
        super().__init__(name=name, value=value)

@client.tree.command(name='config', description='Configure your subscription settings.')
@app_commands.describe(dmy='Whether to use DD-MM-YYYY format (default is True).',
                       time='The time to send the WOTD (This will reset your timezone to UTC).')
@app_commands.choices(time=[
    discord.app_commands.Choice(name='00:00 (Midnight)', value=0),
    discord.app_commands.Choice(name='01:00', value=3600),
    discord.app_commands.Choice(name='02:00', value=7200),
    discord.app_commands.Choice(name='03:00', value=10800),
    discord.app_commands.Choice(name='04:00', value=14400),
    discord.app_commands.Choice(name='05:00', value=18000),
    discord.app_commands.Choice(name='06:00', value=21600),
    discord.app_commands.Choice(name='07:00', value=25200),
    discord.app_commands.Choice(name='08:00', value=28800),
    discord.app_commands.Choice(name='09:00', value=32400),
    discord.app_commands.Choice(name='10:00', value=36000),
    discord.app_commands.Choice(name='11:00', value=39600),
    discord.app_commands.Choice(name='12:00 (Noon)', value=43200),
    discord.app_commands.Choice(name='13:00', value=46800),
    discord.app_commands.Choice(name='14:00', value=50400),
    discord.app_commands.Choice(name='15:00', value=54000),
    discord.app_commands.Choice(name='16:00', value=57600),
    discord.app_commands.Choice(name='17:00', value=61200),
    discord.app_commands.Choice(name='18:00', value=64800),
    discord.app_commands.Choice(name='19:00', value=68400),
    discord.app_commands.Choice(name='20:00', value=72000),
    discord.app_commands.Choice(name='21:00', value=75600),
    discord.app_commands.Choice(name='22:00', value=79200),
    discord.app_commands.Choice(name='23:00', value=82800),
])
async def config(interaction: discord.Interaction, dmy: bool = True, time: int = 0):
    try:
        if interaction.channel.type == discord.ChannelType.private:  # If the command was sent in a DM
            if subscribers.query_subscribed(interaction.user.id, None, None):
                subscribers.configure(user_id=interaction.user.id, time_sunday=time, time_monday=time, time_tuesday=time, time_wednesday=time, time_thursday=time, time_friday=time, time_saturday=time, is_dmy=dmy)

                # Format time for display in message
                utc_time = datetime.time(time // 3600, (time % 3600) // 60)
                tz_str = subscribers.get_subscriber_data(interaction.user.id, None, None)[0][4] or 'UTC'
                try:
                    user_tz = pytz.timezone(tz_str)
                    local_dt = datetime.datetime.combine(datetime.date.today(), utc_time)
                    local_dt = pytz.UTC.localize(local_dt).astimezone(user_tz)
                    time_str = f'`{local_dt.strftime('%H:%M')}` ({tz_str})'
                except pytz.exceptions.UnknownTimeZoneError:
                    time_str = f'`{utc_time.strftime('%H:%M')}` (UTC)'
                
                embed = create_embed('Configuration Updated!',
                                    f'Your subscription settings have been updated.\nTime set to: {time_str}\n'
                                    f'Date format: {"DD-MM-YYYY" if dmy else "MM-DD-YYYY"}', 
                                    discord.Color.green())
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                embed = create_embed('Error', 'You are not subscribed to the Word of the Day.', discord.Color.red())
                await interaction.response.send_message(embed=embed, ephemeral=True)
        elif interaction.channel.type == discord.ChannelType.text or interaction.channel.type == discord.ChannelType.news:  # If the command was sent in a text channel
            if interaction.user.guild_permissions.manage_channels:
                if subscribers.query_subscribed(None, interaction.guild.id, interaction.channel.id):
                    subscribers.configure(guild_id=interaction.guild.id, channel_id=interaction.channel.id, time_sunday=time, time_monday=time, time_tuesday=time, time_wednesday=time, time_thursday=time, time_friday=time, time_saturday=time, is_dmy=dmy)
                    
                    # Format time for display in message
                    utc_time = datetime.time(time // 3600, (time % 3600) // 60)
                    tz_str = subscribers.get_subscriber_data(interaction.guild.id, interaction.channel.id)[0][4] or 'UTC'
                    try:
                        user_tz = pytz.timezone(tz_str)
                        local_dt = datetime.datetime.combine(datetime.date.today(), utc_time)
                        local_dt = pytz.UTC.localize(local_dt).astimezone(user_tz)
                        time_str = f'`{local_dt.strftime('%H:%M')}` ({tz_str})'
                    except pytz.exceptions.UnknownTimeZoneError:
                        time_str = f'`{utc_time.strftime('%H:%M')}` (UTC)'
                    
                    embed = create_embed('Configuration Updated!', 
                                        f'Your subscription settings have been updated.\nTime set to: {time_str}\n'
                                        f'Date format: {"DD-MM-YYYY" if dmy else "MM-DD-YYYY"}', 
                                        discord.Color.green())
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                else:
                    embed = create_embed('Error', 'This channel is not subscribed to the Word of the Day.', discord.Color.red())
                    await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                embed = create_embed('Error', 'You must have the `Manage Channels` permission to configure this channel.', discord.Color.red())
                await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            embed = create_embed('Error', 'This command can only be used in a DM or a text channel.', discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
    except Exception as e:
        log_exception(f'Error in config command: {str(e)}')
        try:
            await interaction.response.send_message('An error occurred while processing your request.', ephemeral=True)
        except:
            pass

@client.tree.command(name='config_advanced', description='Generate a link for advanced configuration.')
async def config_advanced(interaction: discord.Interaction):
    if site:
        user_id = guild_id = channel_id = None
        if interaction.channel.type == discord.ChannelType.private:
            user_id = interaction.user.id
            guild_id = None
            channel_id = None
        else:
            user_id = None
            guild_id = interaction.guild.id
            channel_id = interaction.channel.id
        if subscribers.query_subscribed(user_id=user_id, guild_id=guild_id, channel_id=channel_id):
            if interaction.channel.type == discord.ChannelType.private:
                link = site.generate_config_discord_link(is_user=True, user_id=interaction.user.id)
            elif interaction.channel.type == discord.ChannelType.text or interaction.channel.type == discord.ChannelType.news:
                if interaction.user.guild_permissions.manage_channels:
                    link = site.generate_config_discord_link(is_user=False, guild_id=interaction.guild.id, channel_id=interaction.channel.id)
                else:
                    embed = create_embed('Error', 'You must have the `Manage Channels` permission to configure this channel.', discord.Color.red())
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    return
        else:
            embed = create_embed('Error', 'You are not subscribed to the Word of the Day.', discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        if not link:
            embed = create_embed('Error', 'Could not generate configuration link. Please try again later.', discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        await cache_config_data(user_id=user_id, guild_id=guild_id, channel_id=channel_id)
        embed = create_embed('Advanced Configuration', f'Click [here]({link}) to configure advanced settings.\n\n-# Do not share this link with anyone you do not want to alter your WOTD settings.', discord.Color.green())
        await interaction.response.send_message(embed=embed, ephemeral=True)
    else:
        embed = create_embed('Error', 'Advanced configuration is unavailable. This is not your fault; please contact the bot host for assistance.', discord.Color.red())
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

@client.tree.command(name='config_reset', description='Reset your subscription settings.')
async def config_reset(interaction: discord.Interaction):
    try:
        if interaction.channel.type == discord.ChannelType.private:  # If the command was sent in a DM
            if subscribers.query_subscribed(interaction.user.id, None, None):
                subscribers.configure(interaction.user.id, None, None, 0, True)
                embed = create_embed('Configuration Reset', 'Your subscription settings have been reset.', discord.Color.green())
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                embed = create_embed('Error', 'You are not subscribed to the Word of the Day.', discord.Color.red())
                await interaction.response.send_message(embed=embed, ephemeral=True)
        elif interaction.channel.type == discord.ChannelType.text or interaction.channel.type == discord.ChannelType.news:  # If the command was sent in a text channel
            if interaction.user.guild_permissions.manage_channels:
                if subscribers.query_subscribed(None, interaction.guild.id, interaction.channel.id):
                    subscribers.configure(None, interaction.guild.id, interaction.channel.id, 0, True)
                    embed = create_embed('Configuration Reset', 'Your subscription settings have been reset.', discord.Color.green())
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                else:
                    embed = create_embed('Error', 'This channel is not subscribed to the Word of the Day.', discord.Color.red())
                    await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                embed = create_embed('Error', 'You must have the `Manage Channels` permission to configure this channel.', discord.Color.red())
                await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            embed = create_embed('Error', 'This command can only be used in a DM or a text channel.', discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
    except Exception as e:
        log_exception(f'Error in config_reset command: {str(e)}')
        try:
            await interaction.response.send_message('An error occurred while processing your request.', ephemeral=True)
        except:
            pass

@client.tree.command(name='query', description='Query the Word of the Day.')
async def query(interaction: discord.Interaction):
    try:
        # Get the date from wotd.py (YYYY-MM-DD format)
        current_date = wotd.current_date
        day = current_date.split('-')[2]
        day = day.lstrip('0')
        month_name = datetime.datetime.strptime(current_date, '%Y-%m-%d').strftime('%B')
        year = current_date.split('-')[0]

        # Get the word of the day from wotd.py
        word = wotd.word
        ipa = wotd.ipa
        pos = wotd.pos
        definition = wotd.definition

        if word:
            message = f'Today is {day} {month_name} {year}, and the Word of the Day is "{word}" ({ipa}), which is defined as: ({pos}) {definition}'
        else:
            message = f'Today is {day} {month_name} {year}, and there is no Word of the Day today.'
        await interaction.response.send_message(message, ephemeral=True)
    except Exception as e:
        log_exception(f'Error in query command: {str(e)}')
        try:
            await interaction.response.send_message('An error occurred while processing your request.', ephemeral=True)
        except:
            pass  # Give up

@client.tree.command(name='query_date', description='Query the Word of the Day for a specific date.')
@app_commands.describe(date='The date to query the Word of the Day for (YYYY-MM-DD format).')
async def query_date(interaction: discord.Interaction, date: str):
    try:
        # Validate the date format
        if not re.match(r'^\d{4}-\d{2}-\d{2}$', date):
            embed = create_embed('Error', 'Invalid date format. Please use YYYY-MM-DD.', discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        day, month, year = date.split('-')
        # Check datetime validity
        try:
            datetime.datetime(int(year), int(month), int(day))
        except ValueError:
            embed = create_embed('Error', 'Invalid date. Please ensure the date exists.', discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        # Check whether the date is in the future (not allowed)
        if datetime.datetime.now(tz.tzutc()) < datetime.datetime(int(year), int(month), int(day), tzinfo=tz.tzutc()):
            embed = create_embed('Error', 'You cannot query a future date.', discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        # Get the word of the day for the specified date
        result = wotd.query_word(date)
        if result:
            day = date.split('-')[2]
            day = day.lstrip('0')
            month_name = datetime.datetime.strptime(date, '%Y-%m-%d').strftime('%B')
            date_message = f'{day} {month_name} {year}'
            # Check if the query date is the current date
            if date == wotd.current_date:
                message = f'The Word of the Day for today ({date_message}) is "{result['word']}" ({result['ipa']}), which is defined as: ({result['pos']}) {result['definition']}'
            else:
                message = f'The Word of the Day for {date_message} was "{result['word']}" ({result['ipa']}), which is defined as: ({result['pos']}) {result['definition']}'
            if result['word'] == '':
                message = f'The Word of the Day for {date_message} is not available.'
            await interaction.response.send_message(message, ephemeral=True)
        else:
            embed = create_embed('Error', f'No Word of the Day found for {date}.', discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
    except Exception as e:
        log_exception(f'Error in query_date command: {str(e)}')
        try:
            await interaction.response.send_message('An error occurred while processing your request.', ephemeral=True)
        except:
            pass

@client.tree.command(name='find_wotd', description='Find the Word of the Day by word.')
@app_commands.describe(word='The word to find the Word of the Day for.')
async def find_wotd(interaction: discord.Interaction, word: str):
    try:
        result = wotd.find_wotd(word)  # May send multiple results
        # Send only what date(s) the Word of the Day was found
        if result:
            if len(result) == 1:
                message = f'The Word of the Day "{word}" was found on the following date:\n'
            else:
                message = f'The Word of the Day "{word}" was found on the following dates:\n'
            for row in result:
                date = row['date']
                day = date.split('-')[0]
                day = day.lstrip('0')
                if day[-1] == '1' and day != '11':
                    day_suffix = 'st'
                elif day[-1] == '2' and day != '12':
                    day_suffix = 'nd'
                elif day[-1] == '3' and day != '13':
                    day_suffix = 'rd'
                else:
                    day_suffix = 'th'
                month_name = datetime.datetime.strptime(date, '%Y-%m-%d').strftime('%B')
                date_message = f'{day} {month_name} {date.split('-')[0]}'
                message += f'- {date_message}\n'
            await interaction.response.send_message(message, ephemeral=True)
        else:
            embed = create_embed('Error', f'No Word of the Day found for "{word}".', discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
    except Exception as e:
        log_exception(f'Error in find_word command: {str(e)}')
        try:
            await interaction.response.send_message('An error occurred while processing your request.', ephemeral=True)
        except:
            pass

# Below this point are admin-only commands

@client.command()
async def append(ctx, *, args: str):
    if ctx.author.id not in ADMINS:
        return

    # Regular expression to match arguments surrounded by quotes
    pattern = r'(["\'])(?:(?=(\\?))\2.)*?\1'
    matches = re.findall(pattern, args)

    if len(matches) != 4 and len(matches) != 5:
        await ctx.send('Invalid arguments. Please provide the word, IPA, type, and definition surrounded by quotes.')
        return

    if len(matches) == 4:
        lexer = shlex.shlex(args, posix=True)
        lexer.whitespace_split = True
        lexer.quotes = '"\''
        lexer.escapedquotes = '"\''
        word, ipa, pos, definition = list(lexer)
    elif len(matches) == 5:
        lexer = shlex.shlex(args, posix=True)
        lexer.whitespace_split = True
        lexer.quotes = '"\''
        lexer.escapedquotes = '"\''
        date, word, ipa, pos, definition = list(lexer)
        # Ensure day and month are always two digits
        try:
            day, month, year = date.split('-')
            date = f'{int(day):02d}-{int(month):02d}-{year}'
            datetime.datetime.strptime(date, '%Y-%m-%d')
        except ValueError:
            await ctx.send('Invalid date format. Please use YYYY-MM-DD.')
            return

    # Check for if the word already exists in the database
    # TODO: Make it so the user can confirm whether they want to add it anyways, and detect different definitions
    result = wotd.find_wotd(word)
    if result:
        await ctx.send(f'The word "{word}" already exists in the database. Please use a different word.')
        return

    # Append the word to the database
    if len(matches) == 4:
        date = wotd.append_word(None, word, ipa, pos, definition)
    else:
        wotd.append_word(date, word, ipa, pos, definition)

    # Inform the user that the word was successfully appended
    await ctx.send(f'''
The word "{word}" has been successfully appended to the database:
- Date: {date}
- Word: {word}
- IPA: {ipa}
- PoS: {pos}
- Definition: {definition}
    ''')

@client.command()
async def monitor(ctx):
    if ctx.author.id not in ADMINS:
        return

    # System stats
    uptime = str(datetime.timedelta(seconds=int(time.time() - psutil.boot_time())))
    ping = round((client.latency * 1000), 2)
    process_cpu = psutil.Process(os.getpid())
    process_cpu_percent = round(process_cpu.cpu_percent(), 2)
    process_ram = round(psutil.Process().memory_info().rss / (1024 ** 2))
    sys_stats = f'## System:\n- **Operating System**: {platform.system()} {platform.release()}, {platform.version()}\n- **Uptime**: {uptime}\n- **Ping**: {ping}MS\n- **Process**: {process_cpu_percent}% CPU, {process_ram}MB RAM\n'

    # CPU stats
    cpu_info = cpuinfo.get_cpu_info()
    cpu_name = cpu_info['brand_raw']
    cpu_logical = psutil.cpu_count(logical=True)
    cpu_cores = psutil.cpu_count(logical=False)
    cpu_frequency = str(cpu_info['hz_advertised'][0] / 1000 ** 3)
    cpu_stress = round(psutil.cpu_percent(interval=1), 2)
    cpu_stats = f'## Processor:\n- **Brand**: {cpu_name}\n- **Specs**: {cpu_logical} Logical Processors, {cpu_cores} Cores, {cpu_frequency}GHz\n- **Usage**: {cpu_stress}%\n'

    # GPU stats
    gpu_stats = ''
    gpus = GPUtil.getGPUs()
    if gpus:
        for gpu in gpus:
            gpu_name = gpu.name
            gpu_load = round(gpu.load * 100, 2)
            gpu_temperature = round(gpu.temperature, 2)
            gpu_usage = get_size(gpu.memoryUsed * (1024 ** 2))
            gpu_total = round(gpu.memoryTotal / 1024, 2)
            gpu_stats += f'## Graphics Card [{gpu.id}]:\n- **Brand**: {gpu_name}\n- **Usage**: {gpu_load}%, {gpu_temperature}°C, {gpu_usage}/{gpu_total}GB\n'

    # RAM stats
    ram_info = psutil.virtual_memory()
    ram_usage = get_size(ram_info.used)
    ram_total = get_size(ram_info.total)
    ram_usage_ratio = ram_info.used / ram_info.total
    ram_percent = round(ram_usage_ratio * 100, 2)
    ram_stats = f'## Memory:\n- **Usage**: {ram_usage}/{ram_total} ({ram_percent}%)\n'

    await ctx.send(
        f'# Host Computer Performance:\n{sys_stats}{cpu_stats}{gpu_stats}{ram_stats}'
    )

@client.command()
async def query_next(ctx):
    if ctx.author.id not in ADMINS:
        return

    date = datetime.datetime.now(tz.tzutc())
    date_tomorrow = (date + timedelta(days=1)).strftime('%Y-%m-%d')
    wotd_tomorrow = wotd.query_word(date_tomorrow)

    day = date_tomorrow.split('-')[0]
    day = day.lstrip('0')
    month_name = datetime.datetime.strptime(date_tomorrow, '%Y-%m-%d').strftime('%B')
    year = date_tomorrow.split('-')[2]
    date_tomorrow_formatted = f'{day} {month_name} {year}'

    message = f'Tomorrow is {date_tomorrow_formatted}, and the Word of the Day will be "{wotd_tomorrow['word']}" ({wotd_tomorrow['ipa']}), which is defined as: ({wotd_tomorrow['pos']}) {wotd_tomorrow['definition']}'
    if wotd.word == '':
        message = f'The Word of the Day for tomorrow ({date_tomorrow}) is not available.'
    await ctx.send(message)

@client.command()
async def set_wotd(ctx, *, args: str):
    if ctx.author.id not in ADMINS:
        return

    # Regular expression to match arguments surrounded by quotes
    pattern = r'(["\'])(?:(?=(\\?))\2.)*?\1'
    matches = re.findall(pattern, args)
    if len(matches) != 5:
        await ctx.send('Invalid arguments. Please provide the date, word, IPA, type, and definition surrounded by quotes.')
        return
    lexer = shlex.shlex(args, posix=True)
    lexer.whitespace_split = True
    lexer.quotes = '"\''
    lexer.escapedquotes = '"\''
    date, word, ipa, pos, definition = list(lexer)
    wotd.set_wotd(date, word, ipa, pos, definition)

    # Inform the user that the Word of the Day was successfully set
    await ctx.send(f'''
The Word of the Day has been successfully set to:
- Date: {date}
- Word: {word}
- IPA: {ipa}
- PoS: {pos}
- Definition: {definition}
''')

@client.command()
async def test_send(ctx):  # This command is for testing the custom message format system
    if ctx.author.id not in ADMINS:
        return

    if ctx.channel.type == discord.ChannelType.private:
        user_id = ctx.author.id
        guild_id = None
        channel_id = None
        subscriber_data = subscribers.get_subscriber_data(user_id, guild_id, channel_id)
        subscriber = subscriber_data[0] if subscriber_data else None
    elif ctx.channel.type == discord.ChannelType.text or ctx.channel.type == discord.ChannelType.news:
        user_id = None
        guild_id = ctx.guild.id
        channel_id = ctx.channel.id
        subscriber = subscribers.get_subscriber_data(None, guild_id, channel_id)
    else:
        await ctx.send('This command can only be used in a DM or a text channel.')
        return
    if not subscriber:
        await ctx.send('You are not subscribed to the Word of the Day.')
        return
    try:
        # wotd_data = wotd.query_word(wotd.current_date)
        wotd_data = wotd.query_word('01-01-2025')
        if not wotd_data:
            await ctx.send('The Word of the Day is not available.')
            return

        current_datetime = datetime.datetime.now(tz.tzutc())
        message = format_message(subscriber, wotd_data, current_datetime)

        await ctx.send(message)
    except KeyError:
        await ctx.send('Subscription data is incomplete or invalid.')
    except Exception as e:
        log_exception(f'Error in test_send command: {str(e)}')

@client.command()
async def save_db(ctx):
    if ctx.author.id not in ADMINS:
        return

    try:
        wotd.save_wotd_database()
        await ctx.send('Database saved successfully.')
    except Exception as e:
        log_exception(f'Error saving database: {str(e)}')
        await ctx.send('An error occurred while saving the database.')

async def cache_config_data(user_id=None, guild_id=None, channel_id=None):
    # Get the image of the user or server as a PNG
    if user_id:
        user = await client.fetch_user(user_id)
        avatar_url = user.avatar.url if user.avatar else None
    elif guild_id and channel_id:
        guild = client.get_guild(guild_id)
        avatar_url = guild.icon.with_format('png').url if guild.icon else None
    else:
        return
    if not avatar_url:
        return
    response = requests.get(avatar_url)
    image = Image.open(BytesIO(response.content)).convert('RGBA')
    image = image.resize((128, 128))
    # Save the image to a BytesIO object
    image_bytes = BytesIO()
    image.save(image_bytes, format='PNG')
    image_bytes.seek(0)
    # Save the image to disk as a PNG file (in ../site/cache/config_discord/)
    filename = ''
    if user_id:
        filename = f'{user_id}'
    elif guild_id and channel_id:
        filename = f'{guild_id}_{channel_id}'
    if not os.path.exists('./src/extensions/site/www/cache/config_discord/'):
        os.makedirs('./src/extensions/site/www/cache/config_discord/')
    with open(f'./src/extensions/site/www/cache/config_discord/{filename}.png', 'wb') as f:
        f.write(image_bytes.getvalue())
    with open(f'./src/extensions/site/www/cache/config_discord/{filename}.json', 'w') as f:
        json.dump({
            'user_id': user_id,
            'guild_id': guild_id,
            'channel_id': channel_id,
            'user_name': user.display_name if user_id else None,
            'guild_name': guild.name if guild_id else None,
            'channel_name': client.get_channel(channel_id).name if channel_id else None,
        }, f)

def format_message(subscriber, wotd_data, current_datetime):
    '''Format WOTD message based on subscriber preferences'''

    try:
        # Calculate day suffix
        day = current_datetime.day
        if day in [11, 12, 13]:  # Special case for 11th, 12th, 13th
            day_suffix = 'th'
        elif day % 10 == 1:
            day_suffix = 'st'
        elif day % 10 == 2:
            day_suffix = 'nd'
        elif day % 10 == 3:
            day_suffix = 'rd'
        else:
            day_suffix = 'th'

        day_of_week = current_datetime.strftime('%A')
        month_name = current_datetime.strftime('%B')
        year = current_datetime.year

        # Date formatting options
        current_date_long_dmy = f'{day_of_week}, {day} {month_name} {year}'
        current_date_long_mdy = f'{day_of_week}, {month_name} {day}{day_suffix}, {year}'
        current_date_medium_dmy = f'{day} {month_name} {year}'
        current_date_medium_mdy = f'{month_name} {day}{day_suffix}, {year}'
        current_date_short_hyphen_dmy = f'{current_datetime.day:02d}-{current_datetime.month:02d}-{current_datetime.year}'
        current_date_short_hyphen_mdy = f'{current_datetime.month:02d}-{current_datetime.day:02d}-{current_datetime.year}'
        current_date_short_slashed_dmy = f'{current_datetime.day:02d}/{current_datetime.month:02d}/{current_datetime.year}'
        current_date_short_slashed_mdy = f'{current_datetime.month:02d}/{current_datetime.day:02d}/{current_datetime.year}'

        prefers_dmy = subscriber[15]  # is_dmy
        date_style = subscriber[17]  # message_date_style
        date_style_lookup = {
            0: current_date_long_dmy if prefers_dmy else current_date_long_mdy,
            1: current_date_medium_dmy if prefers_dmy else current_date_medium_mdy,
            2: current_date_short_hyphen_dmy if prefers_dmy else current_date_short_hyphen_mdy,
            3: current_date_short_slashed_dmy if prefers_dmy else current_date_short_slashed_mdy
        }
        current_date = date_style_lookup.get(date_style, current_date_medium_dmy if prefers_dmy else current_date_medium_mdy)

        # Build message based on subscriber's preferences
        message = ''
        if subscriber[13]:  # include_date
            message += f'Today is {current_date}, and the Word of the Day is "{wotd_data["word"]}"'
        else:
            message += f'The Word of the Day is "{wotd_data["word"]}"'
        
        if subscriber[14]:  # include_ipa
            message += f' ({wotd_data["ipa"]}), '
        else:
            message += f', '
        
        message += f'which is defined as: ({wotd_data["pos"]}) {wotd_data["definition"]}'
        return message
        
    except Exception as e:
        log_error(f'Error formatting message: {e}')
        # Fallback to simple format
        return f'Today is {current_datetime.strftime("%d %B %Y")}, and the Word of the Day is "{wotd_data["word"]}" ({wotd_data["ipa"]}), which is defined as: ({wotd_data["pos"]}) {wotd_data["definition"]}'

async def update_activity_loop():
    while True:
        await client.wait_until_ready()  # Wait for the bot to be ready

        # Calculate current time in UTC
        now = datetime.datetime.now(datetime.timezone.utc)

        # Determine the next 12:00 AM UTC
        next_midnight_utc = now.replace(hour=0, minute=0, second=0, microsecond=0)
        if now >= next_midnight_utc:
            next_midnight_utc += datetime.timedelta(days=1)

        # Calculate the sleep duration until the next minute and the total duration until 12:00 AM UTC
        sleep_duration = (next_midnight_utc - now).total_seconds()
        countdown = math.ceil(sleep_duration / 60)
        countdown_str = '{:,}'.format(countdown)
        if countdown == 1:
            activity_state = f'Next word in {countdown_str} minute.'
        elif countdown == 1440:
            activity_state = f'WOTD: {wotd.word}'
        else:
            activity_state = f'Next word in {countdown_str} minutes.'
        activity = discord.Activity(
            name='WOTD',
            type=discord.ActivityType.custom,
            state=activity_state
        )
        await client.change_presence(activity=activity)  # Update the bot's activity status

        # Sleep until the next second is 00
        await asyncio.sleep(60 - now.second)

'''
async def send_wotd_loop():
    global wotd_loop_count, last_send_time
    wotd_loop_count += 1
    if wotd_loop_count != 1:
        log_warning('wotd_loop() was called more than once. Stopping the loop.')
        return

    log_info('Word of the Day Discord Bot loop started')

    while True:
        try:
            # Get current UTC time
            now_utc = datetime.datetime.now(tz.tzutc())
            
            # Calculate next midnight UTC (when we recalculate schedule)
            next_midnight_utc = (now_utc + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            
            # Get all subscribers and calculate their next send times
            all_subscribers = subscribers.get_subscriber_data()
            if not all_subscribers:
                log_info('No subscribers found, waiting until next midnight to check again')
                sleep_duration = (next_midnight_utc - now_utc).total_seconds()
                await asyncio.sleep(sleep_duration)
                continue

            # Build schedule: list of (utc_send_time, subscriber, wotd_date_with_tz) tuples
            schedule = []
            
            # Weekday mapping: Python weekday() -> database column index
            day_column_mapping = {
                0: 6,   # Monday -> time_monday (index 6)
                1: 7,   # Tuesday -> time_tuesday (index 7)
                2: 8,   # Wednesday -> time_wednesday (index 8)
                3: 9,   # Thursday -> time_thursday (index 9)
                4: 10,  # Friday -> time_friday (index 10)
                5: 11,  # Saturday -> time_saturday (index 11)
                6: 5    # Sunday -> time_sunday (index 5)
            }
            
            for subscriber in all_subscribers:
                try:
                    # Get and validate subscriber timezone
                    subscriber_tz_str = subscriber[4] if subscriber[4] else 'UTC'
                    try:
                        subscriber_tz = pytz.timezone(subscriber_tz_str)
                    except pytz.exceptions.UnknownTimeZoneError:
                        log_warning(f'Unknown timezone {subscriber_tz_str} for subscriber, defaulting to UTC')
                        subscriber_tz = pytz.timezone('UTC')

                    # Get subscriber's current local time
                    subscriber_time = now_utc.astimezone(subscriber_tz)
                    
                    # Check today, tomorrow, and day after tomorrow in subscriber's timezone
                    # This handles edge cases for extreme timezones (UTC-12 to UTC+14)
                    for days_ahead in [0, 1, 2]:
                        target_date = subscriber_time + timedelta(days=days_ahead)
                        day_of_week = target_date.weekday()  # 0=Monday, 6=Sunday
                        
                        # Get scheduled time for this day
                        day_time_column_index = day_column_mapping[day_of_week]
                        scheduled_time_seconds = subscriber[day_time_column_index]
                        
                        # Skip if no time scheduled for this day (0 means no schedule)
                        if scheduled_time_seconds is None:
                            continue
                        
                        # Convert seconds to hours, minutes, seconds
                        hours = scheduled_time_seconds // 3600
                        minutes = (scheduled_time_seconds % 3600) // 60
                        seconds = scheduled_time_seconds % 60
                        
                        # Create naive datetime for the target date and time
                        naive_dt = datetime.datetime(
                            target_date.year, target_date.month, target_date.day,
                            hours, minutes, seconds
                        )
                        
                        # Handle DST transitions gracefully
                        try:
                            send_time_local = subscriber_tz.localize(naive_dt, is_dst=None)
                        except pytz.exceptions.AmbiguousTimeError:
                            # During "fall back", choose the first occurrence (standard time)
                            send_time_local = subscriber_tz.localize(naive_dt, is_dst=False)
                            log_info(f'Ambiguous time during DST transition, using standard time: {naive_dt}')
                        except pytz.exceptions.NonExistentTimeError:
                            # During "spring forward", move to the next valid time
                            send_time_local = subscriber_tz.localize(naive_dt + timedelta(hours=1), is_dst=True)
                            log_info(f'Non-existent time during DST transition, moving forward 1 hour: {naive_dt}')
                        
                        # Convert to UTC for scheduling
                        send_time_utc = send_time_local.astimezone(tz.tzutc())
                        
                        # Only schedule if it's in the future and before next midnight UTC
                        # Changed >= to > to allow times that are equal to now_utc (like midnight)
                        # Also added a small buffer (30 seconds) to catch times that just passed
                        buffer_time = now_utc - timedelta(seconds=30)
                        if send_time_utc > buffer_time and send_time_utc < next_midnight_utc:
                            # Determine which date to use for WOTD lookup (keep timezone info)
                            if subscriber[12]:  # send_wotd_in_utc
                                # Use UTC date at send time
                                wotd_date = send_time_utc
                            else:
                                # Use local date and time
                                wotd_date = send_time_local
                            
                            schedule.append((send_time_utc, subscriber, wotd_date))
                            log_info(f'Scheduled send for {send_time_utc.strftime("%Y-%m-%d %H:%M:%S UTC")} '
                                   f'(local: {send_time_local.strftime("%Y-%m-%d %H:%M:%S %Z")}) '
                                   f'for WOTD date: {wotd_date.strftime("%Y-%m-%d %Z")}')
                
                except Exception as e:
                    log_exception(f'Error calculating schedule for subscriber {subscriber}: {str(e)}')
                    continue
            
            # Sort schedule by send time
            schedule.sort(key=lambda x: x[0])
            
            log_info(f'Calculated schedule for {len(schedule)} sends until next midnight')
            
            # Process each scheduled send
            for send_time_utc, subscriber, wotd_date in schedule:
                try:
                    # Wait until it's time to send
                    now_utc = datetime.datetime.now(tz.tzutc())
                    if send_time_utc > now_utc:
                        sleep_duration = (send_time_utc - now_utc).total_seconds()
                        log_info(f'Waiting {sleep_duration:.1f} seconds until next send at {send_time_utc.strftime("%H:%M:%S UTC")}')
                        await asyncio.sleep(sleep_duration)
                    
                    # Get WOTD for the appropriate date
                    # Convert to string using the date part only
                    date_str = wotd_date.strftime('%Y-%m-%d')
                    wotd_data = wotd.query_word(date_str)
                    
                    if not wotd_data or not wotd_data.get('word'):
                        log_warning(f'No WOTD available for {date_str}, skipping subscriber')
                        continue
                    
                    # Format message - pass the timezone-aware datetime
                    # (Remove timezone only if format_message requires it)
                    try:
                        message = format_message(subscriber, wotd_data, wotd_date)
                    except TypeError:
                        # Fallback if format_message doesn't accept timezone-aware datetime
                        message = format_message(subscriber, wotd_data, wotd_date.replace(tzinfo=None))
                    
                    # Send the message
                    success = await send_message_to_subscriber(subscriber, message, date_str)
                    
                    if success:
                        last_send_time = now_utc
                    
                except Exception as e:
                    log_exception(f'Error processing scheduled send: {str(e)}')
                    continue
            
            # After processing all scheduled sends, wait until next midnight to recalculate
            now_utc = datetime.datetime.now(tz.tzutc())
            next_midnight_utc = (now_utc + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            sleep_duration = (next_midnight_utc - now_utc).total_seconds()
            log_info(f'All sends complete, waiting {sleep_duration:.1f} seconds until next midnight to recalculate schedule')
            await asyncio.sleep(sleep_duration)
                
        except Exception as e:
            log_exception(f'Error in send_wotd_loop: {str(e)}')
            await asyncio.sleep(60)  # Wait a minute before retrying
'''

async def send_wotd_loop():
    global wotd_loop_count, last_send_time
    wotd_loop_count += 1
    if wotd_loop_count != 1:
        log_warning('wotd_loop() was called more than once. Stopping the loop.')
        return

    log_info('Word of the Day Discord Bot loop started')

    # Initialize current_date as a datetime object
    current_datetime = datetime.datetime.now(tz.tzutc()).replace(hour=0, minute=0, second=0, microsecond=0)
    
    while True:
        try:
            # Wait until the next hour
            now = datetime.datetime.now(tz.tzutc())
            next_half_hour = (now + timedelta(minutes=30)).replace(second=0, microsecond=0)
            sleep_time = (next_half_hour - now).total_seconds()
            log_info(f'Waiting for {sleep_time} seconds until the next half hour...')
            await asyncio.sleep(sleep_time)

            # Get the current hour in UTC
            now = datetime.datetime.now(tz.tzutc())
            current_time = now.hour * 3600 + now.minute * 60 + now.second
            current_hour = round(current_time / 3600)

            # Check if current_hour is different from the current hour
            while now.hour != current_hour:
                await asyncio.sleep(1/10)  # Sleep for a short time to avoid busy waiting

            # Update date at midnight
            if current_hour == 0:
                current_datetime = current_datetime + timedelta(days=1)

            wotd_data = wotd.query_word(current_datetime.strftime('%Y-%m-%d'))

            # Find the subscribers who want to receive the Word of the Day at this hour
            current_second = current_hour * 3600
            weekday_names = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
            day_of_week_str = weekday_names[current_datetime.weekday()]
            subscribers_list = subscribers.query_next_subscribers(current_second, day_of_week=day_of_week_str)
            
            # Add debug logging to see what's happening
            log_info(f'Looking for subscribers at time: {current_second} seconds (hour {current_hour})')
            
            if not subscribers_list:
                log_info(f'No subscribers found for the current hour: {current_hour:02d}:00 UTC')
            else:
                log_info(f'Found {len(subscribers_list)} subscribers for the current hour: {current_hour:02d}:00 UTC')
                sent_places = []  # This is the solution to the problem of the bot sending the same message multiple times
                async with semaphore:
                    for subscriber in subscribers_list:
                        if subscriber in sent_places:
                            continue
                        if subscriber[1] is not None:  # If the subscriber is a user (DM)
                            try:
                                user = await client.fetch_user(subscriber[1])
                                dm_channel = await user.create_dm()
                                message = format_message(subscriber, wotd_data, current_datetime)
                                await dm_channel.send(message)
                                sent_places.append(subscriber)
                            except discord.errors.Forbidden:
                                log_warning(f'Could not send message to user {subscriber[1]}: Forbidden (DMs disabled)')
                                subscribers.unsubscribe(user_id=subscriber[1])  # Unsubscribe the user if DMs are disabled
                            except discord.errors.NotFound:
                                log_exception(f'Could not send message to user {subscriber[1]}: Not Found (User does not exist)')
                                subscribers.unsubscribe(user_id=subscriber[1])  # Unsubscribe the user if they do not exist
                            except discord.errors.RateLimited as rate_error:
                                # Sleep for the specified time and try again
                                retry_after = getattr(rate_error, 'retry_after', 1)
                                await asyncio.sleep(retry_after)
                                try:
                                    message = format_message(subscriber, wotd_data, current_datetime)
                                    await dm_channel.send(message)
                                    sent_places.append(subscriber)
                                except Exception as retry_error:
                                    log_exception(f'Error retrying message to user {subscriber[1]} after rate limit: {str(retry_error)}')
                                    continue
                            except Exception as e:
                                log_exception(f'Error sending message to user {subscriber[1]}: {str(e)}')
                                continue

                        else:  # If the subscriber is a guild channel
                            try:
                                guild = client.get_guild(subscriber[2])
                                if guild is None:
                                    log_warning(f'Guild {subscriber[2]} not found')
                                    subscribers.unsubscribe(guild_id=subscriber[2], channel_id=subscriber[3])
                                    continue
                                    
                                channel = guild.get_channel(subscriber[3])
                                if channel is None:
                                    log_warning(f'Channel {subscriber[3]} not found in guild {subscriber[2]}')
                                    subscribers.unsubscribe(guild_id=subscriber[2], channel_id=subscriber[3])
                                    continue
                                    
                                message = format_message(subscriber, wotd_data, current_datetime)
                                await channel.send(message)
                                sent_places.append(subscriber)
                            except discord.errors.Forbidden:
                                log_warning(f'Could not send message to channel {subscriber[3]} in guild {subscriber[2]}: Forbidden (Bot does not have permission)')
                                subscribers.unsubscribe(guild_id=subscriber[2], channel_id=subscriber[3])  # Unsubscribe the channel if the bot does not have permission
                            except discord.errors.NotFound:
                                log_exception(f'Could not send message to channel {subscriber[3]} in guild {subscriber[2]}: Not Found (Channel does not exist)')
                                subscribers.unsubscribe(guild_id=subscriber[2], channel_id=subscriber[3])  # Unsubscribe the channel if it does not exist
                            except discord.errors.RateLimited as rate_error:
                                # Sleep for the specified time and try again
                                retry_after = getattr(rate_error, 'retry_after', 1)
                                await asyncio.sleep(retry_after)
                                try:
                                    message = format_message(subscriber, wotd_data, current_datetime)
                                    await channel.send(message)
                                    sent_places.append(subscriber)
                                except Exception as retry_error:
                                    log_exception(f'Error retrying message to channel {subscriber[3]} after rate limit: {str(retry_error)}')
                                    continue
                            except Exception as e:
                                log_exception(f'Error sending message to channel {subscriber[3]} in guild {subscriber[2]}: {str(e)}')
                                continue

        except Exception as e:
            log_exception(f'Error in send_wotd task: {str(e)}')
            await asyncio.sleep(60)

async def send_message_to_subscriber(subscriber, message, date_str):
    '''Helper function to send message to a subscriber. Returns True if successful.'''
    async with semaphore:
        try:
            if subscriber[1] is not None:  # User DM
                try:
                    user = await client.fetch_user(subscriber[1])
                    dm_channel = await user.create_dm()
                    await dm_channel.send(message)
                    log_info(f'Sent WOTD to user {subscriber[1]} for date {date_str}')
                    return True
                except discord.errors.Forbidden:
                    log_warning(f'Could not send message to user {subscriber[1]}: Forbidden (DMs disabled)')
                    subscribers.unsubscribe(user_id=subscriber[1])
                    return False
                except discord.errors.NotFound:
                    log_warning(f'Could not send message to user {subscriber[1]}: Not Found (User does not exist)')
                    subscribers.unsubscribe(user_id=subscriber[1])
                    return False
                except Exception as e:
                    log_error(f'Error sending DM to user {subscriber[1]}: {str(e)}')
                    return False
            
            else:  # Guild channel
                try:
                    guild = client.get_guild(subscriber[2])
                    if guild is None:
                        log_warning(f'Guild {subscriber[2]} not found')
                        subscribers.unsubscribe(guild_id=subscriber[2], channel_id=subscriber[3])
                        return False
                        
                    channel = guild.get_channel(subscriber[3])
                    if channel is None:
                        log_warning(f'Channel {subscriber[3]} not found in guild {subscriber[2]}')
                        subscribers.unsubscribe(guild_id=subscriber[2], channel_id=subscriber[3])
                        return False
                        
                    await channel.send(message)
                    log_info(f'Sent WOTD to channel {subscriber[3]} in guild {subscriber[2]} for date {date_str}')
                    return True
                except discord.errors.Forbidden:
                    log_warning(f'Could not send message to channel {subscriber[3]}: Forbidden')
                    subscribers.unsubscribe(guild_id=subscriber[2], channel_id=subscriber[3])
                    return False
                except discord.errors.NotFound:
                    log_warning(f'Could not send message to channel {subscriber[3]}: Not Found')
                    subscribers.unsubscribe(guild_id=subscriber[2], channel_id=subscriber[3])
                    return False
                except Exception as e:
                    log_error(f'Error sending message to channel {subscriber[3]}: {str(e)}')
                    return False
        except Exception as e:
            log_exception(f'Unexpected error in send_message_to_subscriber: {str(e)}')
            return False

def run_client():
    client.run(TOKEN)

client_thread = threading.Thread(target=run_client)
client_thread.daemon = True
client_thread.start()