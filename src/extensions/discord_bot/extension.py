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
import io
from io import BytesIO
import json
import math
import os
from PIL import Image
import platform
import psutil
import pytz
import re
import requests
import shlex
import threading
import time
import zipfile

from logs import log_info, log_warning, log_error, log_exception
from . import subscribers
import wotd

# Attempt to import site (for advanced configuration, but if the site extension isn't present, just continue and allow errors on /config)
imported_site = False
try:
    from extensions.site import extension as site  # This is messy but it works
    imported_site = True
    log_info('Site extension imported successfully. Advanced configuration is available.')
except Exception as e:
    imported_site = False
    log_warning(f'Could not import site extension. Advanced configuration will be unavailable. Error: {e}')

colorama.init()

subscribers.init_db()  # Initialize the database for subscribers

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_JSON = os.path.join(BASE_DIR, 'config.json')
RATE_LIMIT = 45  # Requests allowed per second (slightly below the 50 requests per second limit)
SEMAPHORE = asyncio.Semaphore(RATE_LIMIT)
update_activity_count = 0
wotd_loop_count = 0
last_send_time = 0

# Load config.json
with open(CONFIG_JSON, 'r') as f:
    CONFIG_JSON = json.load(f)  # Reusing the variable lol
ADMINS = set(CONFIG_JSON['admins'])
MAX_SUBSCRIPTIONS_PER_GUILD = CONFIG_JSON['max_subscriptions_per_guild']

# Load the bot token
DOTENV_PATH = os.path.join(BASE_DIR, '.env')
load_dotenv(DOTENV_PATH)
TOKEN = os.getenv('DISCORD_TOKEN')

# Create a bot instance
intents = discord.Intents.default()
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
    },
    'forgotten': {
        'private': {
            'title': '**All your data has been deleted** from the bot.',
            'description': '''You will no longer receive the Word of the Day, and all your data has been removed.
            To subscribe again, send `/subscribe`.''',
            'color': discord.Color.dark_gray()
        },
        'guild': {
            'title': '**All data for this channel has been deleted** from the bot.',
            'description': '''This channel will no longer receive the Word of the Day, and all data has been removed.
            To subscribe again, send `/subscribe`.''',
            'color': discord.Color.dark_gray()
        },
        'already': {
            'private': {
                'title': 'No data found to delete.',
                'description': '''You are not subscribed to the Word of the Day, and no data was found.
                To subscribe, send `/subscribe`.''',
                'color': discord.Color.dark_red()
            },
            'guild': {
                'title': 'No data found to delete for this channel.',
                'description': '''This channel is not subscribed to the Word of the Day, and no data was found.
                To subscribe, send `/subscribe`.''',
                'color': discord.Color.dark_red()
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

@client.tree.command(name='config', description='Generate a link for configuration.')
async def config(interaction: discord.Interaction):
    if imported_site:
        user_id = guild_id = channel_id = name = avatar_url = None
        if interaction.channel.type == discord.ChannelType.private:
            user_id = interaction.user.id
            guild_id = None
            channel_id = None
            name = interaction.user.display_name
            avatar_url = interaction.user.avatar.url if interaction.user.avatar else None
        else:
            user_id = None
            guild_id = interaction.guild.id
            channel_id = interaction.channel.id
            name = f'{interaction.guild.name}/#{interaction.channel.name}'
            avatar_url = interaction.guild.icon.with_format('png').url if interaction.guild.icon else None
        if subscribers.query_subscribed(user_id=user_id, guild_id=guild_id, channel_id=channel_id):
            if interaction.channel.type == discord.ChannelType.private:
                link = site.generate_config_discord_link(is_user=True, user_id=interaction.user.id, name=name, avatar_url=avatar_url)
            elif interaction.channel.type == discord.ChannelType.text or interaction.channel.type == discord.ChannelType.news:
                if interaction.user.guild_permissions.manage_channels:
                    link = site.generate_config_discord_link(is_user=False, guild_id=interaction.guild.id, channel_id=interaction.channel.id, name=name, avatar_url=avatar_url)
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
        embed = create_embed('Advanced Configuration', f'Click [here]({link}) to configure advanced settings. This link will expire in 10 minutes.\n\n-# Do not share this link with anyone you do not want to alter your WOTD settings.', discord.Color.green())
        await interaction.response.send_message(embed=embed, ephemeral=True)
    else:
        embed = create_embed('Error', 'Advanced configuration is unavailable.', discord.Color.red())
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
                    subscribers.configure(
                        None,
                        interaction.guild.id,
                        interaction.channel.id,
                        'UTC',
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        False,
                        True,
                        True,
                        True,
                        1
                    )
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

@client.tree.command(name='forget_me', description='Delete all your data from the bot.')  # Functionally the same as /unsubscribe
async def forget_me(interaction: discord.Interaction):
    try:
        if interaction.channel.type == discord.ChannelType.private:  # If the command was sent in a DM
            if subscribers.query_subscribed(interaction.user.id, None, None):
                subscribers.unsubscribe(interaction.user.id, None, None)
                embed = create_embed(**embed_templates['forgotten']['private'])
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                embed = create_embed(**embed_templates['forgotten']['already']['private'])
                await interaction.response.send_message(embed=embed, ephemeral=True)
        elif interaction.channel.type == discord.ChannelType.text or interaction.channel.type == discord.ChannelType.news:  # If the command was sent in a text channel
            if interaction.user.guild_permissions.manage_channels:
                if subscribers.query_subscribed(None, interaction.guild.id, interaction.channel.id):
                    subscribers.unsubscribe(None, interaction.guild.id, interaction.channel.id)
                    embed = create_embed(**embed_templates['forgotten']['guild'])
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                else:
                    embed = create_embed(**embed_templates['forgotten']['already']['guild'])
                    await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                embed = create_embed('Error', 'You must have the `Manage Channels` permission to forget this channel.', discord.Color.red())
                await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            embed = create_embed('Error', 'This command can only be used in a DM or a text channel.', discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
    except Exception as e:
        log_exception(f'Error in forget_me command: {str(e)}')
        try:
            await interaction.response.send_message('An error occurred while processing your request.', ephemeral=True)
        except:
            pass

@client.tree.command(name='request_data', description='Request a copy of all your data stored by the bot.')
async def request_data(interaction: discord.Interaction):
    try:
        if interaction.channel.type == discord.ChannelType.private:  # If the command was sent in a DM
            subscriber_data = subscribers.get_subscriber_data(interaction.user.id, None, None)
        else: # If the command was sent in a text channel
            subscriber_data = subscribers.get_subscriber_data(None, interaction.guild.id, interaction.channel.id)
        if subscriber_data:
            # Gather all subscription data
            data_dict = {
                'user_id': subscriber_data[0][1],
                'guild_id': subscriber_data[0][2],
                'channel_id': subscriber_data[0][3],
                'timezone': subscriber_data[0][4],
                'time_sunday': subscriber_data[0][5],
                'time_monday': subscriber_data[0][6],
                'time_tuesday': subscriber_data[0][7],
                'time_wednesday': subscriber_data[0][8],
                'time_thursday': subscriber_data[0][9],
                'time_friday': subscriber_data[0][10],
                'time_saturday': subscriber_data[0][11],
                'send_wotd_in_utc': subscriber_data[0][12],
                'include_date': subscriber_data[0][13],
                'include_ipa': subscriber_data[0][14],
                'is_dmy': subscriber_data[0][15],
                'message_date_style': subscriber_data[0][16]
            }
            # Serialize JSON
            json_bytes = json.dumps(data_dict, indent=4).encode('utf-8')
            # Create in-memory zip
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                zip_file.writestr('subscription_data.json', json_bytes)
            zip_buffer.seek(0)
            # Send as attachment
            file = discord.File(fp=zip_buffer, filename='subscription_data.zip')
            await interaction.response.send_message(
                content='Here is your data as a zip file:',
                file=file,
                ephemeral=True
            )
        else:
            embed = create_embed('Error', 'You are not subscribed to the Word of the Day; we have no data for you.', discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
    except Exception as e:
        log_exception(f'Error in request_data command: {str(e)}')
        try:
            await interaction.response.send_message('An error occurred while processing your request.', ephemeral=True)
        except:
            pass

def format_message(user_id, guild_id, channel_id):
    subscriber_config = subscribers.get_subscriber_data(user_id, guild_id, channel_id)
    if not subscriber_config:
        return None
    subscriber_config = subscriber_config[0]  # Get the first row from the result
    timezone_str = subscriber_config[4]  # Timezone string
    send_time = subscriber_config[5]  # time_sunday (index 5), stored in minutes
    include_date = subscriber_config[13]  # Bool for include_date
    include_ipa = subscriber_config[14]  # Bool for include_ipa
    is_dmy = subscriber_config[15]  # Bool for is_dmy
    message_date_style = subscriber_config[16]  # Nibble for message_date_style

    # Get date information from the subscribers timezone and send_time
    timezone = pytz.timezone(timezone_str)
    now_in_tz = datetime.datetime.now(timezone)
    send_hour = send_time // 60
    send_minute = send_time % 60
    send_datetime_in_tz = now_in_tz.replace(hour=send_hour, minute=send_minute, second=0, microsecond=0)
    if now_in_tz < send_datetime_in_tz:
        send_datetime_in_tz -= timedelta(days=1)
    year_number = send_datetime_in_tz.year
    month_number = send_datetime_in_tz.month
    month_name = send_datetime_in_tz.strftime('%B')
    weekday_name = send_datetime_in_tz.strftime('%A')
    day_number = send_datetime_in_tz.day

    # Get the Word of the Day for the date the subscriber is receiving it in their time zone
    # TODO: If anybody reading through this code cares this much about micro-optimization, this could be optimized to avoid querying the database every time
    wotd_date_str = send_datetime_in_tz.strftime('%Y-%m-%d')
    subscriber_wotd = wotd.query_word(date=wotd_date_str)

    message = ''

    if include_date:
        message += 'Today is '
        if message_date_style == 0:  # Long
            if is_dmy:
                message += f'{weekday_name}, {day_number} {month_name} {year_number}, '
            else:
                day_suffix = 'th'
                if day_number in [1, 21, 31]:
                    day_suffix = 'st'
                elif day_number in [2, 22]:
                    day_suffix = 'nd'
                elif day_number in [3, 23]:
                    day_suffix = 'rd'
                message += f'{weekday_name}, {month_name} {day_number}{day_suffix}, {year_number}, '
        elif message_date_style == 1:  # Medium
            if is_dmy:
                message += f'{day_number} {month_name} {year_number}, '
            else:
                day_suffix = 'th'
                if day_number in [1, 21, 31]:
                    day_suffix = 'st'
                elif day_number in [2, 22]:
                    day_suffix = 'nd'
                elif day_number in [3, 23]:
                    day_suffix = 'rd'
                message += f'{month_name} {day_number}{day_suffix}, {year_number}, '
        elif message_date_style == 2:  # Short, hyphenated
            if is_dmy:
                message += f'{day_number:02}-{month_number:02}-{year_number}, '
            else:
                message += f'{month_number:02}-{day_number:02}-{year_number}, '
        elif message_date_style == 3:  # Short, slashed
            if is_dmy:
                message += f'{day_number:02}/{month_number:02}/{year_number}, '
            else:
                message += f'{month_number:02}/{day_number:02}/{year_number}, '
        message += f'and the Word of the Day is "{subscriber_wotd["word"]}"'
    else:
        message += f'The Word of the Day is "{subscriber_wotd["word"]}"'

    if include_ipa:
        message += f' ({subscriber_wotd["ipa"]}), '
    else:
        message += ', '
    
    message += f'which is defined as: ({subscriber_wotd["pos"]}) {subscriber_wotd["definition"]}'
    if subscriber_wotd["word"]:  # Only add the link if there is a word
        return message

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

        # Create the countdown for the activity status
        countdown = math.ceil(sleep_duration / 60)
        countdown_hours = countdown // 60
        countdown_minutes = countdown % 60
        countdown_str = ''
        if countdown_hours > 0:
            if countdown_hours == 1:
                countdown_str += f'{countdown_hours} hour'
            else:
                countdown_str += f'{countdown_hours} hours'
            countdown_str += ', '
        if countdown_minutes == 1:
            countdown_str += f'{countdown_minutes} minute'
        else:
            countdown_str += f'{countdown_minutes} minutes'

        # Update the bot's activity status
        if countdown == 1440:
            activity_state = f'WOTD: {wotd.word}'
        else:
            activity_state = f'Next word in {countdown_str}.'
        activity = discord.Activity(
            name='WOTD',
            type=discord.ActivityType.custom,
            state=activity_state
        )
        await client.change_presence(activity=activity)  # Update the bot's activity status

        # Sleep until the next second is 00
        await asyncio.sleep(60 - now.second)

async def send_wotd_loop():
    '''The main loop that sends the Word of the Day to subscribers at their scheduled times.'''
    global wotd_loop_count, last_send_time
    wotd_loop_count += 1
    if wotd_loop_count != 1:  # This may happen if the bot is reloaded
        return

    log_info('Word of the Day Discord Bot loop started')

    while True:
        try:
            if subscribers.count_subscribers() == 0:
                log_info('No subscribers found, waiting until next minute to check again')
                await asyncio.sleep(60)
                continue
            else:
                subscribers_to_notify = []  # Initialize list of subscribers to notify this minute
                # Make a list of the current minute and the date for every timezone in pytz
                timezone_times = {}
                for tz_name in pytz.all_timezones:
                    timezone = pytz.timezone(tz_name)
                    now_in_tz = datetime.datetime.now(timezone)
                    current_weekday = now_in_tz.weekday()  # 0=Monday, 6=Sunday
                    current_time_minute = now_in_tz.hour * 60 + now_in_tz.minute  # Total minutes since midnight, 0-1439
                    timezone_times[tz_name] = (current_weekday, current_time_minute)
                
                # Get every single subscriber, check their timezone, and see if they match the current time
                all_subscribers = subscribers.get_subscriber_data()  # Get fresh data from DB
                for subscriber in all_subscribers:
                    subscriber_tz_str = subscriber[4]  # Timezone string
                    current_weekday, current_time_minute = timezone_times[subscriber_tz_str]
                    
                    # Since we don't have per-day scheduling yet, just use Sunday's time for all days
                    scheduled_time_minutes = subscriber[5]  # time_sunday (index 5) - stored in MINUTES
                    
                    if scheduled_time_minutes is None:
                        continue
                    
                    # Compare minutes directly
                    if scheduled_time_minutes == current_time_minute:
                        subscribers_to_notify.append(subscriber)
                
                # Send messages with rate limiting
                for subscriber in subscribers_to_notify:
                    async with SEMAPHORE:  # Rate limit: max 45 concurrent requests
                        try:
                            subscriber_user_id = subscriber[1]
                            subscriber_guild_id = subscriber[2]
                            subscriber_channel_id = subscriber[3]
                            
                            if subscriber_user_id is not None:
                                user = await client.fetch_user(subscriber_user_id)
                                wotd_message = format_message(subscriber_user_id, None, None)
                                subscriber_config = subscribers.get_subscriber_data(subscriber_user_id, None, None)
                                if wotd_message:
                                    if subscriber_config and subscriber_config[0][12]:  # Silent message
                                        await user.send(wotd_message, silent=True)
                                    else:
                                        await user.send(wotd_message)
                                    # Small delay between messages to avoid hitting rate limits
                                    await asyncio.sleep(0.1)
                            else:
                                guild = client.get_guild(subscriber_guild_id)
                                if not guild:
                                    subscribers.unsubscribe(None, subscriber_guild_id, subscriber_channel_id)
                                    continue
                                    
                                channel = guild.get_channel(subscriber_channel_id)
                                if not channel:
                                    subscribers.unsubscribe(None, subscriber_guild_id, subscriber_channel_id)
                                    continue
                                    
                                wotd_message = format_message(None, subscriber_guild_id, subscriber_channel_id)
                                if wotd_message:
                                    await channel.send(wotd_message)
                                    # Small delay between messages
                                    await asyncio.sleep(0.1)
                                    
                        except discord.errors.Forbidden:
                            # Bot doesn't have permission, unsubscribe
                            if subscriber_user_id is not None:
                                subscribers.unsubscribe(subscriber_user_id, None, None)
                            else:
                                subscribers.unsubscribe(None, subscriber_guild_id, subscriber_channel_id)
                        except discord.errors.NotFound:
                            # User/channel not found, unsubscribe
                            if subscriber_user_id is not None:
                                subscribers.unsubscribe(subscriber_user_id, None, None)
                            else:
                                subscribers.unsubscribe(None, subscriber_guild_id, subscriber_channel_id)
                        except Exception as e:
                            continue
                            
        except Exception as e:
            log_exception(f'Error in send_wotd_loop: {str(e)}')
            await asyncio.sleep(60)
            continue

        # Wait until the start of the next minute
        now = datetime.datetime.now(datetime.timezone.utc)
        sleep_duration = 60 - now.second - now.microsecond / 1_000_000
        await asyncio.sleep(sleep_duration)

def run_client():
    client.run(TOKEN)

client_thread = threading.Thread(target=run_client)
client_thread.daemon = True
client_thread.start()
