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
            telegram_id INTEGER,
            time TEXT NOT NULL,
            format TEXT NOT NULL,
            silent BOOLEAN DEFAULT FALSE
        )
    ''')
    conn.commit()
    conn.close()

def subscribe_telegram(telegram_id: int, time: str, format: str, silent: bool = False):
    create_subscribers_table()  # Ensure the table exists
    conn = sqlite3.connect(SUBSCRIBERS_DB)
    c = conn.cursor()
    c.execute('''
        INSERT INTO subscribers (telegram_id, time, format, silent)
        VALUES (?, ?, ?, ?)
    ''', (telegram_id, time, format, silent))
    conn.commit()
    conn.close()

def unsubscribe_telegram(telegram_id: int = None):
    conn = sqlite3.connect(SUBSCRIBERS_DB)
    c = conn.cursor()
    query = 'DELETE FROM subscribers WHERE telegram_id = ?'
    params = [telegram_id]
    c.execute(query, params)
    conn.commit()
    conn.close()

def is_subscribed(telegram_id):
    conn = sqlite3.connect(SUBSCRIBERS_DB)
    c = conn.cursor()
    c.execute('SELECT * FROM subscribers WHERE telegram_id = ?', (telegram_id,))
    result = c.fetchone()
    conn.close()
    return result is not None

if os.path.getsize(SUBSCRIBERS_DB) == 0:
    create_subscribers_table()