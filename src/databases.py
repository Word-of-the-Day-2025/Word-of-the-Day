import os
import sqlite3

# We're using DB files because it's fancier than JSON

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, '..', 'dat')
WORDS_DB = os.path.join(DATA_DIR, 'words.db')

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

if os.path.getsize(WORDS_DB) == 0:
    create_words_table()