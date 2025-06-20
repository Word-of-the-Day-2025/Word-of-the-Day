import asyncio
import colorama
from colorama import Fore
import importlib
import os
import sys
import time

from logs import log_info, log_warning, log_error, log_exception
import wotd

colorama.init(autoreset=True)

EXT_PATH = os.path.join(os.path.dirname(__file__), 'extensions')
SPLASH_PATH = os.path.join(os.path.dirname(__file__), '..', 'dat', 'splash.txt')

# Function to print the splash screen (Giant ASCII art that says "WOTD", can be changed in the splash.txt file)
def print_splash(margin: int = 0):
    if os.path.exists(SPLASH_PATH):
        with open(SPLASH_PATH, 'r', encoding='utf-8') as f:
            print('\n')
            for line in f:
                # RGB values for #1976D2 are 25, 118, 210
                print(f'\033[38;2;25;118;210m{' ' * margin}{line.rstrip()}')
        print('\n')

# Function to load extensions from the extensions directory
def load_extensions():
    extensions = {}
    for item in os.listdir(EXT_PATH):
        path = os.path.join(EXT_PATH, item)
        if os.path.isdir(path) and '__init__.py' in os.listdir(path):
            module_name = f'extensions.{item}'
            try:
                module = importlib.import_module(module_name)
                extensions[item] = module
                log_info(f'Loaded extension {item}')
            except Exception as e:
                log_error(f'Failed to load extension {item}: {e}')
    return extensions

async def main():
    print_splash()  # I wasted an hour making WOTD ASCII art, but it was too fun to leave out

    log_info('Starting WOTD...')

    # Run WOTD loop in the background without blocking main execution
    asyncio.create_task(wotd.wotd_main_loop())
    log_info('WOTD main loop started in background')

    # Load extensions
    log_info('Loading extensions...')
    extensions = load_extensions()

    # Keep main.py alive
    while True:  # TODO: Make it so the program can be exited with Ctrl+C
        await asyncio.sleep(1)

if __name__ == '__main__':
    asyncio.run(main())