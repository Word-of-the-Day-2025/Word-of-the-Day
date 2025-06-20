import asyncio
from datetime import datetime, timedelta
import json
import os
import pytz
import sqlite3

from logs import log_info, log_warning, log_error

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'dat', 'wotd.db')

# Load config.json
CONFIG_PATH = os.path.join(os.path.dirname(__file__), '..', 'config.json')
log_info(f'Loading config from {CONFIG_PATH}')
try:
    with open(CONFIG_PATH, 'r') as f:
        config = json.load(f)
    # Get update time and timezone from config, with defaults if not present
    update_time = config.get('updateTime', '00:00')
    timezone_str = config.get('timezone', 'utc')
    log_info(f'Loaded config: update time = {update_time}, timezone = {timezone_str}')
except Exception as e:
    log_error(f'Error loading config file: {e}')
    raise
tz = pytz.timezone(timezone_str)

# Get the current date in the UTC timezone
global current_date
current_date = datetime.now(tz).strftime('%d-%m-%Y')
log_info(f'Current date in {timezone_str} timezone: {current_date}')

# Initialize the Word of the Day variables
date = word = ipa = pos = definition = ''

def init_db():
    try:
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            c.execute('''CREATE TABLE IF NOT EXISTS words (
                date TEXT PRIMARY KEY,  -- DD-MM-YYYY format
                word TEXT NOT NULL,
                ipa TEXT,
                pos TEXT,
                definition TEXT,
                UNIQUE(date)
            )''')
        log_info('Database initialized successfully.')
    except Exception as e:
        log_error(f'Failed to initialize database: {e}')

def set_wotd(new_date, new_word, new_ipa, new_pos, new_definition):
    global date, word, ipa, pos, definition
    date = new_date
    word = new_word
    ipa = new_ipa
    pos = new_pos
    definition = new_definition
    log_info(f'Set Word of the Day: {date}, {word}, {ipa}, {pos}, {definition}')

def query_word(date):
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute('''SELECT word, ipa, pos, definition FROM words WHERE date = ?''', (date,))
        result = c.fetchone()
        if result:
            return {
                'date': date,
                'word': result[0],
                'ipa': result[1],
                'pos': result[2],
                'definition': result[3]
            }
        else:
            return None

def query_previous(date, limit=1):
    if not date:
        raise ValueError('Date cannot be empty.')
    if limit > 8:
        raise ValueError('Limit cannot exceed 8.')
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        # Ensure dates are compared correctly by converting them to a consistent format
        c.execute('''SELECT date, word, ipa, pos, definition FROM words 
                     WHERE strftime('%Y-%m-%d', substr(date, 7, 4) || '-' || substr(date, 4, 2) || '-' || substr(date, 1, 2)) < 
                           strftime('%Y-%m-%d', substr(?, 7, 4) || '-' || substr(?, 4, 2) || '-' || substr(?, 1, 2)) 
                     ORDER BY strftime('%Y-%m-%d', substr(date, 7, 4) || '-' || substr(date, 4, 2) || '-' || substr(date, 1, 2)) DESC 
                     LIMIT ?''', (date, date, date, limit))
        results = c.fetchall()
        # Check if there are no more entries before the earliest date in the results
        if results:
            c.execute('''SELECT COUNT(*) FROM words 
                         WHERE strftime('%Y-%m-%d', substr(date, 7, 4) || '-' || substr(date, 4, 2) || '-' || substr(date, 1, 2)) < 
                               strftime('%Y-%m-%d', substr(?, 7, 4) || '-' || substr(?, 4, 2) || '-' || substr(?, 1, 2))''', 
                      (results[-1][0], results[-1][0], results[-1][0]))
            has_more = c.fetchone()[0] > 0
        else:
            has_more = False
        return {
            'results': [{'date': row[0], 'word': row[1], 'ipa': row[2], 'pos': row[3], 'definition': row[4]} for row in results],
            'has_more': has_more
        }

def find_wotd(word):
    if not word:
        raise ValueError('Word cannot be empty.')
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute('''SELECT date, word, ipa, pos, definition FROM words WHERE word = ?''', (word,))
        result = c.fetchall()
        if result:
            return [{'date': row[0], 'word': row[1], 'ipa': row[2], 'pos': row[3], 'definition': row[4]} for row in result]
        else:
            return None

def append_word(date, word, ipa, pos, definition):
    if date is None:  # If date is None, use the date after the most recent one used in the database
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            c.execute('''SELECT date FROM words 
                      ORDER BY strftime('%Y-%m-%d', substr(date, 7, 4) || '-' || substr(date, 4, 2) || '-' || substr(date, 1, 2)) DESC 
                      LIMIT 1''')
            last_date = c.fetchone()
            if last_date:
                date = datetime.strptime(last_date[0], '%d-%m-%Y') + timedelta(days=1)
                date = date.strftime('%d-%m-%Y')
            else:
                date = datetime.now(tz).strftime('%d-%m-%Y')

    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute('''INSERT OR REPLACE INTO words (date, word, ipa, pos, definition)
                     VALUES (?, ?, ?, ?, ?)''', (date, word, ipa, pos, definition))
        conn.commit()

    return date

async def wotd_main_loop():
    global current_date, date, word, ipa, pos, definition

    # Initialize the database if it doesn't exist
    if not os.path.exists(DB_PATH) or os.path.getsize(DB_PATH) == 0:
        log_info('WOTD database is not initialized. Initializing...')
        try:
            init_db()
        except Exception as e:
            log_error(f'Failed to initialize database: {e}')

    current_date = datetime.now(tz).strftime('%d-%m-%Y')

    # Loop to get the Word of the Day every day at 12:00 AM UTC
    log_info('Starting Word of the Day loop...')
    while True:
        # Get the current date in the specified timezone
        try:
            word_data = query_word(current_date)
            date = word_data['date'] if word_data else ''
            word = word_data['word'] if word_data else ''
            ipa = word_data['ipa'] if word_data else ''
            pos = word_data['pos'] if word_data else ''
            definition = word_data['definition'] if word_data else ''
            if word_data:
                log_info(f'Word of the Day for {current_date}: {word_data}')
            else:
                log_warning(f'No Word of the Day found for {current_date}.')
        except Exception as e:
            log_error(f'Failed to query Word of the Day: {e}')
        time_until_next_day = (datetime.now(tz) + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0) - datetime.now(tz)
        log_info(f'Waiting for {time_until_next_day.total_seconds()} seconds until the next Word of the Day...')
        await asyncio.sleep(time_until_next_day.total_seconds())  # Sleep until the next day
        current_date = (datetime.strptime(current_date, '%d-%m-%Y') + timedelta(days=1)).strftime('%d-%m-%Y')
        log_info(f'Current date updated to {current_date}')