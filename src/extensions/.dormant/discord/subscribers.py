import os
import sqlite3

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SUBSCRIBERS_DB = os.path.join(BASE_DIR, 'subscribers.db')

def create_subscribers_table():
    conn = sqlite3.connect(SUBSCRIBERS_DB)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS subscribers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL,
            user_id INTEGER,
            guild_id INTEGER,
            channel_id INTEGER,
            time TEXT NOT NULL,
            format TEXT NOT NULL,
            silent BOOLEAN DEFAULT FALSE
        )
    ''')
    conn.commit()
    conn.close()

def subscribe_discord(type: str, user_id: int, guild_id: int, channel_id: int, time: str, format: str, silent: bool = False):
    create_subscribers_table()  # Ensure the table exists
    conn = sqlite3.connect(SUBSCRIBERS_DB)
    c = conn.cursor()
    c.execute('''
        INSERT INTO subscribers (type, user_id, guild_id, channel_id, time, format, silent)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (type, user_id, guild_id, channel_id, time, format, silent))
    conn.commit()
    conn.close()

def unsubscribe_discord(type: str, user_id: int = None, guild_id: int = None, channel_id: int = None):
    conn = sqlite3.connect(SUBSCRIBERS_DB)
    c = conn.cursor()
    query = 'DELETE FROM subscribers WHERE type = ?'
    params = [type]

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
    conn.close()

def is_subscribed_private(user_id):
    conn = sqlite3.connect(SUBSCRIBERS_DB)
    c = conn.cursor()
    c.execute('SELECT * FROM subscribers WHERE user_id = ?', (user_id,))
    result = c.fetchone()
    conn.close()
    return result is not None

def is_subscribed_guild(guild_id, channel_id):
    conn = sqlite3.connect(SUBSCRIBERS_DB)
    c = conn.cursor()
    c.execute('SELECT * FROM subscribers WHERE guild_id = ? AND channel_id = ?', (guild_id, channel_id))
    result = c.fetchone()
    conn.close()
    return result is not None

if os.path.getsize(SUBSCRIBERS_DB) == 0:
    create_subscribers_table()