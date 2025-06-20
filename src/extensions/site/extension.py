import asyncio
import datetime
from dotenv import load_dotenv
from flask import Flask, jsonify, send_from_directory, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import hashlib
import json
import os
import requests
import threading
from waitress import serve

from logs import log_info, log_warning, log_error, log_exception
import wotd

# Serve static files
app_www = Flask(__name__, static_folder='www', static_url_path='')
app_status = Flask(__name__, static_folder='status', static_url_path='')
app_api = Flask(__name__, static_folder='api', static_url_path='')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

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

# Load environment variables
load_dotenv()

# Retrieve hashed password from .env file
HASHED_PASSWORD = os.getenv('HASHED_PASSWORD')
if not HASHED_PASSWORD:
    raise ValueError("HASHED_PASSWORD is not set in the .env file")

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

global previous_wotds
previous_wotds = None

global has_more
has_more = False

global inject_html
inject_html = ''

def get_wotd():
    global word, ipa, pos, definition, date, current_date, day, day_suffix, month_name, year, date_formatted
    word = wotd.word
    ipa = wotd.ipa
    pos = wotd.pos
    definition = wotd.definition
    date = wotd.date
    current_date = wotd.current_date
    day = current_date.split('-')[0]
    day = day.lstrip('0')  # Remove leading zero
    if day[-1] == '1' and day != '11':
        day_suffix = 'st'
    elif day[-1] == '2' and day != '12':
        day_suffix = 'nd'
    elif day[-1] == '3' and day != '13':
        day_suffix = 'rd'
    else:
        day_suffix = 'th'
    month_name = datetime.datetime.strptime(current_date, '%d-%m-%Y').strftime('%B')
    year = current_date.split('-')[2]
    date_formatted = f'{month_name} {day}{day_suffix}, {year}'

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

def set_inject_html():
    global inject_html, word, ipa, pos, definition, date_formatted
    # HTML for Words of the Day
    inject_start_html = '''
        <main class="site-main container">
    '''
    if word:
        wotd_current_html = f'''
                <h1 class="heading">Today's Word of the Day:</h1>
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
        wotd_current_html = '''
            <h1 class="heading">Today's Word of the Day:</h1>
            <section class="no-wotd" style="text-align: center; margin: 1rem;">
                <p>No Word of the Day available at this time :(</p>
            </section>
        '''
    """
    wotd_previous_html = '''
            <div class="divider-horizontal"></div>
            <h1 class="heading">Previous Words of the Day:</h1>
    '''
    """
    if previous_wotds:
        wotd_previous_html = '<div class="divider-horizontal"></div><h1 class="heading">Previous Words of the Day:</h1>'
        for wotd in previous_wotds:
            previous_day = wotd['date'].split('-')[0]
            previous_day = previous_day.lstrip('0')
            if previous_day[-1] == '1' and previous_day != '11':
                previous_day_suffix = 'st'
            elif previous_day[-1] == '2' and previous_day != '12':
                previous_day_suffix = 'nd'
            elif previous_day[-1] == '3' and previous_day != '13':
                previous_day_suffix = 'rd'
            else:
                previous_day_suffix = 'th'
            previous_month_name = datetime.datetime.strptime(wotd['date'], '%d-%m-%Y').strftime('%B')
            previous_year = wotd['date'].split('-')[2]
            previous_date_formatted = f'{previous_month_name} {previous_day}{previous_day_suffix}, {previous_year}'
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

    inject_end_html = '''
        </main>
    '''
    inject_html = (inject_start_html + wotd_current_html + wotd_previous_html + load_more + inject_end_html)

# Initialize these on startup
get_wotd()
get_previous_wotd()
set_inject_html()

@app_www.route('/', methods=['GET'])
def www_index():
    global inject_html, word

    '''
    # Update word and inject_html if needed
    if word != wotd.word:
        get_wotd()
        set_inject_html()
    '''

    # Just do this every time the site gets served, TODO: Make this more efficient
    get_wotd()
    get_previous_wotd()
    set_inject_html()

    # Detect device type based on User-Agent
    user_agent = request.headers.get('User-Agent', '').lower()
    if any(device in user_agent for device in ['mobile', 'android', 'iphone', 'ipad', 'ipod', 'blackberry', 'iemobile', 'opera mini']):
        styles = 'styles_mobile.css'
    else:  # Fallback to desktop styles
        styles = 'styles.css'

    # Read and modify the HTML content
    with open(os.path.join(app_www.static_folder, 'index.html'), 'r') as file:
        content = file.read()
    content = content.replace('{{ inject }}', inject_html)
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
    content = content.replace('{{ styles }}', styles)

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

@app_www.route('/contact', methods=['GET'])
def www_contact():
    # Detect device type based on User-Agent
    user_agent = request.headers.get('User-Agent', '').lower()
    if any(device in user_agent for device in ['mobile', 'android', 'iphone', 'ipad', 'ipod', 'blackberry', 'iemobile', 'opera mini']):
        styles = 'styles_mobile.css'
    else:  # Fallback to desktop styles
        styles = 'styles.css'
    with open(os.path.join(app_www.static_folder, 'contact.html'), 'r') as file:
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

@app_www.route('/api/send-message', methods=['POST'])
@limiter_www.limit('1 per day')  # Limit to 1 message per day per IP
def www_send_message():
    try:
        data = request.get_json()
        if not data or 'message' not in data:
            return jsonify({'error': 'Invalid payload'}), 400
        if len(json.dumps(data).encode('utf-8')) > 1 * 1024 * 1024:  # 1MB limit
            return jsonify({'error': 'Payload too large, must be under 1MB'}), 413

        name = data.get('name', 'Anonymous')
        subject = data.get('subject', 'No Subject')
        message = data['message']
        messages_dir = os.path.join(BASE_DIR, 'messages')
        if not os.path.exists(messages_dir):
            os.makedirs(messages_dir)
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        message_file = os.path.join(messages_dir, f'message_{timestamp}.json')
        with open(message_file, 'w') as f:
            json.dump({'name': name, 'subject': subject, 'message': message, 'timestamp': timestamp}, f)
        log_info(f'Message received: {message}')
        return jsonify({'success': True, 'message': 'Message received successfully'}), 200
    except Exception as e:
        log_exception(f'Error processing message: {e}')
        return jsonify({'error': 'An error occurred while processing the message'}), 500

# Admin only read messages endpoint with password protection
@app_www.route('/api/read-messages/<password>', methods=['GET'])
def www_read_messages(password):
    try:
        # Replace 'your_password_here' with the actual password
        if hashlib.sha256(password.encode('utf-8')).hexdigest() != HASHED_PASSWORD:
            log_warning('Unauthorized access attempt to read messages')
            return jsonify({'error': 'Unauthorized access'}), 403

        messages_dir = os.path.join(BASE_DIR, 'messages')
        if not os.path.exists(messages_dir):
            return jsonify({'error': 'No messages found'}), 404
        messages = []
        for filename in os.listdir(messages_dir):
            if filename.endswith('.json'):
                with open(os.path.join(messages_dir, filename), 'r') as f:
                    message_data = json.load(f)
                messages.append(message_data)
        if messages:
            return jsonify(messages), 200
        else:
            return jsonify({'error': 'No messages found'}), 404
    except Exception as e:
        log_exception(f'Error reading messages: {e}')
        return jsonify({'error': 'An error occurred while reading messages'}), 500

@app_api.route('/query', methods=['GET'])
def api_query():
    date = request.args.get('date', default=wotd.current_date)
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
        previous_wotds = wotd.query_previous(date, limit=limit)
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
        result = wotd.find_wotd(word)
        if result:
            return jsonify(result)
        else:
            return jsonify({'error': 'Word not found'}), 404
    except Exception as e:
        log_exception(f'Error finding word: {e}')
        return jsonify({'error': 'An error occurred while finding the word'}), 500

if WWW_ENABLED:
    threading.Thread(target=lambda: serve(app_www, host='0.0.0.0', port=WWW_PORT, threads=WWW_THREADS, backlog=WWW_BACKLOG), daemon=True).start()
if API_ENABLED:
    threading.Thread(target=lambda: serve(app_api, host='0.0.0.0', port=API_PORT, threads=API_THREADS, backlog=API_BACKLOG), daemon=True).start()