import asyncio
import datetime
from dateutil import tz
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

global queued_word
global queued_ipa
global queued_type
global queued_definition
global queued_date

word = ''
ipa = ''
type = ''
definition = ''
date = ''

queued_word = ''
queued_ipa = ''
queued_type = ''
queued_definition = ''
queued_date = ''

def query_queued():
    global queued_word
    global queued_ipa
    global queued_type
    global queued_definition
    global queued_date

    return queued_word, queued_ipa, queued_type, queued_definition, queued_date

def query_wotd():
    global word
    global ipa
    global type
    global definition
    global date

    return word, ipa, type, definition, date

async def queue_wotd():
    # Make the variables global
    global queued_word
    global queued_ipa
    global queued_type
    global queued_definition
    global queued_date

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
        queued_word = entry[1]
        queued_ipa = entry[2]
        queued_type = entry[3]
        queued_definition = entry[4]

        # Find out what the date will be next 8:00 AM PST
        utc_now = datetime.datetime.now(datetime.timezone.utc)
        # pacific = pytz.timezone('US/Pacific')
        pacific = pytz.timezone('America/Los_Angeles')
        pacific_now = utc_now.astimezone(pacific)
        if pacific_now.hour >= 8:
            next_8am = pacific_now.replace(hour=8, minute=0, second=0, microsecond=0) + datetime.timedelta(days=1)
        else:
            next_8am = pacific_now.replace(hour=8, minute=0, second=0, microsecond=0)
        queued_date = next_8am.strftime('%d-%m-%Y')

        # Set the word at 12:00 AM UTC (4:00PM PST, but only update the Word of the Day at 8:00 AM PST)
        now = datetime.datetime.now(datetime.timezone.utc)
        next_midnight = (now + datetime.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        sleep_duration = (next_midnight - now).total_seconds()
        await asyncio.sleep(sleep_duration)

async def update_wotd():
    global word
    global ipa
    global type
    global definition
    global date

    while True:
        # Wait for 8:00 AM PST
        now = datetime.datetime.now(datetime.timezone.utc)
        pst = tz.gettz('America/Los_Angeles')
        current_pst = now.astimezone(pst)
        next_8am_pst = current_pst.replace(hour=8, minute=0, second=0, microsecond=0)
        if current_pst >= next_8am_pst:
            next_8am_pst += datetime.timedelta(days=1)
        sleep_duration = (next_8am_pst - now).total_seconds()
        await asyncio.sleep(sleep_duration)

        # Update the word of the day
        word, ipa, type, definition, date = query_queued()

queue_wotd_thread = threading.Thread(target=lambda: asyncio.run(queue_wotd()))
queue_wotd_thread.start()

update_wotd_thread = threading.Thread(target=lambda: asyncio.run(update_wotd()))
update_wotd_thread.start()