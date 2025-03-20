import asyncio
import colorama
import datetime
from dateutil import tz
from dotenv import load_dotenv
import os
import pytz
import sqlite3
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters
import telegram.error

from .subscribers import subscribe_telegram, unsubscribe_telegram, is_subscribed, SUBSCRIBERS_DB
from wotd import query_queued, query_wotd

colorama.init()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_JSON = os.path.join(BASE_DIR, 'config.json')
RATE_LIMIT = 25  # Requests allowed per second (slightly below the 30 requests per second limit)
semaphore = asyncio.Semaphore(RATE_LIMIT)

# Load the bot token
DOTENV_PATH = os.path.join(BASE_DIR, '.env')
load_dotenv(DOTENV_PATH)
TOKEN = os.getenv('TELEGRAM_TOKEN')

async def start(update: Update, context):
    await update.message.reply_text(
        text='Hello! I am the Word of the Day bot. Use `/subscribe` to subscribe to Word of the Day.',
        parse_mode='Markdown'
    )

async def subscribe(update: Update, context):
    chat_id = update.message.chat_id
    if chat_id < 0:
        chat_type = 'group'
    else:
        chat_type = 'private'
    if is_subscribed(telegram_id=chat_id):
        if chat_type == 'group':
            await update.message.reply_text('This group is already subscribed to Word of the Day.')
        else:
            await update.message.reply_text('You are already subscribed to Word of the Day.')
        return
    subscribe_telegram(chat_id, '00:00', 'MDY', silent=False)
    if chat_type == 'group':
        await update.message.reply_text('This group has subscribed to Word of the Day!')
    else:
        await update.message.reply_text('You have subscribed to Word of the Day!')

async def unsubscribe(update: Update, context):
    chat_id = update.message.chat_id
    if chat_id < 0:
        chat_type = 'group'
    else:
        chat_type = 'private'
    if not is_subscribed(telegram_id=chat_id):
        if chat_type == 'group':
            await update.message.reply_text('This group is not subscribed to Word of the Day.')
        else:
            await update.message.reply_text('You are not subscribed to Word of the Day.')
        return
    unsubscribe_telegram(chat_id)
    if chat_type == 'group':
        await update.message.reply_text('This group has unsubscribed from Word of the Day.')
    else:
        await update.message.reply_text('You have unsubscribed from Word of the Day.')

async def query(update: Update, context):
    # Query the word of the day
    word, ipa, type, definition, date = query_wotd()

    # If the word of the day has not been set yet, return
    if not word:
        await update.message.reply_text('The Word of the Day has not been set yet.')
        return

    # Send the Word of the Day to every subscriber
    date = date.split('-')
    month = date[1]
    month = datetime.date(2000, int(month), 1).strftime('%B')  # Convert the month number to the month name
    day = date[0].lstrip('0')
    year = date[2]
    if day[-1] == '1' and day != '11':
        day += 'st'
    elif day[-1] == '2' and day != '12':
        day += 'nd'
    elif day[-1] == '3' and day != '13':
        day += 'rd'
    else:
        day += 'th'
    date = f'{month} {day}, {year}'
    message = f'Today is {date}, and the Word of the Day is "{word}" ({ipa}), which is defined as: ({type}) {definition}'

    await update.message.reply_text(message)

async def config(update: Update, context):
    await update.message.reply_text('Configuration options will be available soon.')

"""
async def send_all(update: Update, context):
    '''Send a message to all subscribers.'''

    message = 'This is a test message.'
    conn = sqlite3.connect(SUBSCRIBERS_DB)
    c = conn.cursor()
    c.execute('SELECT * FROM subscribers')
    subscribers = c.fetchall()
    conn.close()
    sent_places = []
    async with semaphore:
        app = Application.builder().token(TOKEN).build()
    for subscriber in subscribers:
        async with semaphore:
            if subscriber[1] in sent_places:
                # Skip the user if they have already received the Word of the Day
                print(colorama.Fore.YELLOW + f'Skipping {subscriber[1]} because they have already received the message.' + colorama.Style.RESET_ALL)
                continue
            try:
                print(colorama.Fore.CYAN + f'Sending message to {subscriber[1]}' + colorama.Style.RESET_ALL)
                await app.bot.send_message(chat_id=subscriber[1], text=message)
                print(colorama.Fore.GREEN + f'Message sent to {subscriber[1]}' + colorama.Style.RESET_ALL)
                sent_places.append(subscriber[1])
            except Exception as e:
                if isinstance(e, telegram.error.Forbidden):
                    # The user or group has blocked the bot, so unsubscribe them
                    print(colorama.Fore.RED + f'Unsubscribing {subscriber[1]} because they have blocked the bot.' + colorama.Style.RESET_ALL)
                    unsubscribe_telegram(subscriber[1])
                elif isinstance(e, telegram.error.RetryAfter):
                    # Sleep for the specified retry duration and try again
                    await asyncio.sleep(e.retry_after)
                    try:
                        print(colorama.Fore.CYAN + f'Sending message to {subscriber[1]}' + colorama.Style.RESET_ALL)
                        await app.bot.send_message(chat_id=subscriber[1], text=message)
                    except Exception as retry_e:
                        # Skip the user if an error occurs again
                        print(colorama.Fore.RED + f'Error sending message to {subscriber[1]}' + colorama.Style.RESET_ALL)
                        continue
                else:
                    # Skip the user if an error occurs
                    print(colorama.Fore.RED + f'Error sending message to {subscriber[1]}' + colorama.Style.RESET_ALL)
                    continue
"""

async def send_wotd(app):
    '''Send the Word of the Day to every subscriber.'''

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

        # Query the word of the day
        queued_word, queued_ipa, queued_type, queued_definition, queued_date = query_queued()

        # Send the Word of the Day to every subscriber
        utc_now = datetime.datetime.now(pytz.utc)
        month = utc_now.strftime('%B')
        day = utc_now.strftime('%d').lstrip('0')
        year = utc_now.strftime('%Y')
        if day[-1] == '1' and day != '11':
            day += 'st'
        elif day[-1] == '2' and day != '12':
            day += 'nd'
        elif day[-1] == '3' and day != '13':
            day += 'rd'
        else:
            day += 'th'
        date = f'{month} {day}, {year}'
        message = f'Today is {date}, and the Word of the Day is "{queued_word}" ({queued_ipa}), which is defined as: ({queued_type}) {queued_definition}'

        conn = sqlite3.connect(SUBSCRIBERS_DB)
        c = conn.cursor()
        c.execute('SELECT * FROM subscribers')
        subscribers = c.fetchall()
        conn.close()
        sent_places = []
        async with semaphore:
            app = Application.builder().token(TOKEN).build()
        for subscriber in subscribers:
            async with semaphore:
                if subscriber[1] in sent_places:
                    # Skip the user if they have already received the Word of the Day
                    continue
                try:
                    await app.bot.send_message(chat_id=subscriber[1], text=message)
                    sent_places.append(subscriber[1])
                except Exception as e:
                    if isinstance(e, telegram.error.Forbidden):
                        # The user or group has blocked the bot, so unsubscribe them
                        unsubscribe_telegram(subscriber[1])
                    elif isinstance(e, telegram.error.RetryAfter):
                        # Sleep for the specified retry duration and try again
                        await asyncio.sleep(e.retry_after)
                        try:
                            await app.bot.send_message(chat_id=subscriber[1], text=message)
                        except Exception as retry_e:
                            # Skip the user if an error occurs again
                            continue
                    else:
                        # Skip the user if an error occurs
                        continue

def run_app():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('subscribe', subscribe))
    app.add_handler(CommandHandler('unsubscribe', unsubscribe))
    app.add_handler(CommandHandler('query', query))
    app.add_handler(CommandHandler('config', config))

    app.run_polling()

run_app()