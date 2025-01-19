import asyncio
import datetime
import pytz
import sqlite3
import threading
import time

from databases import WORDS_DB

global word
global ipa
global type
global definition
global date

word = ''
ipa = ''
type = ''
definition = ''
date = ''

async def word_of_the_day():
    # Make the variables global
    global word
    global ipa
    global type
    global definition
    global date

    # Get the word of the day
    while True:
        # Get the first unused word and update its "used" value to 1 (True)
        conn = sqlite3.connect(WORDS_DB)
        c = conn.cursor()
        c.execute('SELECT * FROM words WHERE used = 0 LIMIT 1')
        entry = c.fetchone()
        if entry:
            c.execute('UPDATE words SET used = 1 WHERE id = ?', (entry[0],))
            conn.commit()
        conn.close()

        # Set the word of the day variables
        word = entry[1]
        ipa = entry[2]
        type = entry[3]
        definition = entry[4]

        # Find out what the date will be next 8:00 AM PST
        utc_now = datetime.datetime.now(datetime.timezone.utc)
        pacific = pytz.timezone('US/Pacific')
        pacific_now = utc_now.astimezone(pacific)
        if pacific_now.hour >= 8:
            next_8am = pacific_now.replace(hour=8, minute=0, second=0, microsecond=0) + datetime.timedelta(days=1)
        else:
            next_8am = pacific_now.replace(hour=8, minute=0, second=0, microsecond=0)
        date = next_8am.strftime('%d-%m-%Y')

        # Set the word at 12:00 AM UTC (4:00PM PST, but only update the Word of the Day at 8:00 AM PST)
        now = datetime.datetime.now(datetime.timezone.utc)
        next_midnight = (now + datetime.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        sleep_duration = (next_midnight - now).total_seconds()
        await asyncio.sleep(sleep_duration)

def query_queued():
    global word
    global ipa
    global type
    global definition
    global date

    return word, ipa, type, definition, date