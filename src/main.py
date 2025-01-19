import asyncio
import importlib
import os
import threading

from wotd import word_of_the_day

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
EXTENSIONS_FOLDER = os.path.join(BASE_DIR, 'extensions')

if __name__ == '__main__':
    for folder in os.listdir(EXTENSIONS_FOLDER):
        if os.path.isdir(os.path.join(EXTENSIONS_FOLDER, folder)) and '__init__.py' in os.listdir(os.path.join(EXTENSIONS_FOLDER, folder)):
            module_name = f'extensions.{folder}'
            try:
                # Try importing the extension
                importlib.import_module(module_name)
                print(f'Successfully loaded {module_name}')
            except ModuleNotFoundError as e:
                print(f'Could not load {module_name}: {e}')

    loop = asyncio.get_event_loop()
    loop.create_task(word_of_the_day())
    loop.run_forever()

    while True:
        pass