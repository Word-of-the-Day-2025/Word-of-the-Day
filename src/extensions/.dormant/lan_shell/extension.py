import asyncio
from flask import Flask, request, render_template_string
import json
from multiprocessing import Process
import os
import subprocess
import sys
import threading

app = Flask(__name__)

# Store logs for display
server_logs = []
current_directory = os.getcwd()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, 'config.json')

with open(CONFIG_FILE, 'r') as f:
    config = json.load(f)
    PORT = config['port']

with open(os.path.join(BASE_DIR, 'index.html'), 'r') as f:
    HTML = f.read()

@app.route('/', methods=['GET', 'POST'])
def terminal():
    global server_logs, current_directory

    if request.method == 'POST':
        command = request.form.get('command')
        if command:
            if command.startswith('cd '):
                try:
                    new_directory = command[3:].strip()
                    os.chdir(new_directory)
                    current_directory = os.getcwd()
                    server_logs.append(f'$ {command}\n')
                except Exception as e:
                    server_logs.append(f'$ {command}\n{str(e)}\n')
            else:
                try:
                    # Execute the command and capture output
                    result = subprocess.check_output(command, shell=True, stderr=subprocess.STDOUT, text=True, cwd=current_directory)
                    server_logs.append(f'$ {command}\n{result}')
                except subprocess.CalledProcessError as e:
                    server_logs.append(f'$ {command}\n{e.output}')

    # Limit logs to the last 1024 lines
    server_logs = server_logs[-1024:]

    # Render the HTML template with logs
    return render_template_string(HTML, logs='\n'.join(server_logs))

def run():
    if sys.platform.startswith('win'):
        from waitress import serve
        serve(app, host='0.0.0.0', port=PORT)
    elif sys.platform.startswith('linux'):
        from gunicorn.app.wsgiapp import run
        script_name = os.path.splitext(os.path.basename(__file__))[0]
        sys.argv = ['gunicorn', '-w', '4', '-b', f'0.0.0.0:{PORT}', f'{script_name}:app']
        run()

# Run the server in a separate thread
thread = threading.Thread(target=run)
thread.daemon = True
thread.start()

# Run the asyncio event loop
try:
    loop = asyncio.get_running_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
loop.run_forever()