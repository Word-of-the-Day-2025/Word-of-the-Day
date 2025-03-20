import asyncio
import importlib
import os
import threading

import wotd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
EXTENSIONS_FOLDER = os.path.join(BASE_DIR, 'extensions')

if __name__ == '__main__':
    for folder in os.listdir(EXTENSIONS_FOLDER):
        if os.path.isdir(os.path.join(EXTENSIONS_FOLDER, folder)) and '__init__.py' in os.listdir(os.path.join(EXTENSIONS_FOLDER, folder)) and folder != '__pycache__' and folder != '.dormant':
            print(f'Attempting to load extensions.{folder}')
            module_name = f'extensions.{folder}'
            try:
                # Try importing the extension
                importlib.import_module(module_name)
                print(f'Successfully loaded {module_name}')
            except ModuleNotFoundError as e:
                print(f'Could not load {module_name}: {e}')
    for file in os.listdir(EXTENSIONS_FOLDER):
        if file.endswith('.py'):
            print(f'Attempting to load {file}')
            module_name = f'extensions.{file[:-3]}'
            try:
                # Try importing the extension
                importlib.import_module(module_name)
                print(f'Successfully loaded {module_name}')
            except ModuleNotFoundError as e:
                print(f'Could not load {module_name}: {e}')

    while True:
        pass