import os
import sqlite3

from logs import log_info, log_warning, log_error, log_exception

SUBSCRIBERS_DB_PATH = os.path.join(os.path.dirname(__file__), 'subscribers.db')

def init_db():
    try:
        with sqlite3.connect(SUBSCRIBERS_DB_PATH) as conn:
            c = conn.cursor()
            c.execute('''CREATE TABLE IF NOT EXISTS subscribers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                guild_id INTEGER,
                channel_id INTEGER,
                time INTEGER DEFAULT 0,
                dmy BOOLEAN DEFAULT 1
            )''')
            conn.commit()
    except Exception as e:
        log_error(f'Failed to initialize database: {e}')

def query_subscribed(user_id=None, guild_id=None, channel_id=None):
    try:
        with sqlite3.connect(SUBSCRIBERS_DB_PATH) as conn:
            c = conn.cursor()
            query = 'SELECT * FROM subscribers WHERE 1=1'
            params = []

            if user_id is not None:
                query += ' AND user_id = ?'
                params.append(user_id)
            if guild_id is not None:
                query += ' AND guild_id = ?'
                params.append(guild_id)
            if channel_id is not None:
                query += ' AND channel_id = ?'
                params.append(channel_id)

            c.execute(query, params)
            result = c.fetchall()
            return True if result else False
    except Exception as e:
        log_error(f'Failed to query database: {e}')
        return False

def query_guild_over_limit(guild_id, max_subscriptions):
    try:
        with sqlite3.connect(SUBSCRIBERS_DB_PATH) as conn:
            c = conn.cursor()
            c.execute('SELECT COUNT(*) FROM subscribers WHERE guild_id = ?', (guild_id,))
            count = c.fetchone()[0]
            return count >= max_subscriptions
    except Exception as e:
        log_error(f'Failed to query guild subscription limit: {e}')
        return False

def get_subscriber_data(user_id=None, guild_id=None, channel_id=None):
    try:
        with sqlite3.connect(SUBSCRIBERS_DB_PATH) as conn:
            c = conn.cursor()
            query = 'SELECT * FROM subscribers WHERE 1=1'
            params = []

            if user_id is not None:
                query += ' AND user_id = ?'
                params.append(user_id)
            if guild_id is not None:
                query += ' AND guild_id = ?'
                params.append(guild_id)
            if channel_id is not None:
                query += ' AND channel_id = ?'
                params.append(channel_id)

            c.execute(query, params)
            result = c.fetchall()
            return result
    except Exception as e:
        log_error(f'Failed to get subscriber data: {e}')
        return []

def subscribe(user_id, guild_id, channel_id, time=0, dmy=True):
    try:
        with sqlite3.connect(SUBSCRIBERS_DB_PATH) as conn:
            c = conn.cursor()
            c.execute('''INSERT INTO subscribers (user_id, guild_id, channel_id, time, dmy)
                         VALUES (?, ?, ?, ?, ?)''',
                      (user_id, guild_id, channel_id, time, dmy))
            conn.commit()
            log_info(f'Subscribed user {user_id} to guild {guild_id}, channel {channel_id}')
    except sqlite3.IntegrityError:
        log_warning(f'User {user_id} is already subscribed to guild {guild_id}, channel {channel_id}')
    except Exception as e:
        log_error(f'Failed to subscribe user {user_id}: {e}')

def unsubscribe(user_id=None, guild_id=None, channel_id=None):
    try:
        with sqlite3.connect(SUBSCRIBERS_DB_PATH) as conn:
            c = conn.cursor()
            query = 'DELETE FROM subscribers WHERE 1=1'
            params = []

            if user_id is not None:
                query += ' AND user_id = ?'
                params.append(user_id)
            if guild_id is not None:
                query += ' AND guild_id = ?'
                params.append(guild_id)
            if channel_id is not None:
                query += ' AND channel_id = ?'
                params.append(channel_id)

            c.execute(query, params)
            conn.commit()
            log_info(f'Unsubscribed user {user_id} from guild {guild_id}, channel {channel_id}')
    except Exception as e:
        log_error(f'Failed to unsubscribe user {user_id}: {e}')

def query_next_subscribers(time):
    try:
        with sqlite3.connect(SUBSCRIBERS_DB_PATH) as conn:
            c = conn.cursor()
            c.execute('''SELECT * FROM subscribers
                        WHERE time = ?''', (time,))
            result = c.fetchall()
            return result
    except Exception as e:
        log_error(f'Failed to query next subscribers: {e}')
        return []

def sanitize_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None

def sanitize_string(value, max_length=512):
    if not isinstance(value, str):
        return None
    value = value.strip()
    if len(value) > max_length:
        return None
    return value

def sanitize_bool(value):  # This might be the most useless function in the code
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        value = value.lower()
        if value in ['true', '1', 'yes']:
            return True
        elif value in ['false', '0', 'no']:
            return False
    return None

def configure(user_id=None, guild_id=None, channel_id=None, time=0, dmy=None):
    try:
        # Sanitize inputs
        user_id = sanitize_int(user_id)
        guild_id = sanitize_int(guild_id)
        channel_id = sanitize_int(channel_id)
        time = sanitize_int(time)
        dmy = sanitize_bool(dmy)

        # Validate that at least one ID is provided
        if user_id is None and guild_id is None and channel_id is None:
            log_error('No valid IDs provided for configuration.')
            return
        
        with sqlite3.connect(SUBSCRIBERS_DB_PATH) as conn:
            c = conn.cursor()
            
            # Base query
            query = 'UPDATE subscribers SET time = ?, dmy = ? WHERE 1=1'
            params = [time, dmy]

            # Add conditions only if IDs are valid
            if user_id is not None:
                query += ' AND user_id = ?'
                params.append(user_id)
            if guild_id is not None:
                query += ' AND guild_id = ?'
                params.append(guild_id)
            if channel_id is not None:
                query += ' AND channel_id = ?'
                params.append(channel_id)

            # Execute the query
            c.execute(query, params)
            conn.commit()
            log_info(f'Configured subscription for user {user_id} in guild {guild_id}, channel {channel_id}')
    except Exception as e:
        log_error(f'Failed to configure subscription for user {user_id}: {e}')