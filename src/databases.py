import os
import sqlite3

# We're using DB files because it's fancier than JSON

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, '..', 'dat')
WORDS_DB = os.path.join(DATA_DIR, 'words.db')
SUBSCRIBERS_DISCORD_DB = os.path.join(DATA_DIR, 'subscribers_discord.db')  # TODO: Make managing Discord subscribers part of the Discord extension

def create_words_table():
    conn = sqlite3.connect(WORDS_DB)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS words (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            word TEXT NOT NULL,
            ipa TEXT NOT NULL,
            type TEXT NOT NULL,
            definition TEXT NOT NULL,
            used BOOLEAN DEFAULT FALSE NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

def add_word(word: str, ipa: str, type: str, definition: str, used: bool):
    create_words_table()  # Ensure the table exists
    conn = sqlite3.connect(WORDS_DB)
    c = conn.cursor()
    c.execute('INSERT INTO words (word, ipa, type, definition, used) VALUES (?, ?, ?, ?, ?)', (word, ipa, type, definition, used))
    conn.commit()
    conn.close()

def create_subscribers_discord_table():
    conn = sqlite3.connect(SUBSCRIBERS_DISCORD_DB)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS subscribers_discord (
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
    create_subscribers_discord_table()  # Ensure the table exists
    conn = sqlite3.connect(SUBSCRIBERS_DISCORD_DB)
    c = conn.cursor()
    c.execute('''
        INSERT INTO subscribers_discord (type, user_id, guild_id, channel_id, time, format, silent)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (type, user_id, guild_id, channel_id, time, format, silent))
    conn.commit()
    conn.close()

def unsubscribe_discord(type: str, user_id: int = None, guild_id: int = None, channel_id: int = None):
    conn = sqlite3.connect(SUBSCRIBERS_DISCORD_DB)
    c = conn.cursor()
    query = 'DELETE FROM subscribers_discord WHERE type = ?'
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

def is_subscribed_discord_private(user_id):
    conn = sqlite3.connect(SUBSCRIBERS_DISCORD_DB)
    c = conn.cursor()
    c.execute('SELECT * FROM subscribers_discord WHERE user_id = ?', (user_id,))
    result = c.fetchone()
    conn.close()
    return result is not None

def is_subscribed_discord_guild(guild_id, channel_id):
    conn = sqlite3.connect(SUBSCRIBERS_DISCORD_DB)
    c = conn.cursor()
    c.execute('SELECT * FROM subscribers_discord WHERE guild_id = ? AND channel_id = ?', (guild_id, channel_id))
    result = c.fetchone()
    conn.close()
    return result is not None

if os.path.getsize(SUBSCRIBERS_DISCORD_DB) == 0:
    create_subscribers_discord_table()
if os.path.getsize(WORDS_DB) == 0:
    create_words_table()