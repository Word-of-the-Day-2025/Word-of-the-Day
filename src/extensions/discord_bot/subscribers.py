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
                timezone TEXT DEFAULT 'UTC',
                time_sunday INTEGER DEFAULT 0,
                time_monday INTEGER DEFAULT 0,
                time_tuesday INTEGER DEFAULT 0,
                time_wednesday INTEGER DEFAULT 0,
                time_thursday INTEGER DEFAULT 0,
                time_friday INTEGER DEFAULT 0,
                time_saturday INTEGER DEFAULT 0,
                send_wotd_in_utc BOOLEAN DEFAULT 0,
                include_date BOOLEAN DEFAULT 1,
                include_ipa BOOLEAN DEFAULT 1,
                is_dmy BOOLEAN DEFAULT 1,
                send_updates BOOLEAN DEFAULT 1,
                message_date_style TINYINT DEFAULT 1 CHECK(message_date_style BETWEEN 0 AND 3)
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

def subscribe(user_id, guild_id, channel_id, timezone='UTC', time_sunday=0, time_monday=0, time_tuesday=0, time_wednesday=0, time_thursday=0, time_friday=0, time_saturday=0, send_wotd_in_utc=False, include_date=True, include_ipa=True, is_dmy=True, send_updates=True, message_date_style=1):
    try:
        with sqlite3.connect(SUBSCRIBERS_DB_PATH) as conn:
            c = conn.cursor()
            c.execute('''INSERT INTO subscribers (user_id, guild_id, channel_id, timezone, time_sunday, time_monday, time_tuesday, time_wednesday, time_thursday, time_friday, time_saturday, send_wotd_in_utc, include_date, include_ipa, is_dmy, send_updates, message_date_style)
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                      (user_id, guild_id, channel_id, timezone, time_sunday, time_monday, time_tuesday, time_wednesday, time_thursday, time_friday, time_saturday, send_wotd_in_utc, include_date, include_ipa, is_dmy, send_updates, message_date_style))
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

def query_next_subscribers(time, day_of_week):
    try:
        with sqlite3.connect(SUBSCRIBERS_DB_PATH) as conn:
            c = conn.cursor()
            c.execute(f'''SELECT * FROM subscribers
                        WHERE time_{day_of_week} = ?''', (time,))
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

def configure(user_id=None, guild_id=None, channel_id=None, timezone=None,  # This is quite a few arguments
              time_sunday=None, time_monday=None, time_tuesday=None, time_wednesday=None, time_thursday=None, time_friday=None, time_saturday=None,
              send_wotd_in_utc=True, include_date=True, include_ipa=True, is_dmy=True, send_updates=True, message_date_style=None):
    try:
        # Sanitize inputs
        user_id = sanitize_int(user_id)
        guild_id = sanitize_int(guild_id)
        channel_id = sanitize_int(channel_id)
        is_dmy = sanitize_bool(is_dmy)

        # Validate that at least one ID is provided
        if user_id is None and guild_id is None and channel_id is None:
            log_error('No valid IDs provided for configuration.')
            return
        
        with sqlite3.connect(SUBSCRIBERS_DB_PATH) as conn:
            c = conn.cursor()
            
            # Build query dynamically based on non-None values
            query_parts = []
            params = []
            fields = {
                'timezone': timezone,
                'time_sunday': time_sunday,
                'time_monday': time_monday,
                'time_tuesday': time_tuesday,
                'time_wednesday': time_wednesday,
                'time_thursday': time_thursday,
                'time_friday': time_friday,
                'time_saturday': time_saturday,
                'send_wotd_in_utc': send_wotd_in_utc,
                'include_date': include_date,
                'include_ipa': include_ipa,
                'is_dmy': is_dmy,
                'send_updates': send_updates,
                'message_date_style': message_date_style
            }
            
            for field, value in fields.items():
                if value is not None:
                    query_parts.append(f'{field} = ?')
                    params.append(value)
                    
            if not query_parts:
                return
                
            query = 'UPDATE subscribers SET ' + ', '.join(query_parts) + ' WHERE 1=1'

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