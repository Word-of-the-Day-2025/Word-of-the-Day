import asyncio
import base64
import datetime
from flask import Flask, jsonify, send_from_directory, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import hashlib
import json
import os
import pytz
import requests
import secrets
import shutil
import threading
from torrentool.api import Torrent
from waitress import serve

from main import MAIN_DOMAIN, API_DOMAIN, VERSION
from logs import log_info, log_warning, log_error, log_exception
import wotd

# Detect whether this is the first time this file is being imported
global first_import
if 'first_import' not in globals():
    first_import = True
    log_info('Site extension imported for the first time')
else:
    first_import = False
    log_info('Site extension re-imported')

discord_subscribers = False
try:
    discord_subscribers = True
    from extensions.discord_bot import subscribers as discord_subscribers  # This is messy but it works
    log_info('Discord bot extension imported successfully. Advanced configuration is available.')
except Exception as e:
    discord_subscribers = False
    log_warning(f'Could not import discord bot extension. Advanced configuration will be unavailable. Error: {e}')

# Serve static files
app_www = Flask(__name__, static_folder='www', static_url_path='')
app_status = Flask(__name__, static_folder='status', static_url_path='')
app_api = Flask(__name__, static_folder='api', static_url_path='')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

cache_path = os.path.join(BASE_DIR, 'www', 'cache')
if os.path.exists(cache_path):
    try:
        shutil.rmtree(cache_path)  # Recursively delete the directory and its contents
        log_info('Cleared site cache folder on startup')
    except Exception as e:
        log_warning(f'Failed to clear site cache folder on startup: {e}')

# Extract configuration variables from the JSON data
CONFIG_JSON = os.path.join(BASE_DIR, 'config.json')
with open(CONFIG_JSON, 'r') as f:
    CONFIG_JSON = json.load(f)  # Reusing the variable lol
# WWW configuration
WWW_ENABLED = CONFIG_JSON['www']['enabled']
WWW_PORT = CONFIG_JSON['www']['port']
WWW_THREADS = CONFIG_JSON['www']['threads']
WWW_BACKLOG = CONFIG_JSON['www']['backlog']
WWW_RATE_LIMIT_MAX_REQUESTS = CONFIG_JSON['www']['rateLimit']['maxRequests']
WWW_RATE_LIMIT_WINDOW_MS = CONFIG_JSON['www']['rateLimit']['windowMs']
# API configuration
API_ENABLED = CONFIG_JSON['api']['enabled']
API_PORT = CONFIG_JSON['api']['port']
API_THREADS = CONFIG_JSON['api']['threads']
API_BACKLOG = CONFIG_JSON['api']['backlog']
API_RATE_LIMIT_MAX_REQUESTS = CONFIG_JSON['api']['rateLimit']['maxRequests']
API_RATE_LIMIT_WINDOW_MS = CONFIG_JSON['api']['rateLimit']['windowMs']

# Enable rate limits
limiter_www = Limiter(
    get_remote_address,
    app = app_www,
    default_limits=[f'{WWW_RATE_LIMIT_MAX_REQUESTS} per {WWW_RATE_LIMIT_WINDOW_MS // 1000} seconds']
)
limiter_api = Limiter(
    get_remote_address,
    app = app_api,
    default_limits=[f'{API_RATE_LIMIT_MAX_REQUESTS} per {API_RATE_LIMIT_WINDOW_MS // 1000} seconds']
)

global word, ipa, pos, definition, date, current_date, day, day_suffix, month_name, year, date_formatted
word, ipa, pos, definition, date, current_date, day, day_suffix, month_name, year, date_formatted = '', '', '', '', '', '', '', '', '', '', ''

global active_config_links
active_config_links = {}

global previous_wotds
previous_wotds = None

global has_more
has_more = False

global index_inject_html
index_inject_html = ''

global databases_inject_html
databases_inject_html = ''

global token_cleanup_timer
token_cleanup_timer = None

global timezone_options
timezone_options = ''

global time_options
time_options = '''<option value="0">00:00</option>
<option value="1800">00:30</option>
<option value="3600">01:00</option>
<option value="5400">01:30</option>
<option value="7200">02:00</option>
<option value="9000">02:30</option>
<option value="10800">03:00</option>
<option value="12600">03:30</option>
<option value="14400">04:00</option>
<option value="16200">04:30</option>
<option value="18000">05:00</option>
<option value="19800">05:30</option>
<option value="21600">06:00</option>
<option value="23400">06:30</option>
<option value="25200">07:00</option>
<option value="27000">07:30</option>
<option value="28800">08:00</option>
<option value="30600">08:30</option>
<option value="32400">09:00</option>
<option value="34200">09:30</option>
<option value="36000">10:00</option>
<option value="37800">10:30</option>
<option value="39600">11:00</option>
<option value="41400">11:30</option>
<option value="43200">12:00</option>
<option value="45000">12:30</option>
<option value="46800">13:00</option>
<option value="48600">13:30</option>
<option value="50400">14:00</option>
<option value="52200">14:30</option>
<option value="54000">15:00</option>
<option value="55800">15:30</option>
<option value="57600">16:00</option>
<option value="59400">16:30</option>
<option value="61200">17:00</option>
<option value="63000">17:30</option>
<option value="64800">18:00</option>
<option value="66600">18:30</option>
<option value="68400">19:00</option>
<option value="70200">19:30</option>
<option value="72000">20:00</option>
<option value="73800">20:30</option>
<option value="75600">21:00</option>
<option value="77400">21:30</option>
<option value="79200">22:00</option>
<option value="81000">22:30</option>
<option value="82800">23:00</option>
<option value="84600">23:30</option>
'''

# Generate timezone options for the dropdown
def generate_timezone_options():
    global timezone_options

    timezone_options = '<select name="timezone" id="timezone" class="selection">\n'
    for tz in pytz.all_timezones:
        if tz == 'UTC':
            timezone_options += f'<option value="{tz}" selected>{tz}</option>\n'
        else:
            timezone_options += f'<option value="{tz}">{tz}</option>\n'
    timezone_options += '</select>'
    return timezone_options

generate_timezone_options()

def generate_token():
    '''Generate a simple token for securing config links'''
    random_bytes = secrets.token_bytes(32)
    token = base64.urlsafe_b64encode(random_bytes).decode('utf-8').rstrip('=')
    return token

def generate_config_discord_link(is_user: bool, user_id: str = None, guild_id: str = None, channel_id: str = None):
    '''Generate a unique link for Discord bot advanced configuration'''
    token = generate_token()
    
    # Start a periodic cleanup if not already running
    schedule_cleanup_expired_tokens()
    
    if is_user:
        link = f'{MAIN_DOMAIN}/config_discord?user_id={user_id}&token={token}'
        # Store user-specific data with the token
        active_config_links[token] = {
            'is_user': True,
            'user_id': user_id,
            'guild_id': None,
            'channel_id': None,
            'expires_at': datetime.datetime.now(pytz.UTC) + datetime.timedelta(hours=1)
        }
    else:
        link = f'{MAIN_DOMAIN}/config_discord?guild_id={guild_id}&channel_id={channel_id}&token={token}'
        # Store guild-specific data with the token
        active_config_links[token] = {
            'is_user': False,
            'user_id': None,
            'guild_id': guild_id,
            'channel_id': channel_id,
            'expires_at': datetime.datetime.now(pytz.UTC) + datetime.timedelta(hours=1)
        }
    
    # Delete previous config links if they are for the same user/guild+channel
    tokens_to_delete = []
    for existing_token, data in active_config_links.items():
        if existing_token != token:
            if is_user and data.get('is_user') and data.get('user_id') == user_id:
                tokens_to_delete.append(existing_token)
            elif not is_user and not data.get('is_user') and data.get('guild_id') == guild_id and data.get('channel_id') == channel_id:
                tokens_to_delete.append(existing_token)

    # Remove the deleted tokens from the active_config_links dictionary
    for token_to_delete in tokens_to_delete:
        del active_config_links[token_to_delete]
        
    return link

def cleanup_expired_tokens():
    '''Remove expired tokens from the active_config_links dictionary'''
    now = datetime.datetime.now(pytz.UTC)
    expired_tokens = [token for token, data in active_config_links.items() 
                     if data['expires_at'] < now]
    
    # Create config_discord cache directory if it doesn't exist
    config_discord_path = os.path.join(BASE_DIR, 'www', 'cache', 'config_discord')
    os.makedirs(config_discord_path, exist_ok=True)
    
    for token in expired_tokens:
        try:
            is_user = active_config_links[token].get('is_user')
            user_id = active_config_links[token].get('user_id')
            guild_id = active_config_links[token].get('guild_id')
            channel_id = active_config_links[token].get('channel_id')
            filename = ''
            if is_user and user_id:
                filename = f'{user_id}'
            elif not is_user and guild_id and channel_id:
                filename = f'{guild_id}_{channel_id}'

            # Try to remove files but handle errors gracefully
            if filename:
                png_path = os.path.join(config_discord_path, f'{filename}.png')
                json_path = os.path.join(config_discord_path, f'{filename}.json')
                
                if os.path.exists(png_path):
                    try:
                        os.remove(png_path)
                    except Exception as e:
                        log_warning(f'Failed to remove {png_path}: {e}')
                        
                if os.path.exists(json_path):
                    try:
                        os.remove(json_path)
                    except Exception as e:
                        log_warning(f'Failed to remove {json_path}: {e}')
            
            del active_config_links[token]
        except Exception as e:
            log_warning(f'Error cleaning up token {token}: {e}')

def schedule_cleanup_expired_tokens():
    '''Schedule periodic cleanup of expired tokens'''
    global token_cleanup_timer
    
    # Check if we already have a cleanup timer running
    if token_cleanup_timer is None or not token_cleanup_timer.is_alive():
        # Run cleanup now and schedule next run
        cleanup_expired_tokens()
        token_cleanup_timer = threading.Timer(300, schedule_cleanup_expired_tokens)  # Run every 5 minutes
        token_cleanup_timer.daemon = True
        token_cleanup_timer.start()
        token_cleanup_timer.daemon = True
        token_cleanup_timer.start()

def get_wotd():
    global word, ipa, pos, definition, date, current_date, day, day_suffix, month_name, year, date_formatted
    word = wotd.word
    ipa = wotd.ipa
    pos = wotd.pos
    definition = wotd.definition
    date = wotd.date
    current_date = wotd.current_date
    
    # Parse the date correctly for YYYY-MM-DD format
    date_parts = current_date.split('-')
    if len(date_parts) == 3:
        year = date_parts[0]
        month = date_parts[1]
        day = date_parts[2]
        
        # Remove leading zeros from day
        day = day.lstrip('0')
        
        # Set the appropriate suffix for the day
        if day[-1] == '1' and day != '11':
            day_suffix = 'st'
        elif day[-1] == '2' and day != '12':
            day_suffix = 'nd'
        elif day[-1] == '3' and day != '13':
            day_suffix = 'rd'
        else:
            day_suffix = 'th'
            
        # Get the month name
        month_name = datetime.datetime.strptime(month, '%m').strftime('%B')
        
        # Format the complete date
        date_formatted = f'{month_name} {day}{day_suffix}, {year}'
    else:
        # Default values if date format is unexpected
        day, day_suffix, month_name, year = '', '', '', ''
        date_formatted = 'Date unavailable'

def get_previous_wotd():
    global previous_wotds
    global has_more
    query_result = wotd.query_previous(date=wotd.current_date, limit=3)
    if query_result and 'results' in query_result:
        previous_wotds = query_result['results']
        has_more = query_result.get('has_more', False)
        return {
            'previous_wotds': previous_wotds,
            'has_more': query_result.get('has_more', False)
        }
    else:
        previous_wotds = None
        has_more = query_result.get('has_more', False)
        return {
            'previous_wotds': None,
            'has_more': False
        }

def set_index_inject_html(is_mobile):
    global index_inject_html, word, ipa, pos, definition, date_formatted
    # HTML for Words of the Day
    inject_start_html = '''
        <main class="site-main container mobile-padding">
    '''
    header_0 = 'Today\'s Word of the Day:'
    header_1 = 'Previous Words of the Day:'
    if is_mobile:
        header_0 = 'Today\'s WOTD:'
        header_1 = 'Previous WOTDs:'
    if word:
        wotd_current_html = f'''
                <h1 class="heading">{header_0}</h1>
                <section class="card wotd-card">
                    <h1 id="word" class="word">
                        {word}
                        <span id="pos" class="pos pos-{pos.lower()}">{pos}</span>
                    </h1>
                    <p id="ipa" class="ipa">{ipa}</p>
                    <p id="definition" class="definition">
                        {definition}
                    </p>
                    <p id="date" class="date">{date_formatted}</p>
                </section>
        '''
    else:
        wotd_current_html = f'''
            <h1 class="heading">{header_0}</h1>
            <section class="no-wotd" style="text-align: center; margin: 1rem;">
                <p>No Word of the Day available at this time :(</p>
            </section>
        '''

    if previous_wotds:
        wotd_previous_html = f'<div class="divider-horizontal"></div><h1 class="heading">{header_1}</h1>'
        for wotd in previous_wotds:
            try:
                date_obj = datetime.datetime.strptime(wotd['date'], '%Y-%m-%d')
                previous_day = str(date_obj.day)
                
                # Add appropriate suffix
                if previous_day[-1] == '1' and previous_day != '11':
                    previous_day_suffix = 'st'
                elif previous_day[-1] == '2' and previous_day != '12':
                    previous_day_suffix = 'nd'
                elif previous_day[-1] == '3' and previous_day != '13':
                    previous_day_suffix = 'rd'
                else:
                    previous_day_suffix = 'th'
                    
                previous_month_name = date_obj.strftime('%B')
                previous_year = str(date_obj.year)
                previous_date_formatted = f'{previous_month_name} {previous_day}{previous_day_suffix}, {previous_year}'
                
            except ValueError as e:
                log_warning(f'Failed to parse date {wotd["date"]}: {e}')
                previous_date_formatted = 'Invalid date'
                
            wotd_previous_html += f'''
                <section class="card wotd-card">
                    <h1 id="word" class="word">
                        {wotd['word']}
                        <span id="pos" class="pos pos-{wotd['pos'].lower()}">{wotd['pos']}</span>
                    </h1>
                    <p id="ipa" class="ipa">{wotd['ipa']}</p>
                    <p id="definition" class="definition">
                        {wotd['definition']}
                    </p>
                    <p id="date" class="date">{previous_date_formatted}</p>
                </section>
            '''
    else:
        wotd_previous_html = ''

    if has_more:
        load_more = '''
            <section class="load-more">
                <button id="load-more-button" class="load-more-button">Load More</button>
            </section>
        '''
    else:
        load_more = ''

    index_inject_html = '''
        </main>
    '''
    index_inject_html = (inject_start_html + wotd_current_html + wotd_previous_html + load_more + index_inject_html)

def set_databases_inject_html(is_mobile):
    global databases_inject_html

    # List database backups
    backup_path = os.path.abspath(os.path.join(BASE_DIR, '..', '..', '..', 'dat', 'backups'))
    backups = []
    if os.path.exists(backup_path):
        for file in os.listdir(backup_path):
            if file.endswith('.db'):
                try:  # Get from file name
                    date_part = file.split('_')[-1].split('.')[0]  # Gets '2025-07'
                    year, month = date_part.split('-')  # Splits into '2025' and '07'
                    backups.append({
                        'name': file,
                        'month': int(month),
                        'year': int(year)
                    })
                except:  # Get from file modified time if name is invalid
                    mod_time = os.path.getmtime(os.path.join(backup_path, file))
                    mod_datetime = datetime.datetime.fromtimestamp(mod_time)
                    backups.append({
                        'name': file,
                        'month': mod_datetime.month,
                        'year': mod_datetime.year
                    })

    # If there are no backups, show a message
    if not backups:
        databases_inject_html = '''
            <main class="site-main container mobile-padding">
                <h1 class="heading">Databases</h1>
                <section class="no-wotd" style="text-align: center; margin: 1rem;">
                    <p>No database backups available at this time :(</p>
                </section>
            </main>
        '''
        return databases_inject_html

    # Start building the HTML
    databases_inject_html = '''
        <main class="site-main container mobile-padding">
            <h1 class="heading">Databases</h1>
    '''

    # Sort backups by year and month
    sorted_backups = sorted(backups, key=lambda x: (x['year'], x['month']), reverse=True)
    
    # Group backups by year
    current_year = None
    for i, backup in enumerate(sorted_backups):
        if backup['year'] != current_year:
            current_year = backup['year']
            databases_inject_html += f'''
                <h2 class="subheading">{current_year}:</h2>
            '''
            
        month_name = datetime.datetime(year=backup['year'], month=backup['month'], day=1).strftime('%B')
        is_last = i == len(sorted_backups) - 1
        margin_style = 'margin-bottom: 2rem;' if is_last else ''
        
        if is_mobile:
            databases_inject_html += f'''
                <section class="card backup-card" style="{margin_style}">
                    <p class="backup-title">{backup['name']}</p>
                    <p class="backup-size">{os.path.getsize(os.path.join(backup_path, backup['name'])) // 1024} KB</p>
                    <div style="flex-grow: 1;"></div>
                    <img src="/assets/svg/download.svg" alt="Download" class="icon" onclick="window.location.href='/databases/download/{backup['name']}'" style="cursor: pointer; height: 1.5rem;" />
                </section>
            '''
        else:
            databases_inject_html += f'''
                <section class="card backup-card" style="{margin_style}">
                    <p class="backup-title">{month_name} {backup['year']}: {backup['name']}</p>
                    <p class="backup-size">Size: {os.path.getsize(os.path.join(backup_path, backup['name'])) // 1024} KB</p>
                    <div style="flex-grow: 1;"></div>
                    <img src="/assets/svg/download.svg" alt="Download" class="icon" onclick="window.location.href='/databases/download/{backup['name']}'" style="cursor: pointer; height: 1.5rem;" />
                </section>
            '''

    # End the building of the HTML
    databases_inject_html += '''
        </main>
    '''

    return databases_inject_html

# Initialize these on startup
get_wotd()
get_previous_wotd()
set_index_inject_html(is_mobile=False)
set_databases_inject_html(is_mobile=False)

@app_www.route('/', methods=['GET'])
def www_index():
    global index_inject_html, word

    # Just do this every time the site gets served, TODO: Make this more efficient
    get_wotd()
    get_previous_wotd()

    # Detect device type based on User-Agent
    user_agent = request.headers.get('User-Agent', '').lower()
    if any(device in user_agent for device in ['mobile', 'android', 'iphone', 'ipad', 'ipod', 'blackberry', 'iemobile', 'opera mini']):
        styles = 'styles_mobile.css'
        set_index_inject_html(is_mobile=True)
    else:  # Fallback to desktop styles
        styles = 'styles.css'
        set_index_inject_html(is_mobile=False)

    # Read and modify the HTML content
    with open(os.path.join(app_www.static_folder, 'index.html'), 'r') as file:
        content = file.read()
    content = content.replace('{{ inject }}', index_inject_html)
    content = content.replace('{{ styles }}', styles)

    return content

@app_www.route('/subscribe', methods=['GET'])
def www_subscribe():
    # Detect device type based on User-Agent
    user_agent = request.headers.get('User-Agent', '').lower()
    if any(device in user_agent for device in ['mobile', 'android', 'iphone', 'ipad', 'ipod', 'blackberry', 'iemobile', 'opera mini']):
        styles = 'styles_mobile.css'
    else:
        styles = 'styles.css'

    with open(os.path.join(app_www.static_folder, 'subscribe.html'), 'r') as file:
        content = file.read()
    if styles == 'styles_mobile.css':
        content = content.replace('Subscribe to Word of the Day', 'Subscribe to WOTD')  # Shorten for mobile
    content = content.replace('{{ styles }}', styles)
    
    return content

@app_www.route('/about', methods=['GET'])
def www_about():
    # Detect device type based on User-Agent
    user_agent = request.headers.get('User-Agent', '').lower()
    if any(device in user_agent for device in ['mobile', 'android', 'iphone', 'ipad', 'ipod', 'blackberry', 'iemobile', 'opera mini']):
        styles = 'styles_mobile.css'
        
    else:  # Fallback to desktop styles
        styles = 'styles.css'

    with open(os.path.join(app_www.static_folder, 'about.html'), 'r') as file:
        content = file.read()
    if styles == 'styles_mobile.css':
        content = content.replace('About Word of the Day', 'About WOTD')  # Shorten for mobile
    content = content.replace('{{ styles }}', styles)

    return content

@app_www.route('/databases', methods=['GET'])
def www_databases():
    global databases_inject_html

    # Detect device type based on User-Agent
    user_agent = request.headers.get('User-Agent', '').lower()
    if any(device in user_agent for device in ['mobile', 'android', 'iphone', 'ipad', 'ipod', 'blackberry', 'iemobile', 'opera mini']):
        styles = 'styles_mobile.css'
        set_databases_inject_html(is_mobile=True)
    else:  # Fallback to desktop styles
        styles = 'styles.css'
        set_databases_inject_html(is_mobile=False)

    with open(os.path.join(app_www.static_folder, 'databases.html'), 'r') as file:
        content = file.read()
    content = content.replace('{{ inject }}', databases_inject_html)
    content = content.replace('{{ styles }}', styles)

    return content

@app_www.route('/databases/download/<path:filename>', methods=['GET'])
def download_database(filename):
    # Get the paths for both database
    backup_path = os.path.abspath(os.path.join(BASE_DIR, '..', '..', '..', 'dat', 'backups'))
    db_file = os.path.join(backup_path, filename)
    
    # Check if the file exists
    if os.path.exists(db_file) and filename.endswith('.db'):
        return send_from_directory(
            backup_path,
            filename,
            mimetype='application/x-sqlite3'
        )
    else:
        return 'Database file not found', 404

@app_www.route('/config_discord', methods=['GET'])
def configure_discord():
    token = request.args.get('token')
    user_id = request.args.get('user_id')
    guild_id = request.args.get('guild_id')
    channel_id = request.args.get('channel_id')
    
    # Detect device type for styling
    user_agent = request.headers.get('User-Agent', '').lower()
    if any(device in user_agent for device in ['mobile', 'android', 'iphone', 'ipad', 'ipod', 'blackberry', 'iemobile', 'opera mini']):
        styles = 'styles_mobile.css'
    else:
        styles = 'styles.css'

    # Check access conditions and return 403 page if forbidden
    if not token or ((not user_id) and (not guild_id or not channel_id)):
        with open(os.path.join(app_www.static_folder, '403.html'), 'r') as file:
            content = file.read()
        content = content.replace('{{ styles }}', styles)
        return content, 403
    
    # Verify the token
    token_data = active_config_links.get(token)
    if not token_data:
        with open(os.path.join(app_www.static_folder, '403.html'), 'r') as file:
            content = file.read()
        content = content.replace('{{ styles }}', styles)
        return content, 403
    
    # Verify the user_id matches
    if token_data.get('is_user'):
        if str(token_data.get('user_id')) != str(user_id):
            with open(os.path.join(app_www.static_folder, '403.html'), 'r') as file:
                content = file.read()
            content = content.replace('{{ styles }}', styles)
            return content, 403
    else:
        if str(token_data.get('guild_id')) != str(guild_id) or str(token_data.get('channel_id')) != str(channel_id):
            with open(os.path.join(app_www.static_folder, '403.html'), 'r') as file:
                content = file.read()
            content = content.replace('{{ styles }}', styles)
            return content, 403

    # Get the image filename based on whether it's a user or guild config
    filename = ''
    if token_data.get('is_user') and user_id:
        filename = f'{user_id}'
    elif not token_data.get('is_user') and guild_id and channel_id:
        filename = f'{guild_id}_{channel_id}'
    # Get the username from the cached json file
    user_name = None
    guild_name = None
    channel_name = None
    channel_info = ''
    if filename and os.path.exists(os.path.join(BASE_DIR, 'www', 'cache', 'config_discord', f'{filename}.json')):
        try:
            with open(os.path.join(BASE_DIR, 'www', 'cache', 'config_discord', f'{filename}.json'), 'r') as f:
                config_data = json.load(f)
                user_name = config_data.get('user_name')
                guild_name = config_data.get('guild_name')
                channel_name = config_data.get('channel_name')
        except Exception as e:
            log_warning(f'Failed to read cached config for {filename}: {e}')
    if user_name:
        discord_name = user_name
    else:
        discord_name = f'{guild_name}'
        channel_name = f'#{channel_name}'
        channel_info = f'<p class="channel-name">{channel_name}</p>' if channel_name else ''

    # Load and serve the Discord user configuration page
    with open(os.path.join(app_www.static_folder, 'configure_discord.html'), 'r') as file:
        content = file.read()
    content = content.replace('{{ user_id }}', user_id if user_id else '')
    content = content.replace('{{ guild_id }}', guild_id if guild_id else '')
    content = content.replace('{{ channel_id }}', channel_id if channel_id else '')
    content = content.replace('{{ token }}', token if token else '')
    content = content.replace('{{ timezone_options }}', timezone_options)
    content = content.replace('{{ time_options }}', time_options)
    content = content.replace('{{ styles }}', styles)
    content = content.replace('{{ image_filename }}', filename)
    content = content.replace('{{ discord_name }}', discord_name if discord_name else 'Unknown')
    content = content.replace('{{ channel_info }}', channel_info)
    
    return content

@app_www.route('/api', methods=['GET'])
def www_api():
    # Detect device type based on User-Agent
    user_agent = request.headers.get('User-Agent', '').lower()
    if any(device in user_agent for device in ['mobile', 'android', 'iphone', 'ipad', 'ipod', 'blackberry', 'iemobile', 'opera mini']):
        styles = 'styles_mobile.css'
    else:  # Fallback to desktop styles
        styles = 'styles.css'

    with open(os.path.join(app_www.static_folder, 'api.html'), 'r') as file:
        content = file.read()
    content = content.replace('{{ styles }}', styles)

    return content

# This is required for the load more button, the retro console versions of the site will use pages, though
@app_www.route('/api/query_previous', methods=['GET'])
def www_query_previous():
    date = request.args.get('date', default=wotd.current_date)
    limit = 3
    try:
        previous_wotds = wotd.query_previous(date, limit=limit)
        if previous_wotds:
            return jsonify(previous_wotds)
        else:
            return jsonify({'error': 'No previous words found'}), 404
    except Exception as e:
        log_exception(f'Error querying previous words: {e}')
        return jsonify({'error': 'An error occurred while querying previous words'}), 500

@app_www.route('/api/discord_save_settings', methods=['POST'])
def www_discord_save_settings():
    # Check content type to determine how to get the data
    if request.is_json:
        # Get data from JSON body
        data = request.json
        user_id = data.get('user_id')
        guild_id = data.get('guild_id')
        channel_id = data.get('channel_id')
        token = data.get('token')
    else:
        # Get data from form
        user_id = request.form.get('user_id')
        guild_id = request.form.get('guild_id')
        channel_id = request.form.get('channel_id')
        token = request.form.get('token')

    # Check whether the user/guild is valid and the token is valid
    token_data = active_config_links.get(token)
    if not token_data:
        return jsonify({'error': 'Invalid or expired token'}), 403
    if token_data.get('is_user'):
        if str(token_data.get('user_id')) != str(user_id):
            return jsonify({'error': 'User ID does not match token'}), 403
    else:
        if str(token_data.get('guild_id')) != str(guild_id) or str(token_data.get('channel_id')) != str(channel_id):
            return jsonify({'error': 'Guild ID or Channel ID does not match token'}), 403

    # Parse time settings based on data source
    if request.is_json:
        # Get data from the nested JSON structure
        time_settings = data.get('time_settings', {})
        timezone = time_settings.get('timezone', 'UTC')
        json_times = time_settings.get('times', {})
        times = {
            'Sunday': json_times.get('Sunday', '0'),
            'Monday': json_times.get('Monday', '0'),
            'Tuesday': json_times.get('Tuesday', '0'),
            'Wednesday': json_times.get('Wednesday', '0'),
            'Thursday': json_times.get('Thursday', '0'),
            'Friday': json_times.get('Friday', '0'),
            'Saturday': json_times.get('Saturday', '0')
        }
        wotd_for_utc = time_settings.get('wotd_for_utc', False)
        
        # Get message format settings
        message_format = data.get('message_format', {})
        include_date = message_format.get('include_date', True)
        include_ipa = message_format.get('include_ipa', True)
        display_dmy = message_format.get('display_dmy', True)
        send_updates = message_format.get('send_updates', True)
        message_date_style = data.get('message_date_style', 'medium')
    else:
        # Parse time settings from form data
        timezone = request.form.get('timezone', 'UTC')
        times = {
            'Sunday': request.form.get('time_sunday', '0'),
            'Monday': request.form.get('time_monday', '0'),
            'Tuesday': request.form.get('time_tuesday', '0'),
            'Wednesday': request.form.get('time_wednesday', '0'),
            'Thursday': request.form.get('time_thursday', '0'),
            'Friday': request.form.get('time_friday', '0'),
            'Saturday': request.form.get('time_saturday', '0')
        }
        
        # Parse boolean settings from form data
        wotd_for_utc = request.form.get('wotd_for_utc') == 'true'
        include_date = request.form.get('include_date') == 'true'
        include_ipa = request.form.get('include_ipa') == 'true'
        display_dmy = request.form.get('display_dmy') == 'true'
        send_updates = request.form.get('send_updates') == 'true'
        message_date_style = request.form.get('message_date_style', 'medium')

    style_to_int = {
        'long': 0,
        'medium': 1,
        'short': 2,
        'short_slash': 3
    }
    
    # Convert message_date_style to integer value
    message_date_style = style_to_int.get(message_date_style, 1)  # Default to 1 (medium) if invalid

    try:
        # Configure settings via discord_subscribers
        discord_subscribers.configure(
            user_id=user_id,
            guild_id=guild_id,
            channel_id=channel_id,
            timezone=timezone,
            time_sunday=times['Sunday'],
            time_monday=times['Monday'],
            time_tuesday=times['Tuesday'],
            time_wednesday=times['Wednesday'],
            time_thursday=times['Thursday'],
            time_friday=times['Friday'],
            time_saturday=times['Saturday'],
            send_wotd_in_utc=wotd_for_utc,
            include_date=include_date,
            include_ipa=include_ipa,
            is_dmy=display_dmy,
            send_updates=send_updates,
            message_date_style=message_date_style
        )
        return jsonify({'status': 'success'})
    except Exception as e:
        log_exception(f'Error saving Discord settings: {e}')
        return jsonify({'error': str(e)}), 500

@app_www.route('/api/discord_reset_settings', methods=['POST'])
def www_discord_reset_settings():
    # Check content type to determine how to get the data
    if request.is_json:
        # Get data from JSON body
        data = request.json
        user_id = data.get('user_id')
        guild_id = data.get('guild_id')
        channel_id = data.get('channel_id')
        token = data.get('token')
    else:
        # Get data from form
        user_id = request.form.get('user_id')
        guild_id = request.form.get('guild_id')
        channel_id = request.form.get('channel_id')
        token = request.form.get('token')

    # Check whether the user/guild is valid and the token is valid
    token_data = active_config_links.get(token)
    if not token_data:
        return jsonify({'error': 'Invalid or expired token'}), 403
    if token_data.get('is_user'):
        if str(token_data.get('user_id')) != str(user_id):
            return jsonify({'error': 'User ID does not match token'}), 403
    else:
        if str(token_data.get('guild_id')) != str(guild_id) or str(token_data.get('channel_id')) != str(channel_id):
            return jsonify({'error': 'Guild ID or Channel ID does not match token'}), 403
    
    discord_subscribers.configure(
        user_id=user_id,
        guild_id=guild_id,
        channel_id=channel_id,
        timezone='UTC',
        time_sunday='0',
        time_monday='0',
        time_tuesday='0',
        time_wednesday='0',
        time_thursday='0',
        time_friday='0',
        time_saturday='0',
        send_wotd_in_utc=False,
        include_date=True,
        include_ipa=True,
        is_dmy=True,
        send_updates=True,
        message_date_style=1  # Medium
    )

    return jsonify({'status': 'success'})

@app_www.route('/api/discord_forget_me', methods=['POST'])
def www_discord_forget_me():
    # Handle forgetting user data
    user_id = guild_id = channel_id = None
    if request.json.get('user_id'):
        user_id = request.json.get('user_id')
        guild_id = None
        channel_id = None
    else:
        user_id = None
        guild_id = request.json.get('guild_id')
        channel_id = request.json.get('channel_id')

    # Verify the token used is for the correct user/guild
    token = request.json.get('token')
    token_data = active_config_links.get(token)
    if not token_data:
        return jsonify({'error': 'Invalid or expired token'}), 403
    if token_data.get('is_user'):
        if str(token_data.get('user_id')) != str(user_id):
            return jsonify({'error': 'User ID does not match token'}), 403
    else:
        if str(token_data.get('guild_id')) != str(guild_id) or str(token_data.get('channel_id')) != str(channel_id):
            return jsonify({'error': 'Guild ID or Channel ID does not match token'}), 403
    
    # Delete the subscriber
    discord_subscribers.unsubscribe(
        user_id=user_id,
        guild_id=guild_id,
        channel_id=channel_id
    )
    filename = ''
    if user_id:
        filename = f'{user_id}'
    else:
        filename = f'{guild_id}_{channel_id}'
    os.remove(os.path.join(BASE_DIR, 'www', 'cache', f'config_discord', f'{filename}.png')) if filename and os.path.exists(os.path.join(BASE_DIR, 'www', 'cache', f'config_discord', f'{filename}.png')) else None
    os.remove(os.path.join(BASE_DIR, 'www', 'cache', f'config_discord', f'{filename}.json')) if filename and os.path.exists(os.path.join(BASE_DIR, 'www', 'cache', f'config_discord', f'{filename}.json')) else None

    # Delete the token to prevent reuse
    if token in active_config_links:
        del active_config_links[token]

    return jsonify({'status': 'success'})

@app_www.errorhandler(404)
def not_found(e):
    # Detect device type based on User-Agent
    user_agent = request.headers.get('User-Agent', '').lower()
    if any(device in user_agent for device in ['mobile', 'android', 'iphone', 'ipad', 'ipod', 'blackberry', 'iemobile', 'opera mini']):
        styles = 'styles_mobile.css'
    else:  # Fallback to desktop styles
        styles = 'styles.css'
    with open(os.path.join(app_www.static_folder, '404.html'), 'r') as file:
        content = file.read()
    content = content.replace('{{ styles }}', styles)
    return content, 404

@app_www.errorhandler(404)
def not_found(_e):
    # Detect device type based on User-Agent
    user_agent = request.headers.get('User-Agent', '').lower()
    if any(device in user_agent for device in ['mobile', 'android', 'iphone', 'ipad', 'ipod', 'blackberry', 'iemobile', 'opera mini']):
        styles = 'styles_mobile.css'
    else:  # Fallback to desktop styles
        styles = 'styles.css'
    with open(os.path.join(app_www.static_folder, '404.html'), 'r') as file:
        content = file.read()
    content = content.replace('{{ styles }}', styles)
    return content, 404

@app_api.route('/metadata', methods=['GET'])
def api_metadata():
    # Return metadata about the site and API
    return jsonify({
        'site_name': 'Word of the Day',
        'version': str(VERSION)  # Should always be a string, but if for some reason it's not, convert it
    })

@app_api.route('/query', methods=['GET'])
def api_query():
    date = request.args.get('date', default=wotd.current_date)
    try:
        # Parse the date and make it timezone-aware
        date_obj = datetime.datetime.strptime(date, '%Y-%m-%d')
        date_obj = pytz.UTC.localize(date_obj)  # Use localize instead of replace
        
        # Get current time in UTC
        current_time = datetime.datetime.now(pytz.UTC)
        
        if date_obj > current_time:
            return jsonify({'error': 'Date cannot be in the future'}), 400
    except ValueError:
        return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400
    
    try:
        word_data = wotd.query_word(date=date)
        if word_data:
            return jsonify(word_data)
        else:
            return jsonify({'error': 'Word not found for the specified date'}), 404
    except Exception as e:
        log_exception(f'Error querying word: {e}')
        return jsonify({'error': 'An error occurred while querying the word'}), 500

@app_api.route('/query_previous', methods=['GET'])
def api_query_previous():
    date = request.args.get('date', default=wotd.current_date)
    limit = request.args.get('limit', default=3, type=int)
    try:
        previous_wotds = wotd.query_previous(date, limit=limit, allow_future=False)
        if previous_wotds:
            return jsonify(previous_wotds)
        else:
            return jsonify({'error': 'No previous words found'}), 404
    except Exception as e:
        log_exception(f'Error querying previous words: {e}')
        return jsonify({'error': 'An error occurred while querying previous words'}), 500

@app_api.route('/find_wotd', methods=['GET'])
def api_find_wotd():
    word = request.args.get('word', default=None)
    if not word:
        return jsonify({'error': 'No word provided'}), 400
    try:
        result = wotd.find_wotd(word, False)
        if result:
            return jsonify(result)
        else:
            return jsonify({'error': 'Word not found'}), 404
    except Exception as e:
        log_exception(f'Error finding word: {e}')
        return jsonify({'error': 'An error occurred while finding the word'}), 500

if first_import:
    if WWW_ENABLED:
        threading.Thread(target=lambda: serve(app_www, host='0.0.0.0', port=WWW_PORT, threads=WWW_THREADS, backlog=WWW_BACKLOG), daemon=True).start()
    if API_ENABLED:
        threading.Thread(target=lambda: serve(app_api, host='0.0.0.0', port=API_PORT, threads=API_THREADS, backlog=API_BACKLOG), daemon=True).start()