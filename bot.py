import discord
from discord.ext import tasks
from flask import Flask, request, render_template_string, redirect, url_for
import sqlite3
import datetime
import json
import threading
import asyncio
import time

# --- CONFIGURATION LOAD ---
with open('config.json', 'r') as f:
    config = json.load(f)

TOKEN = config['bot_token']
PORT = config['web_port']
WEB_PASS = config['web_password']
DEFAULT_CID = config['default_channel_id']

# --- SHARED STATE ---
# The bot will update this list, and Flask will read it.
known_channels = []

# --- DATABASE SETUP ---
DB_FILE = "scheduler.db"


def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS queue
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  message TEXT,
                  send_time TEXT,
                  channel_id INTEGER,
                  channel_name TEXT)''')
    conn.commit()
    conn.close()


# --- FLASK WEB SERVER ---
app = Flask(__name__)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Discord Scheduler</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        :root { --bg: #2c2f33; --panel: #23272a; --input: #40444b; --text: #fff; --primary: #7289da; --danger: #f04747; --success: #43b581; }
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: var(--bg); color: var(--text); margin: 0; padding: 20px; display: flex; flex-direction: column; align-items: center; }
        .container { width: 100%; max-width: 800px; display: grid; grid-template-columns: 1fr; gap: 20px; }
        @media(min-width: 768px) { .container { grid-template-columns: 1fr 1fr; } }

        .card { background: var(--panel); padding: 20px; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.3); }
        h2 { margin-top: 0; border-bottom: 2px solid var(--primary); padding-bottom: 10px; font-size: 1.2rem;}

        input, textarea, select { width: 100%; padding: 12px; margin: 8px 0 16px 0; border: none; border-radius: 4px; background: var(--input); color: white; box-sizing: border-box; font-size: 14px; }
        button { background: var(--primary); color: white; padding: 12px; border: none; border-radius: 4px; cursor: pointer; width: 100%; font-weight: bold; font-size: 14px; transition: background 0.2s;}
        button:hover { background: #5b6eae; }

        .msg-list { list-style: none; padding: 0; }
        .msg-item { background: var(--input); margin-bottom: 10px; padding: 15px; border-radius: 6px; border-left: 4px solid var(--success); position: relative; }
        .msg-meta { font-size: 0.85em; color: #99aab5; margin-bottom: 5px; display: flex; justify-content: space-between;}
        .msg-content { font-size: 1em; white-space: pre-wrap; word-break: break-word;}
        .delete-btn { background: var(--danger); width: auto; padding: 5px 10px; font-size: 0.8em; position: absolute; top: 10px; right: 10px; }
        .delete-btn:hover { background: #c03535; }

        .flash { padding: 10px; border-radius: 4px; margin-bottom: 20px; text-align: center; }
        .flash.success { background: rgba(67, 181, 129, 0.2); border: 1px solid var(--success); }
        .flash.error { background: rgba(240, 71, 71, 0.2); border: 1px solid var(--danger); }
    </style>
</head>
<body>
    <div style="margin-bottom: 20px; text-align: center;">
        <h1>📅 Auto-Message Bot</h1>
        <p style="color: #99aab5;">Server Time: {{ server_time }}</p>
    </div>

    {% if msg %}
        <div class="flash {{ type }}">{{ msg }}</div>
    {% endif %}

    <div class="container">
        <div class="card">
            <h2>New Message</h2>
            <form method="POST" action="/">
                <label>Web Password</label>
                <input type="password" name="password" required>

                <label>Target Channel</label>
                <select name="channel_select">
                    {% for ch in channels %}
                        <option value="{{ ch.id }}|{{ ch.name }}" {% if ch.id == default_cid %}selected{% endif %}>#{{ ch.name }}</option>
                    {% endfor %}
                </select>

                <label>Message</label>
                <textarea name="content" rows="5" required placeholder="Type your announcement here..."></textarea>

                <label>Send Time (YYYY-MM-DD HH:MM)</label>
                <input type="datetime-local" name="datetime" required>

                <button type="submit">Schedule It</button>
            </form>
        </div>

        <div class="card">
            <h2>Upcoming Queue</h2>
            {% if queue %}
                <ul class="msg-list">
                {% for item in queue %}
                    <li class="msg-item">
                        <div class="msg-meta">
                            <span>📅 {{ item.time }}</span>
                            <span>#{{ item.ch_name }}</span>
                        </div>
                        <div class="msg-content">{{ item.msg }}</div>
                        <form method="POST" action="/delete" style="margin:0;">
                             <input type="hidden" name="password" value="{{ last_pass }}">
                             <input type="hidden" name="id" value="{{ item.id }}">
                             <button class="delete-btn" onclick="return confirm('Cancel this message?')">Cancel</button>
                        </form>
                    </li>
                {% endfor %}
                </ul>
            {% else %}
                <p style="text-align: center; color: #99aab5; margin-top: 50px;">No messages scheduled.</p>
            {% endif %}
        </div>
    </div>
</body>
</html>
"""


@app.route('/', methods=['GET', 'POST'])
def home():
    # 1. Check if we just loaded the page with a success message in the URL
    status_msg = request.args.get('msg', "")
    status_type = request.args.get('type', "")
    last_pass = ""

    # 2. Handle the Form Submission
    if request.method == 'POST':
        last_pass = request.form.get('password')

        # Password Check
        if last_pass != WEB_PASS:
            status_msg = "Wrong Password!"
            status_type = "error"
        else:
            # Gather Data
            message = request.form.get('content')
            raw_time = request.form.get('datetime')
            raw_channel = request.form.get('channel_select')

            # Channel Logic
            if raw_channel:
                ch_data = raw_channel.split('|')
                channel_id = ch_data[0]
                channel_name = ch_data[1] if len(ch_data) > 1 else "Unknown"
            else:
                channel_id = DEFAULT_CID
                channel_name = "Default"

            # Save to DB
            if message and raw_time:
                try:
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    c.execute("INSERT INTO queue (message, send_time, channel_id, channel_name) VALUES (?, ?, ?, ?)",
                              (message, raw_time, channel_id, channel_name))
                    conn.commit()
                    conn.close()

                    # --- THE CRITICAL FIX ---
                    # Instead of showing the page immediately, we REDIRECT the browser.
                    # This clears the "form submission" memory.
                    return redirect(url_for('home', msg="Message Scheduled!", type="success"))

                except Exception as e:
                    status_msg = f"Database Error: {e}"
                    status_type = "error"

    # 3. Load the Queue for display (happens on every load/refresh)
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id, message, send_time, channel_name FROM queue ORDER BY send_time ASC")
    rows = c.fetchall()
    conn.close()

    queue_data = [{'id': r[0], 'msg': r[1], 'time': r[2].replace('T', ' '), 'ch_name': r[3]} for r in rows]
    server_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    return render_template_string(HTML_TEMPLATE,
                                  msg=status_msg,
                                  type=status_type,
                                  channels=known_channels,
                                  queue=queue_data,
                                  default_cid=DEFAULT_CID,
                                  server_time=server_time,
                                  last_pass=last_pass)

@app.route('/delete', methods=['POST'])
def delete_msg():
    if request.form.get('password') != WEB_PASS:
        return "Wrong Password"

    msg_id = request.form.get('id')
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM queue WHERE id = ?", (msg_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('home'))


def run_flask():
    import logging
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)
    app.run(host='0.0.0.0', port=PORT, debug=False, use_reloader=False)


# --- DISCORD BOT ---
intents = discord.Intents.default()
intents.guilds = True  # Required to see channel lists

client = discord.Client(intents=intents)


@tasks.loop(minutes=1)
async def update_channel_list():
    """Updates the global list of channels for the dropdown."""
    global known_channels
    temp_list = []
    # Loop through all servers (guilds) the bot is in
    for guild in client.guilds:
        for channel in guild.text_channels:
            if channel.permissions_for(guild.me).send_messages:
                temp_list.append({'id': channel.id, 'name': f"{guild.name} - {channel.name}"})
    known_channels = temp_list
    # If list is empty, user might not have invited bot yet
    if not known_channels:
        print("[WARN] No channels found. Is the bot in a server?")


@tasks.loop(seconds=30)
async def check_schedule():
    current_time = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M")
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id, message, channel_id FROM queue WHERE send_time <= ?", (current_time,))
    rows = c.fetchall()

    for row in rows:
        msg_id, msg_content, cid = row
        try:
            channel = client.get_channel(int(cid))
            if channel:
                await channel.send(msg_content)
                print(f"[SENT] Message to {cid}")
            else:
                print(f"[ERROR] Could not find channel {cid}")
        except Exception as e:
            print(f"[ERROR] Failed to send: {e}")

        c.execute("DELETE FROM queue WHERE id = ?", (msg_id,))

    conn.commit()
    conn.close()


@client.event
async def on_ready():
    print(f'Logged in as {client.user}')
    init_db()
    check_schedule.start()
    update_channel_list.start()


# --- MAIN ---
if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    client.run(TOKEN)