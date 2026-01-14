import discord
from discord.ext import tasks
from flask import Flask, request, render_template_string, redirect, url_for
import sqlite3
import datetime
import json
import threading
import asyncio
import time
import sys

# --- CONFIGURATION LOAD ---
try:
    with open('config.json', 'r') as f:
        config = json.load(f)
    TOKEN = config['bot_token']
    PORT = config['web_port']
    WEB_PASS = config['web_password']
    DEFAULT_CID = config['default_channel_id']
except FileNotFoundError:
    print("❌ FATAL: 'config.json' not found. Please create it.")
    sys.exit(1)
except KeyError as e:
    print(f"❌ FATAL: Missing key in config.json: {e}")
    sys.exit(1)

# --- SHARED STATE ---
known_channels = []
known_roles = []

# --- DATABASE SETUP ---
DB_FILE = "scheduler.db"


def log(msg, level="INFO"):
    """Simple logger with timestamps."""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{level}] {msg}")


def init_db():
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        # Added 'role_id' and 'role_name' columns
        c.execute('''CREATE TABLE IF NOT EXISTS queue
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      message TEXT,
                      send_time TEXT,
                      channel_id INTEGER,
                      channel_name TEXT,
                      role_id INTEGER,
                      role_name TEXT)''')
        conn.commit()
        conn.close()
        log("Database connected and checked.")
    except sqlite3.Error as e:
        log(f"Database initialization failed: {e}", "CRITICAL")
        sys.exit(1)


# --- FLASK WEB SERVER ---
app = Flask(__name__)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Discord Scheduler</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        :root { --bg: #2c2f33; --panel: #23272a; --input: #40444b; --text: #fff; --primary: #7289da; --danger: #f04747; --success: #43b581; --warning: #faa61a; }
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
        .ping-badge { background: #7289da; color: white; padding: 2px 6px; border-radius: 4px; font-size: 0.8em; margin-right: 5px; }
        .delete-btn { background: var(--danger); width: auto; padding: 5px 10px; font-size: 0.8em; position: absolute; top: 10px; right: 10px; }
        .delete-btn:hover { background: #c03535; }

        .flash { padding: 10px; border-radius: 4px; margin-bottom: 20px; text-align: center; font-weight: bold; }
        .flash.success { background: rgba(67, 181, 129, 0.2); border: 1px solid var(--success); color: var(--success); }
        .flash.error { background: rgba(240, 71, 71, 0.2); border: 1px solid var(--danger); color: var(--danger); }
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

                <label>Ping Role (Optional)</label>
                <select name="role_select">
                    <option value="none">-- No Ping --</option>
                    <option value="everyone">@everyone</option>
                    <option value="here">@here</option>
                    {% for r in roles %}
                        <option value="{{ r.id }}|{{ r.name }}">{{ r.name }}</option>
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
                        <div class="msg-content">{% if item.role_name %}<span class="ping-badge">@{{ item.role_name }}</span>{% endif %}{{ item.msg }}</div>
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
    status_msg = request.args.get('msg', "")
    status_type = request.args.get('type', "")
    last_pass = ""

    if request.method == 'POST':
        last_pass = request.form.get('password')

        if last_pass != WEB_PASS:
            status_msg = "⛔ Incorrect Password"
            status_type = "error"
        else:
            message = request.form.get('content')
            raw_time = request.form.get('datetime')
            raw_channel = request.form.get('channel_select')
            raw_role = request.form.get('role_select')

            # Parse Channel
            if raw_channel:
                try:
                    ch_data = raw_channel.split('|')
                    channel_id = ch_data[0]
                    channel_name = ch_data[1] if len(ch_data) > 1 else "Unknown"
                except Exception:
                    channel_id = DEFAULT_CID
                    channel_name = "Default (Parse Error)"
            else:
                channel_id = DEFAULT_CID
                channel_name = "Default"

            # Parse Role
            role_id = None
            role_name = None

            if raw_role == "everyone":
                role_id = "everyone"
                role_name = "everyone"
            elif raw_role == "here":
                role_id = "here"
                role_name = "here"
            elif raw_role and raw_role != "none":
                try:
                    r_data = raw_role.split('|')
                    role_id = r_data[0]
                    role_name = r_data[1] if len(r_data) > 1 else "Role"
                except:
                    role_id = None

            # Save to DB
            if message and raw_time:
                try:
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    c.execute(
                        "INSERT INTO queue (message, send_time, channel_id, channel_name, role_id, role_name) VALUES (?, ?, ?, ?, ?, ?)",
                        (message, raw_time, channel_id, channel_name, role_id, role_name))
                    conn.commit()
                    conn.close()
                    log(f"WebUI: Scheduled message for {channel_name} at {raw_time}")
                    return redirect(url_for('home', msg="✅ Message Scheduled!", type="success"))

                except sqlite3.OperationalError as e:
                    status_msg = f"❌ Database Locked/Error: {e}"
                    status_type = "error"
                    log(f"WebUI DB Error: {e}", "ERROR")
                except Exception as e:
                    status_msg = f"❌ Unexpected Error: {e}"
                    status_type = "error"
                    log(f"WebUI Unknown Error: {e}", "ERROR")

    # Fetch Queue
    queue_data = []
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT id, message, send_time, channel_name, role_name FROM queue ORDER BY send_time ASC")
        rows = c.fetchall()
        conn.close()
        queue_data = [{'id': r[0], 'msg': r[1], 'time': r[2].replace('T', ' '), 'ch_name': r[3], 'role_name': r[4]} for
                      r in rows]
    except sqlite3.Error as e:
        log(f"Failed to fetch queue: {e}", "ERROR")

    server_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    return render_template_string(HTML_TEMPLATE,
                                  msg=status_msg,
                                  type=status_type,
                                  channels=known_channels,
                                  roles=known_roles,
                                  queue=queue_data,
                                  default_cid=DEFAULT_CID,
                                  server_time=server_time,
                                  last_pass=last_pass)


@app.route('/delete', methods=['POST'])
def delete_msg():
    if request.form.get('password') != WEB_PASS:
        return "Wrong Password"

    msg_id = request.form.get('id')
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("DELETE FROM queue WHERE id = ?", (msg_id,))
        conn.commit()
        conn.close()
        log(f"WebUI: Deleted message ID {msg_id}")
    except sqlite3.Error as e:
        log(f"Failed to delete message: {e}", "ERROR")

    return redirect(url_for('home'))


def run_flask():
    import logging
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)
    app.run(host='0.0.0.0', port=PORT, debug=False, use_reloader=False)


# --- DISCORD BOT ---
intents = discord.Intents.default()
intents.guilds = True
intents.members = True  # Needed to see members/roles properly sometimes

client = discord.Client(intents=intents)


@tasks.loop(minutes=1)
async def update_discord_data():
    """Updates the global list of channels AND roles."""
    global known_channels
    global known_roles

    # 1. Update Channels
    temp_channels = []
    temp_roles = []

    try:
        for guild in client.guilds:
            # Channels
            for channel in guild.text_channels:
                if channel.permissions_for(guild.me).send_messages:
                    temp_channels.append({'id': channel.id, 'name': f"{guild.name} - {channel.name}"})

            # Roles (Filter out managed/bot roles usually)
            for role in guild.roles:
                if not role.is_default() and not role.managed:
                    temp_roles.append({'id': role.id, 'name': f"{guild.name} - {role.name}"})

        known_channels = temp_channels
        known_roles = temp_roles

    except Exception as e:
        log(f"Error updating discord data: {e}", "WARN")


@tasks.loop(seconds=30)
async def check_schedule():
    current_time = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M")

    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT id, message, channel_id, role_id FROM queue WHERE send_time <= ?", (current_time,))
        rows = c.fetchall()
    except sqlite3.Error as e:
        log(f"DB Error checking schedule: {e}", "ERROR")
        return

    for row in rows:
        msg_id, msg_content, cid, role_id = row

        # Construct the ping
        ping_str = ""
        if role_id == "everyone":
            ping_str = "@everyone "
        elif role_id == "here":
            ping_str = "@here "
        elif role_id:  # It's a specific ID
            ping_str = f"<@&{role_id}> "

        final_message = f"{ping_str}{msg_content}"

        try:
            channel = client.get_channel(int(cid))
            if channel:
                await channel.send(final_message)
                log(f"✅ SENT message to channel {cid} with ping {role_id}")
            else:
                log(f"❌ FAILED: Channel {cid} not found", "ERROR")

        except discord.Forbidden:
            log(f"⛔ PERMISSION DENIED: Cannot send to channel {cid}.", "ERROR")
        except Exception as e:
            log(f"❌ UNKNOWN ERROR sending to {cid}: {e}", "ERROR")

        # Cleanup
        try:
            c.execute("DELETE FROM queue WHERE id = ?", (msg_id,))
        except sqlite3.Error as e:
            log(f"Failed to remove sent message from DB: {e}", "CRITICAL")

    conn.commit()
    conn.close()


@client.event
async def on_ready():
    log(f'Logged in as {client.user}')
    init_db()
    check_schedule.start()
    update_discord_data.start()


if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    try:
        client.run(TOKEN)
    except Exception as e:
        print(f"\n❌ CRITICAL: Failed to start bot: {e}")