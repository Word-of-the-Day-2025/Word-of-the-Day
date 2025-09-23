import asyncio
from datetime import datetime, timedelta
import os
import pytz
import sqlite3

from logs import log_info, log_warning, log_error

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'dat', 'wotd.db')

# Set timezone to UTC
tz = pytz.timezone('UTC')

# Get the current date in the UTC timezone
global current_date
current_date = datetime.now(tz).strftime('%Y-%m-%d')

# Initialize the Word of the Day variables
date = word = ipa = pos = definition = ''

def init_db():
    try:
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            c.execute('''CREATE TABLE IF NOT EXISTS words (
                date TEXT PRIMARY KEY,  -- YYYY-MM-DD format (ISO 8601)
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

def query_previous(date, limit=1, allow_future=False):
    if not date:
        raise ValueError('Date cannot be empty.')
    if limit > 8:
        raise ValueError('Limit cannot exceed 8.')
    
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        
        if not allow_future:
            date_obj = datetime.strptime(date, '%Y-%m-%d')
            date_obj = tz.localize(date_obj)  # Make it timezone-aware
            current_time = datetime.now(tz)
            
            if date_obj > current_time:
                raise ValueError('Date cannot be in the future.')

        # Query for previous entries before the given date
        c.execute('''SELECT date, word, ipa, pos, definition FROM words 
                     WHERE date < ? 
                     ORDER BY date DESC 
                     LIMIT ?''', (date, limit))
        results = c.fetchall()

        # Check if there are no more entries before the earliest date in the results
        if results:
            c.execute('''SELECT COUNT(*) FROM words 
                         WHERE date < ?''', (results[-1][0],))
            has_more = c.fetchone()[0] > 0
        else:
            has_more = False
            
        return {
            'results': [{'date': row[0], 'word': row[1], 'ipa': row[2], 'pos': row[3], 'definition': row[4]} for row in results],
            'has_more': has_more
        }

def find_wotd(word, allow_future=False):
    if not word:
        raise ValueError('Word cannot be empty.')
    
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        
        if not allow_future:
            current_date_str = datetime.now(tz).strftime('%Y-%m-%d')
            c.execute('''SELECT date, word, ipa, pos, definition FROM words 
                         WHERE word = ? AND date <= ?''', (word, current_date_str))
        else:
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
            # Query for the most recent date
            c.execute('''SELECT date FROM words 
                      ORDER BY date DESC 
                      LIMIT 1''')
            last_date = c.fetchone()
            if last_date:
                date = datetime.strptime(last_date[0], '%Y-%m-%d') + timedelta(days=1)
                date = date.strftime('%Y-%m-%d')
            else:
                date = datetime.now(tz).strftime('%Y-%m-%d')

    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute('''INSERT OR REPLACE INTO words (date, word, ipa, pos, definition)
                     VALUES (?, ?, ?, ?, ?)''', (date, word, ipa, pos, definition))
        conn.commit()

    return date

def save_wotd_database():
    ''' Save the database of WOTDs, only up to the last day of the previous month '''
    try:
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            # Get the last day of the previous month
            first_day_of_current_month = datetime.now(tz).replace(day=1)
            last_day_of_previous_month = first_day_of_current_month - timedelta(days=1)
            last_date_str = last_day_of_previous_month.strftime('%Y-%m-%d')
            last_ym_strr = last_day_of_previous_month.strftime('%Y-%m')  # For naming the backup file (YYYY-MM)

            # Query for all entries up to the last day of the previous month
            c.execute('''SELECT date, word, ipa, pos, definition FROM words 
                         WHERE date <= ? 
                         ORDER BY date ASC''', (last_date_str,))
            results = c.fetchall()

            # Save to a new database file
            if not os.path.exists(os.path.join(os.path.dirname(__file__), '..', 'dat', 'backups')):
                os.makedirs(os.path.join(os.path.dirname(__file__), '..', 'dat', 'backups'))
            backup_db_path = os.path.join(os.path.dirname(__file__), '..', 'dat', 'backups', f'wotd_{last_ym_strr}.db')
            with sqlite3.connect(backup_db_path) as backup_conn:
                backup_c = backup_conn.cursor()
                backup_c.execute('''CREATE TABLE IF NOT EXISTS words (
                    date TEXT PRIMARY KEY,
                    word TEXT NOT NULL,
                    ipa TEXT,
                    pos TEXT,
                    definition TEXT,
                    UNIQUE(date)
                )''')
                backup_c.executemany('''INSERT OR REPLACE INTO words (date, word, ipa, pos, definition)
                                        VALUES (?, ?, ?, ?, ?)''', results)
                backup_conn.commit()
            log_info(f'Saved WOTD database up to {last_date_str} to {backup_db_path}')
    except Exception as e:
        log_error(f'Failed to save WOTD database: {e}')

async def wotd_main_loop():
    global current_date, date, word, ipa, pos, definition

    # Initialize the database if it doesn't exist
    if not os.path.exists(DB_PATH) or os.path.getsize(DB_PATH) == 0:
        log_info('WOTD database is not initialized. Initializing...')
        try:
            init_db()
        except Exception as e:
            log_error(f'Failed to initialize database: {e}')

    current_date = datetime.now(tz).strftime('%Y-%m-%d')

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

        # Check whether it is a new month to save a database of the WOTDs for public access
        if datetime.now(tz).day == 1:
            save_wotd_database()

        await asyncio.sleep(time_until_next_day.total_seconds())  # Sleep until the next day
        current_date = (datetime.strptime(current_date, '%Y-%m-%d') + timedelta(days=1)).strftime('%Y-%m-%d')
        log_info(f'Current date updated to {current_date}')