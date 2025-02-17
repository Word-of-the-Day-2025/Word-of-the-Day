import asyncio
import importlib
import os
import threading

from wotd import queue_wotd, update_wotd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
EXTENSIONS_FOLDER = os.path.join(BASE_DIR, 'extensions')

if __name__ == '__main__':
    for folder in os.listdir(EXTENSIONS_FOLDER):
        if os.path.isdir(os.path.join(EXTENSIONS_FOLDER, folder)) and '__init__.py' in os.listdir(os.path.join(EXTENSIONS_FOLDER, folder)) and folder != '__pycache__' and folder != '.dormant':
            module_name = f'extensions.{folder}'
            try:
                # Try importing the extension
                importlib.import_module(module_name)
                print(f'Successfully loaded {module_name}')
            except ModuleNotFoundError as e:
                print(f'Could not load {module_name}: {e}')
    for file in os.listdir(EXTENSIONS_FOLDER):
        if file.endswith('.py'):
            module_name = f'extensions.{file[:-3]}'
            try:
                # Try importing the extension
                importlib.import_module(module_name)
                print(f'Successfully loaded {module_name}')
            except ModuleNotFoundError as e:
                print(f'Could not load {module_name}: {e}')

    loop_0 = asyncio.get_event_loop()
    loop_0.create_task(queue_wotd())
    loop_0.run_forever()

    loop_1 = asyncio.get_event_loop()
    loop_1.create_task(update_wotd())
    loop_1.run_forever()

    while True:
        pass