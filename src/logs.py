from colorama import Fore, Style
from datetime import datetime
import json
import logging
import os

LOG_DIR = os.path.join(os.path.dirname(__file__), '..', 'log')

# Create the logs directory if it doesn't exist
os.makedirs(LOG_DIR, exist_ok=True)

# Get the current date and time for the log file name
current_time = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')

# Set up logging configuration
logging.basicConfig(
    filename=os.path.join(LOG_DIR, f'{current_time}.log'),
    filemode='a',
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# Create a logger instance
logger = logging.getLogger()

# Set up console handler for logging to stdout
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

def log_exception(e):
    logger.error(f'{Fore.RED}Exception: {e}{Style.RESET_ALL}', exc_info=True)

def log_info(message):
    logger.info(f'{Fore.GREEN}{message}{Style.RESET_ALL}')

def log_warning(message):
    logger.warning(f'{Fore.YELLOW}{message}{Style.RESET_ALL}')

def log_error(message):
    logger.error(f'{Fore.RED}{message}{Style.RESET_ALL}')
