import os
import sqlite3
import threading

from logs import log_info, log_error

SUBSCRIBERS_DB_PATH = os.path.join(os.path.dirname(__file__), 'subscribers.db')

# In-memory cache of subscribers with thread safety
subscribers_db = []
_cache_lock = threading.Lock()

def init_db():
    global subscribers_db
    try:
        with sqlite3.connect(SUBSCRIBERS_DB_PATH) as conn:
            c = conn.cursor()
            c.execute('''CREATE TABLE IF NOT EXISTS subscribers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                guild_id INTEGER,
                channel_id INTEGER,
                timezone TEXT DEFAULT 'UTC',
                time_sunday SMALLINT DEFAULT 0,
                time_monday SMALLINT DEFAULT 0,
                time_tuesday SMALLINT DEFAULT 0,
                time_wednesday SMALLINT DEFAULT 0,
                time_thursday SMALLINT DEFAULT 0,
                time_friday SMALLINT DEFAULT 0,
                time_saturday SMALLINT DEFAULT 0,
                silent_message BOOLEAN DEFAULT 0,
                include_date BOOLEAN DEFAULT 1,
                include_ipa BOOLEAN DEFAULT 1,
                is_dmy BOOLEAN DEFAULT 1,
                message_date_style TINYINT DEFAULT 1 CHECK(message_date_style BETWEEN 0 AND 3)
            )''')
            conn.commit()
            c.execute('SELECT * FROM subscribers')
            with _cache_lock:
                subscribers_db = c.fetchall()
    except Exception as e:
        log_error(f'Failed to initialize database: {e}')

def count_subscribers():
    with _cache_lock:
        return len(subscribers_db)

def query_subscribed(user_id=None, guild_id=None, channel_id=None):
    try:
        with _cache_lock:
            log_info(f'QUERY_SUBSCRIBED: Checking cache, size={len(subscribers_db)}, id(subscribers_db)={id(subscribers_db)}, user_id={user_id}, guild_id={guild_id}, channel_id={channel_id}')
            for row in subscribers_db:
                if ((user_id is None or row[1] == user_id) and
                    (guild_id is None or row[2] == guild_id) and
                    (channel_id is None or row[3] == channel_id)):
                    return True
        return False
    except Exception as e:
        log_error(f'Failed to query database: {e}')
        return False

def query_guild_over_limit(guild_id, max_subscriptions):
    try:
        with _cache_lock:
            count = sum(1 for r in subscribers_db if r[2] == guild_id)
        return count >= max_subscriptions
    except Exception as e:
        log_error(f'Failed to query guild subscription limit: {e}')
        return False

def get_subscriber_data(user_id=None, guild_id=None, channel_id=None):
    try:
        results = []
        with _cache_lock:
            for row in subscribers_db:
                if ((user_id is None or row[1] == user_id) and
                    (guild_id is None or row[2] == guild_id) and
                    (channel_id is None or row[3] == channel_id)):
                    results.append(row)
        return results
    except Exception as e:
        log_error(f'Failed to get subscriber data: {e}')
        return []

def subscribe(user_id, guild_id, channel_id, timezone='UTC', time_sunday=0, time_monday=0, time_tuesday=0, time_wednesday=0, time_thursday=0, time_friday=0, time_saturday=0, silent_message=False, include_date=True, include_ipa=True, is_dmy=True, message_date_style=1):
    global subscribers_db

    try:
        with _cache_lock:
            log_info(f'SUBSCRIBE: Cache size before: {len(subscribers_db)}, id(subscribers_db)={id(subscribers_db)}')
        
        with sqlite3.connect(SUBSCRIBERS_DB_PATH) as conn:
            c = conn.cursor()
            c.execute('''INSERT INTO subscribers (user_id, guild_id, channel_id, timezone, time_sunday, time_monday, time_tuesday, time_wednesday, time_thursday, time_friday, time_saturday, silent_message, include_date, include_ipa, is_dmy, message_date_style)
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                      (user_id, guild_id, channel_id, timezone, time_sunday, time_monday, time_tuesday, time_wednesday, time_thursday, time_friday, time_saturday, silent_message, include_date, include_ipa, is_dmy, message_date_style))
            conn.commit()
            
            # Get the ID of the newly inserted row
            new_id = c.lastrowid
            
            # Add the new subscriber to the cache
            new_row = (new_id, user_id, guild_id, channel_id, timezone, time_sunday, time_monday, time_tuesday, time_wednesday, time_thursday, time_friday, time_saturday, silent_message, include_date, include_ipa, is_dmy, message_date_style)
            with _cache_lock:
                subscribers_db.append(new_row)
            
    except sqlite3.IntegrityError:
        pass  # Ignore duplicate subscriptions
    except Exception as e:
        log_error(f'Failed to subscribe user {user_id}: {e}')

def unsubscribe(user_id=None, guild_id=None, channel_id=None):
    global subscribers_db

    # Convert string IDs to integers if needed
    if user_id is not None and isinstance(user_id, str):
        user_id = int(user_id)
    if guild_id is not None and isinstance(guild_id, str):
        guild_id = int(guild_id)
    if channel_id is not None and isinstance(channel_id, str):
        channel_id = int(channel_id)

    try:
        with _cache_lock:
            # Count before deletion
            count_before = len(subscribers_db)
        
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

            log_info(f'UNSUBSCRIBE: SQL query: {query} with params: {params}')
            c.execute(query, params)
            rows_deleted = c.rowcount
            conn.commit()
            log_info(f'UNSUBSCRIBE: Deleted {rows_deleted} rows from database')

            # Remove matching rows from the cache
            with _cache_lock:
                before_filter = len(subscribers_db)
                subscribers_db[:] = [
                    row for row in subscribers_db
                    if not (
                        (user_id is None or row[1] == user_id) and
                        (guild_id is None or row[2] == guild_id) and
                        (channel_id is None or row[3] == channel_id)
                    )
                ]
                count_after = len(subscribers_db)
            
    except Exception as e:
        log_error(f'Failed to unsubscribe user {user_id}: {e}')

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

def sanitize_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        value = value.lower()
        if value in ['true', '1', 'yes']:
            return True
        elif value in ['false', '0', 'no']:
            return False
    return None

def configure(user_id=None, guild_id=None, channel_id=None, timezone=None,
              time_sunday=None, time_monday=None, time_tuesday=None, time_wednesday=None, time_thursday=None, time_friday=None, time_saturday=None,
              silent_message=True, include_date=True, include_ipa=True, is_dmy=True, message_date_style=None):
    global subscribers_db

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
                'silent_message': silent_message,
                'include_date': include_date,
                'include_ipa': include_ipa,
                'is_dmy': is_dmy,
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

            # Update the cache - find matching rows and update them
            with _cache_lock:
                for i, row in enumerate(subscribers_db):
                    if ((user_id is None or row[1] == user_id) and
                        (guild_id is None or row[2] == guild_id) and
                        (channel_id is None or row[3] == channel_id)):
                        
                        # Convert row to list to modify it
                        row_list = list(row)
                        
                        # Update fields in the cached row
                        field_indices = {
                            'timezone': 4,
                            'time_sunday': 5,
                            'time_monday': 6,
                            'time_tuesday': 7,
                            'time_wednesday': 8,
                            'time_thursday': 9,
                            'time_friday': 10,
                            'time_saturday': 11,
                            'silent_message': 12,
                            'include_date': 13,
                            'include_ipa': 14,
                            'is_dmy': 15,
                            'message_date_style': 16
                        }
                        
                        for field, value in fields.items():
                            if value is not None:
                                row_list[field_indices[field]] = value
                        
                        # Replace the row in cache
                        subscribers_db[i] = tuple(row_list)
                    
    except Exception as e:
        log_error(f'Failed to configure subscription for user {user_id}: {e}')