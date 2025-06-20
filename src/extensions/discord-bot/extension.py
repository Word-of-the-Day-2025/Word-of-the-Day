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
import json
import math
import os
import platform
import psutil
import pytz
import re
import shlex
import sqlite3
from string import Template
import threading
import time

from logs import log_info, log_warning, log_error, log_exception
from . import subscribers
import wotd

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
                subscribers.subscribe(interaction.user.id, None, None, 0, True)
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
                    subscribers.subscribe(None, interaction.guild.id, interaction.channel.id, 0, True)
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
                       time='The time to send the Word of the Day (UTC).')
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
                subscribers.configure(interaction.user.id, None, None, time, dmy)
                
                # Format time for display in message
                time_str = f'<t:{time}:t>'
                
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
                    subscribers.configure(None, interaction.guild.id, interaction.channel.id, time, dmy)
                    
                    # Format time for display in message
                    time_str = f'<t:{time}:t>'
                    
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
        # Get the date from wotd.py (DD-MM-YYYY format)
        current_date = wotd.current_date
        day = current_date.split('-')[0]
        day = day.lstrip('0')
        month_name = datetime.datetime.strptime(current_date, '%d-%m-%Y').strftime('%B')
        year = current_date.split('-')[2]

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
@app_commands.describe(date='The date to query the Word of the Day for (DD-MM-YYYY format).')
async def query_date(interaction: discord.Interaction, date: str):
    try:
        # Validate the date format
        if not re.match(r'^\d{2}-\d{2}-\d{4}$', date):
            embed = create_embed('Error', 'Invalid date format. Please use DD-MM-YYYY.', discord.Color.red())
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
            day = date.split('-')[0]
            day = day.lstrip('0')
            month_name = datetime.datetime.strptime(date, '%d-%m-%Y').strftime('%B')
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
                month_name = datetime.datetime.strptime(date, '%d-%m-%Y').strftime('%B')
                date_message = f'{day} {month_name} {date.split('-')[2]}'
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
            datetime.datetime.strptime(date, '%d-%m-%Y')
        except ValueError:
            await ctx.send('Invalid date format. Please use DD-MM-YYYY.')
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
    date_tomorrow = (date + timedelta(days=1)).strftime('%d-%m-%Y')
    wotd_tomorrow = wotd.query_word(date_tomorrow)

    day = date_tomorrow.split('-')[0]
    day = day.lstrip('0')
    month_name = datetime.datetime.strptime(date_tomorrow, '%d-%m-%Y').strftime('%B')
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

        day = datetime.datetime.now(tz.tzutc()).day
        day_suffix = 'th'
        if day % 10 == 1 and day != 11:
            day_suffix = 'st'
        elif day % 10 == 2 and day != 12:
            day_suffix = 'nd'
        elif day % 10 == 3 and day != 13:
            day_suffix = 'rd'
        month_name = datetime.datetime.now(tz.tzutc()).strftime('%B')
        year = datetime.datetime.now(tz.tzutc()).year

        if subscriber[5] == True:  # If the subscriber prefers DD-MM-YYYY format
            current_date = f'{day} {month_name} {year}'
        else:
            current_date = f'{month_name} {day}{day_suffix}, {year}'

        message = f'Today is {current_date}, and the Word of the Day is "{wotd_data['word']}" ({wotd_data['ipa']}), which is defined as: ({wotd_data['pos']}) {wotd_data['definition']}'
        await ctx.send(message)
    except KeyError:
        await ctx.send('Subscription data is incomplete or invalid.')
    except Exception as e:
        log_exception(f'Error in test_send command: {str(e)}')

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
            next_hour = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
            sleep_time = (next_hour - now).total_seconds()
            log_info(f'Waiting for {sleep_time} seconds until the next hour...')
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
            
            # Format current date as string for the query
            current_date_str = current_datetime.strftime('%d-%m-%Y')
            
            # Get the Word of the Day for the current date
            wotd_data = wotd.query_word(current_date_str)
            if not wotd_data:
                log_warning(f'No Word of the Day found for {current_date_str}. Skipping this hour.')
                continue

            # Format the Word of the Day message
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
            
            month_name = current_datetime.strftime('%B')
            year = current_datetime.year

            message_dmy = f'Today is {day} {month_name} {year}, and the Word of the Day is "{wotd_data["word"]}" ({wotd_data["ipa"]}), which is defined as: ({wotd_data["pos"]}) {wotd_data["definition"]}'
            message_mdy = f'Today is {month_name} {day}{day_suffix}, {year}, and the Word of the Day is "{wotd_data["word"]}" ({wotd_data["ipa"]}), which is defined as: ({wotd_data["pos"]}) {wotd_data["definition"]}'

            # Find the subscribers who want to receive the Word of the Day at this hour
            current_second = current_hour * 3600
            subscribers_list = subscribers.query_next_subscribers(current_second)
            
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
                                if subscriber[5] == True:  # If the subscriber prefers DD-MM-YYYY format
                                    await dm_channel.send(message_dmy)
                                else:  # If the subscriber prefers MM-DD-YYYY format
                                    await dm_channel.send(message_mdy)
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
                                    if subscriber[5] == True:  # If the subscriber prefers DD-MM-YYYY format
                                        await dm_channel.send(message_dmy)
                                    else:  # If the subscriber prefers MM-DD-YYYY format
                                        await dm_channel.send(message_mdy)
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
                                    
                                if subscriber[5] == True:  # If the subscriber prefers DD-MM-YYYY format
                                    await channel.send(message_dmy)
                                else:
                                    await channel.send(message_mdy)
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
                                    if subscriber[5] == True:  # If the subscriber prefers DD-MM-YYYY format
                                        await channel.send(message_dmy)
                                    else:  # If the subscriber prefers MM-DD-YYYY format
                                        await channel.send(message_mdy)
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

def run_client():
    client.run(TOKEN)

client_thread = threading.Thread(target=run_client)
client_thread.daemon = True
client_thread.start()