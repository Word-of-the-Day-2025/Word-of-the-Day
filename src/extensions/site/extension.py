import argon2
import asyncio
import base64
import datetime
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, send_from_directory, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import hashlib
from io import BytesIO
import json
import markdown
import os
from PIL import Image
import pytz
import requests
import secrets
import shutil
import sys
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
else:
    first_import = False

imported_discord_subscribers = False
try:
    from extensions.discord_bot import subscribers as discord_subscribers  # This is messy but it works
    import extensions.site.config_discord as config_discord
    asyncio.create_task(config_discord.expire_config_link())
    log_info('Discord bot extension imported successfully. Advanced configuration is available.')
    imported_discord_subscribers = True
except Exception as e:
    log_warning(f'Could not import discord bot extension. Advanced configuration will be unavailable. Error: {e}')
    imported_discord_subscribers = False

# Serve static files
app_www = Flask(__name__, static_folder='www/static', static_url_path='/www/static', template_folder='www/templates')
app_status = Flask(__name__, static_folder='status', static_url_path='')
app_api = Flask(__name__, static_folder='api', static_url_path='')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Load the admin password from .env
DOTENV_PATH = os.path.join(BASE_DIR, '.env')
load_dotenv(DOTENV_PATH)
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD')

# This is absolutely necessary
COCONUT_HASH = '45c3fa9f65a07255b7f5efb0b57ef1e41bc7d23a7fd7e6cd6844a9f7dcd2a11d'  # SHA-256 hash of coconut.jpg
if not os.path.exists(os.path.join(BASE_DIR, 'www', 'static', 'assets', 'img', 'coconut.jpg')):
    sys.exit(0)
if not hashlib.sha256(open(os.path.join(BASE_DIR, 'www', 'static', 'assets', 'img', 'coconut.jpg'), 'rb').read()).hexdigest() == COCONUT_HASH:
    sys.exit(0)

# Extract configuration variables from the JSON data
CONFIG_JSON = os.path.join(BASE_DIR, 'config.json')
with open(CONFIG_JSON, 'r') as f:
    CONFIG_JSON = json.load(f)  # Reusing the variable lol
# WWW configuration
WWW_ENABLED = CONFIG_JSON['www']['enabled']
WWW_PORT = CONFIG_JSON['www']['port']
WWW_THREADS = CONFIG_JSON['www']['threads']
WWW_BACKLOG = CONFIG_JSON['www']['backlog']
WWW_RATE_LIMIT_MAX_REQUESTS = CONFIG_JSON['www']['rate_limit']['max_requests']
WWW_RATE_LIMIT_WINDOW_MS = CONFIG_JSON['www']['rate_limit']['window_ms']
# API configuration
API_ENABLED = CONFIG_JSON['api']['enabled']
API_PORT = CONFIG_JSON['api']['port']
API_THREADS = CONFIG_JSON['api']['threads']
API_BACKLOG = CONFIG_JSON['api']['backlog']
API_RATE_LIMIT_MAX_REQUESTS = CONFIG_JSON['api']['rate_limit']['max_requests']
API_RATE_LIMIT_WINDOW_MS = CONFIG_JSON['api']['rate_limit']['window_ms']

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

index_word, index_ipa, index_pos, index_definition, index_date, current_date, day, day_suffix, month_name, year, date_formatted = '', '', '', '', '', '', '', '', '', '', ''

previous_wotds = None

has_more = False

def md_to_html(md_content: str) -> str:
    # Convert markdown with extra extensions for attributes
    html_content = markdown.markdown(
        md_content,
        extensions=['attr_list', 'fenced_code']
    )
    
    # Post-process HTML to wrap sections and add classes
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Add classes to headings
    for h1 in soup.find_all('h1'):
        h1['class'] = h1.get('class', []) + ['heading-primary']
    for h2 in soup.find_all('h2'):
        h2['class'] = h2.get('class', []) + ['heading-secondary']

    # Add class to all <code> tags for inline code
    for code_tag in soup.find_all('code'):
        code_tag['class'] = code_tag.get('class', []) + ['inline-code']
    
    # Wrap each h2 and its following content in a section
    sections = []
    current_section = None
    
    for element in list(soup.children):
        if element.name == 'h1':
            if current_section:
                sections.append(current_section)
            current_section = soup.new_tag('section', **{'class': 'article-section'})
            current_section.append(element.extract())
        elif current_section is not None:
            current_section.append(element.extract())
    
    if current_section:
        sections.append(current_section)
    
    # Rebuild soup with sections
    new_soup = BeautifulSoup('', 'html.parser')
    for section in sections:
        new_soup.append(section)
    
    html_content = str(new_soup)

    return html_content

# Load static articles
SETUP_DISCORD_HTML = md_to_html(open(os.path.join(BASE_DIR, 'www', 'static', 'articles', 'setup-discord.md'), 'r', encoding='utf-8').read())
TERMS_DISCORD_HTML = md_to_html(open(os.path.join(BASE_DIR, 'www', 'static', 'articles', 'terms-discord.md'), 'r', encoding='utf-8').read())
PRIVACY_DISCORD_HTML = md_to_html(open(os.path.join(BASE_DIR, 'www', 'static', 'articles', 'privacy-discord.md'), 'r', encoding='utf-8').read())

def get_device_type(user_agent: str) -> str:
    mobile_keywords = ['mobile', 'android', 'iphone', 'ipod', 'blackberry', 'iemobile', 'opera mini']
    wii_keywords = ['wii']  # Wii support in the big '25 is necessary
    if any(keyword in user_agent.lower() for keyword in mobile_keywords):
        device_type = 'mobile'
    elif any(keyword in user_agent.lower() for keyword in wii_keywords):
        device_type = 'wii'
    else:
        device_type = 'desktop'
    return device_type

def get_github_data(handle: str):
    url = f'https://api.github.com/users/{handle}'
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            return data
        else:
            log_warning(f'GitHub API returned status code {response.status_code}')
            return {
                'name': 'Gilgamesh',
                'html_url': f'{url}'
            }
    except Exception as e:
        log_error(f'Failed to fetch GitHub data: {e}')
        return {
            'name': 'Gilgamesh',
            'html_url': f'{url}'
        }

def generate_token():
    '''Generate a simple token for securing config links'''
    random_bytes = secrets.token_bytes(32)
    token = base64.urlsafe_b64encode(random_bytes).decode('utf-8').rstrip('=')
    return token

def get_wotd():
    global index_word, index_ipa, index_pos, index_definition, index_date, current_date
    current_wotd = wotd.query_word(date=wotd.current_date)
    if current_wotd:
        index_word = current_wotd['word']
        index_ipa = current_wotd['ipa']
        index_pos = current_wotd['pos']
        index_definition = current_wotd['definition']
        index_date = current_wotd['date']
        current_date = current_wotd['date']
    
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

def get_wotd_databases():
    global index_inject_html
    global databases_inject_html

    index_inject_html = ''
    databases_inject_html = ''

    # Read all files in BASE_PATH/dat/backups
    backup_path = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(sys.modules['__main__'].__file__)), '..', 'dat', 'backups'))
    databases = []
    if os.path.exists(backup_path):
        for filename in os.listdir(backup_path):
            if filename.endswith('.db'):
                # Get file size and format it
                file_path = os.path.join(backup_path, filename)
                file_size = os.path.getsize(file_path)
                if file_size < 1024:  # If you believe this should be 1,000, please don't make a pull request
                    file_size = f'{file_size} B'
                elif file_size < 1048576:
                    file_size = f'{round(file_size / 1024)} KB'
                elif file_size < 1073741824:
                    file_size = f'{round(file_size / 1048576)} MB'
                else:
                    file_size = f'{round(file_size / 1073741824)} GB'
                # Format the month to say the month name and year
                month = filename.split('_')[1].split('.')[0]
                month = datetime.datetime.strptime(month, '%Y-%m').strftime('%B %Y')
                # Append to databases list
                databases.append({
                    'name': filename,
                    'month': month,
                    'filename': filename,
                    'filesize': file_size
                })

    return databases

# Initialize these on startup
global github_data
get_wotd()
get_previous_wotd()
github_data = get_github_data('gaming-gaming')

def generate_config_discord_link(is_user: bool, user_id: int = None, guild_id: int = None, channel_id: int = None, name: str = None, avatar_url: str = None) -> str:
    token = ''
    while token == '' or token in config_discord.active_config_links:  # Ensure unique token, even though collision is absurdly unlikely to ever happen
        token = generate_token()

    # Cache avatar image if provided
    response = requests.get(avatar_url)
    image = Image.open(BytesIO(response.content)).convert('RGBA')
    image = image.resize((128, 128))
    image_bytes = BytesIO()
    image.save(image_bytes, format='PNG')
    image_bytes.seek(0)

    # If the same channel or user still has an active link, remove it
    for existing_token in list(config_discord.active_config_links.keys()):
        link_info = config_discord.active_config_links[existing_token]
        if (is_user and link_info.get('is_user') and link_info.get('user_id') == user_id) or (not is_user and not link_info.get('is_user') and link_info.get('guild_id') == guild_id and link_info.get('channel_id') == channel_id):
            del config_discord.active_config_links[existing_token]

    config_discord.active_config_links[token] = {
        'is_user': is_user,
        'user_id': user_id,
        'guild_id': guild_id,
        'channel_id': channel_id,
        'name': name,
        'expiration_time': datetime.datetime.now() + datetime.timedelta(minutes=10),
        'avatar_image': image_bytes
    }

    if is_user and user_id:
        link = f'{MAIN_DOMAIN}/config-discord?token={token}&user_id={user_id}'
    else:
        link = f'{MAIN_DOMAIN}/config-discord?token={token}&guild_id={guild_id}&channel_id={channel_id}'

    return link

@app_www.route('/')
def www_index():
    # Get data
    get_wotd()
    get_previous_wotd()
    device_type = get_device_type(request.headers.get('User-Agent', ''))
    accept_lang = request.headers.get('Accept-Language', 'en-US')
    date_format = 'Normal'
    if 'en-US' in accept_lang:
        date_format = 'American'  # God bless America :bald_eagle:

    wotd_text = ''
    if device_type == 'mobile':
        wotd_text = 'WOTD'
    else:
        wotd_text = 'Word of the Day'
    
    # Format date
    if current_date:
        date_obj = datetime.datetime.strptime(current_date, '%Y-%m-%d')
        day = str(date_obj.day)
        day_suffix = ''
        if day[-1] == '1' and day != '11':
            day_suffix = 'st'
        elif day[-1] == '2' and day != '12':
            day_suffix = 'nd'
        elif day[-1] == '3' and day != '13':
            day_suffix = 'rd'
        month_name = date_obj.strftime('%B')
        month = str(date_obj.month).zfill(2)
        year = str(date_obj.year)
        date = f'{day} {month_name} {year}'
        if date_format == 'American':
            date = f'{month_name} {day}{day_suffix}, {year}'
    else:
        date = '????-??-??'

    # Format date in previous WOTDs
    if previous_wotds:
        for wotd_entry in previous_wotds:
            try:
                # Store the original date BEFORE formatting
                original_date = wotd_entry['date']
                
                date_obj = datetime.datetime.strptime(original_date, '%Y-%m-%d')
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
                
                # Create a new key for the formatted date
                if date_format == 'American':
                    wotd_entry['date_formatted'] = f'{previous_month_name} {previous_day}{previous_day_suffix}, {previous_year}'
                else:
                    wotd_entry['date_formatted'] = f'{previous_day} {previous_month_name} {previous_year}'

                # Keep the original date in YYYY-MM-DD format
                wotd_entry['date'] = original_date
                wotd_entry['word'] = wotd_entry['word'][:1].upper() + wotd_entry['word'][1:]
                
            except ValueError as e:
                log_warning(f'Failed to parse date {wotd_entry["date"]}: {e}')
                wotd_entry['date_formatted'] = '????-??-??'

    # Render template
    return render_template('index.html',
        wotd=wotd_text,
        device_type=device_type,
        word=index_word[:1].upper() + index_word[1:] if index_word else '',
        ipa=index_ipa,
        pos=index_pos,
        definition=index_definition,
        date=index_date,
        current_date=current_date,
        previous_wotds=previous_wotds,
        has_more=has_more
    )

@app_www.route('/about')
def www_about():
    global github_data
    # Get data
    device_type = get_device_type(request.headers.get('User-Agent', ''))

    wotd_text = ''
    if device_type == 'mobile':
        wotd_text = 'WOTD'
    else:
        wotd_text = 'Word of the Day'
    
    # Render template
    return render_template('about.html',
        wotd=wotd_text,
        device_type=device_type,
        github_username=github_data.get('name'),
        github_url=github_data.get('html_url')
    )

@app_www.route('/subscribe', methods=['GET'])
def www_subscribe():
    # Get data
    device_type = get_device_type(request.headers.get('User-Agent', ''))

    wotd_text = ''
    if device_type == 'mobile':
        wotd_text = 'WOTD'
    else:
        wotd_text = 'Word of the Day'

    # Render template
    return render_template('subscribe.html',
        wotd=wotd_text,
        device_type=device_type
    )

@app_www.route('/databases', methods=['GET'])
def www_databases():
    # Get data
    device_type = get_device_type(request.headers.get('User-Agent', ''))
    databases = get_wotd_databases()

    wotd_text = ''
    if device_type == 'mobile':
        wotd_text = 'WOTD'
    else:
        wotd_text = 'Word of the Day'

    # Render template
    return render_template('databases.html',
        wotd=wotd_text,
        device_type=device_type,
        databases=databases
    )

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

@app_www.route('/articles/api-docs', methods=['GET'])
def www_api():
    # Detect device type based on User-Agent
    device_type = get_device_type(request.headers.get('User-Agent', ''))

    wotd_text = ''
    docs_text = ''
    if device_type == 'mobile':
        wotd_text = 'WOTD'
        docs_text = 'Docs'
    else:
        wotd_text = 'Word of the Day'
        docs_text = 'Documentation'

    return render_template('api-docs.html',
        wotd=wotd_text,
        docs=docs_text,
        device_type=device_type
    )

@app_www.route('/articles/terms-discord', methods=['GET'])
def www_discord_terms():
    # Detect device type based on User-Agent
    device_type = get_device_type(request.headers.get('User-Agent', ''))

    md_content = md_to_html(open(os.path.join(BASE_DIR, 'www', 'static', 'articles', 'terms-discord.md'), 'r', encoding='utf-8').read())

    return render_template('article.html',
        title='Terms of Service (Discord Bot)',
        content=md_content,
        device_type=device_type
    )

@app_www.route('/articles/privacy-discord', methods=['GET'])
def www_discord_privacy():
    # Detect device type based on User-Agent
    device_type = get_device_type(request.headers.get('User-Agent', ''))

    return render_template('article.html',
        title='Privacy Policy (Discord Bot)',
        content=PRIVACY_DISCORD_HTML,
        device_type=device_type
    )

@app_www.route('/articles/setup-discord', methods=['GET'])
def www_discord_setup():
    # Detect device type based on User-Agent
    device_type = get_device_type(request.headers.get('User-Agent', ''))

    return render_template('article.html',
        title='Discord Bot Setup',
        content=SETUP_DISCORD_HTML,
        device_type=device_type
    )

@app_www.route('/config-discord', methods=['GET'])
def www_config_discord():
    device_type = get_device_type(request.headers.get('User-Agent', ''))

    token = request.args.get('token')
    user_id = request.args.get('user_id')
    guild_id = request.args.get('guild_id')
    channel_id = request.args.get('channel_id')
    token_data = config_discord.active_config_links.get(token)

    # Use the provided get_subscriber_data function to get configuration
    subscriber_rows = discord_subscribers.get_subscriber_data(
        user_id=int(user_id) if user_id else None,
        guild_id=int(guild_id) if guild_id else None,
        channel_id=int(channel_id) if channel_id else None
    )
    configuration = None
    if subscriber_rows:
        # Map the row to a dict for easier access
        row = subscriber_rows[0]
        configuration = {
            'timezone': row[4],
            'time_sunday': str(row[5]).zfill(2),
            'include_date': bool(row[13]),
            'include_ipa': bool(row[14]),
            'is_dmy': bool(row[15]),
            'silent_message': bool(row[12]),
            'message_date_style': row[16]
        }
        # Convert time_sunday, which is minutes since midnight, to HH:MM format
        configuration_time = int(row[5])
        hours = configuration_time // 60
        minutes = configuration_time % 60
        configuration['time_sunday'] = f'{str(hours).zfill(2)}:{str(minutes).zfill(2)}'

    # Check access conditions and return 403 page if forbidden
    if token_data and ((token_data.get('is_user') and str(token_data.get('user_id')) == str(user_id)) or (not token_data.get('is_user') and str(token_data.get('guild_id')) == str(guild_id) and str(token_data.get('channel_id')) == str(channel_id))):
        return render_template('config-discord.html',
            device_type=device_type,
            timezones=pytz.all_timezones,
            discord_name=token_data.get('name'),
            discord_icon_base64=base64.b64encode(token_data.get('avatar_image').getvalue()).decode('utf-8'),
            selected_timezone=configuration.get('timezone') if configuration else 'UTC',
            single_time=configuration.get('time_sunday') if configuration else '00:00',
            include_date=configuration.get('include_date') if configuration else True,
            include_ipa=configuration.get('include_ipa') if configuration else True,
            is_dmy=configuration.get('is_dmy') if configuration else True,
            silent_mode=configuration.get('silent_message') if configuration else False,
            date_format=(
                {0: 'Long', 1: 'Medium', 2: 'ShortHyphen', 3: 'ShortSlash'}.get(configuration.get('message_date_style'), 'Medium')
                if configuration else 'Medium'
            )
        )
    else:
        return render_template('403.html',
            device_type=device_type
        ), 403

@app_www.route('/admin/append-word', methods=['GET', 'POST'])
def www_admin_append_word():
    device_type = get_device_type(request.headers.get('User-Agent', ''))

    # Verify admin password
    password = request.args.get('password')
    if password is None:
        return render_template('403.html',
            device_type=device_type
        ), 403
    ph = argon2.PasswordHasher()
    try:
        ph.verify(ADMIN_PASSWORD, password)
    except argon2.exceptions.VerifyMismatchError:
        return render_template('403.html',
            device_type=device_type
        ), 403
    except Exception as e:
        log_exception(f'Error verifying admin password: {e}')
        return render_template('403.html',
            device_type=device_type
        ), 403
    
    return render_template('admin-append-word.html',
        device_type=device_type
    )

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
    # Get data from JSON body
    data = request.json
    user_id = data.get('user_id')
    guild_id = data.get('guild_id')
    channel_id = data.get('channel_id')
    timezone = data.get('time_settings', {}).get('timezone')
    time = data.get('time_settings', {}).get('time')
    include_date = data.get('message_format', {}).get('include_date')
    include_ipa = data.get('message_format', {}).get('include_ipa')
    is_dmy = data.get('message_format', {}).get('display_dmy')
    silent_message = data.get('message_format', {}).get('silent_message')
    message_date_style = data.get('message_date_style')

    date_format_map = {
        'Long': 0,
        'Medium': 1,
        'ShortHyphen': 2,
        'ShortSlash': 3
    }
    date_value = date_format_map.get(message_date_style)

    token = data.get('token')

    # Check whether the user/guild is valid and the token is valid
    token_data = config_discord.active_config_links.get(token)
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
        timezone=timezone,
        # Set the same time for all days of the week, we don't have per-day scheduling yet
        time_sunday=time,
        time_monday=time,
        time_tuesday=time,
        time_wednesday=time,
        time_thursday=time,
        time_friday=time,
        time_saturday=time,
        include_date=include_date,
        include_ipa=include_ipa,
        is_dmy=is_dmy,
        silent_message=silent_message,
        message_date_style=date_value
    )

    return jsonify({'status': 'success'})

@app_www.route('/api/discord_reset_settings', methods=['POST'])
def www_discord_reset_settings():
    # Get data from JSON body
    data = request.json
    user_id = data.get('user_id')
    guild_id = data.get('guild_id')
    channel_id = data.get('channel_id')
    token = data.get('token')

    # Check whether the user/guild is valid and the token is valid
    token_data = config_discord.active_config_links.get(token)
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
        include_date=True,
        include_ipa=True,
        is_dmy=True,
        silent_message=False,
        message_date_style=1  # Medium
    )

    return jsonify({'status': 'success'})

@app_www.route('/api/discord_forget', methods=['POST'])
def www_discord_forget():
    # Get data from JSON body
    data = request.json
    user_id = data.get('user_id')
    guild_id = data.get('guild_id')
    channel_id = data.get('channel_id')
    token = data.get('token')

    # Check whether the user/guild is valid and the token is valid
    token_data = config_discord.active_config_links.get(token)
    if not token_data:
        return jsonify({'error': 'Invalid or expired token'}), 403
    if token_data.get('is_user'):
        if str(token_data.get('user_id')) != str(user_id):
            return jsonify({'error': 'User ID does not match token'}), 403
    else:
        if str(token_data.get('guild_id')) != str(guild_id) or str(token_data.get('channel_id')) != str(channel_id):
            return jsonify({'error': 'Guild ID or Channel ID does not match token'}), 403

    discord_subscribers.unsubscribe(user_id=user_id, guild_id=guild_id, channel_id=channel_id)
    if token in config_discord.active_config_links:
        del config_discord.active_config_links[token]

    return jsonify({'status': 'success'})

@app_www.route('/api/admin/append_word', methods=['POST'])
def www_api_admin_append_word():
    # Verify admin password
    data = request.json
    password = data.get('admin_password')
    if password is None:
        return jsonify({'error': 'Forbidden'}), 403
    ph = argon2.PasswordHasher()
    try:
        ph.verify(ADMIN_PASSWORD, password)
    except argon2.exceptions.VerifyMismatchError:
        return jsonify({'error': 'Forbidden'}), 403
    except Exception as e:
        log_exception(f'Error verifying admin password: {e}')
        return jsonify({'error': 'Forbidden'}), 403
    
    # Get data from JSON body
    word = data.get('word')
    ipa = data.get('ipa')
    pos = data.get('pos')
    definition = data.get('definition')
    date = data.get('date')

    # Check whether the word is already in the database
    word_exists = wotd.find_wotd(word_search=word, allow_future=True)  # Returns None if not found, which is falsy; returns dict if found, which is truthy
    if word_exists:
        return jsonify({'error': 'Word already exists in the database'}), 400

    try:
        wotd.append_word(
            word=word,
            ipa=ipa,
            pos=pos,
            definition=definition,
            date=date
        )
        get_wotd()  # Refresh current WOTD, in case the appended word is for today
        return jsonify({'status': 'success'})
    except Exception as e:
        log_exception(f'Error appending word: {e}')
        return jsonify({'error': 'An error occurred while appending the word'}), 500

@app_www.errorhandler(404)
def not_found(e):
    # Get data
    device_type = get_device_type(request.headers.get('User-Agent', ''))

    return render_template('404.html',
        device_type=device_type
    ), 404

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