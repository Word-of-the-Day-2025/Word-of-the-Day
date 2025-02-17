import os
import sqlite3

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WORDS_DB = os.path.join(BASE_DIR, 'words.db')

def reset_used_state():
    conn = sqlite3.connect(WORDS_DB)
    c = conn.cursor()
    c.execute('UPDATE words SET used = 0')
    conn.commit()
    conn.close()

if __name__ == '__main__':
    reset_used_state()