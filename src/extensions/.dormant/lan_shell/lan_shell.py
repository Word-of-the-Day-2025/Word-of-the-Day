from flask import Flask, request, render_template_string
import subprocess
import os

app = Flask(__name__)

# Store logs for display
server_logs = []
current_directory = os.getcwd()

HTML = '''
<!DOCTYPE html>
<html>
<head>
    <title>Server Control</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body {
            font-family: monospace;
            background-color: #0f0f0f;
            color: #ffffff;
            margin: 0;
            padding: 0;
            display: flex;
            flex-direction: column;
            height: 100vh;
        }
        textarea {
            flex: 1;
            width: 100%;
            background-color: #0f0f0f;
            color: #ffffff;
            border: none;
            resize: none;
            padding: 8px;
            box-sizing: border-box;
        }
        form {
            display: flex;
            background-color: #0f0f0f;
            padding: 8px;
            box-sizing: border-box;
        }
        input {
            flex: 1;
            padding: 12px;
            margin-right: 8px;
            background-color: #202020;
            color: #ffffff;
            border: none;
            border-radius: 8px;
            outline: none;
            font-size: 16px;
        }
        button {
            padding: 12px 16px;
            background-color: #202020;
            color: #ffffff;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-size: 16px;
        }
        button:hover {
            background-color: #404040;
        }
        @media (max-width: 600px) {
            input, button {
                padding: 10px;
                font-size: 14px;
            }
            form {
                flex-direction: column;
            }
            input {
                margin-right: 0;
                margin-bottom: 8px;
            }
        }
    </style>
</head>
<body>
    <textarea id="log" readonly>{{ logs }}</textarea>
    <form method="POST">
        <input type="text" name="command" placeholder="Enter command..." autofocus autocomplete="off">
        <button type="submit">Send</button>
    </form>
    <script>
        // Automatically scroll to the bottom of the log
        const log = document.getElementById('log');
        log.scrollTop = log.scrollHeight;
        
        // Clear input field after submitting
        const inputField = document.querySelector('input[name="command"]');
        inputField.value = '';
    </script>
</body>
</html>
'''

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

app.run(host='0.0.0.0', port=8000)