# Discord Message Scheduler Bot

A simple Python Discord bot that hosts a local frontend Web UI, allowing you to schedule messages to be sent to specific Discord servers and channels at a later date and time.

## Features

* **Web Dashboard:** Clean, password-protected interface to manage messages.
* **Channel Selection:** Automatically pulls text channels from your server for easy selection.
* **Queue Management:** View upcoming messages and cancel them if needed.
* **Persistent Storage:** Uses a local SQLite database, so scheduled messages survive bot restarts.

## Prerequisites

* Python 3.8 or higher
* A Discord Account

## Setup Guide

### 1. Discord Developer Portal (Bot Creation)

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications).
2. Click **New Application** and give it a name.
3. **Create the Bot:**
* Click **Bot** on the left sidebar.
* Click **Add Bot** -> **Yes, do it!**
* **IMPORTANT:** Scroll down to "Privileged Gateway Intents" and enable **Message Content Intent** and **Server Members Intent**. Save Changes.
* Click **Reset Token** and copy this token. You will need it for the config file.


4. **Invite the Bot:**
* Click **OAuth2** -> **URL Generator**.
* Check `bot`.
* Check permissions: `Read Messages/View Channels`, `Send Messages`, `Read Message History`.
* Copy the generated URL at the bottom and paste it into your browser to invite the bot to your server.



### 2. Installation (Server Side)

Clone this repository to your machine:

```bash
git clone https://github.com/yourusername/discord-scheduler-bot.git
cd discord-scheduler-bot

```

Install the required dependencies:

```bash
pip install -r requirements.txt

```

### 3. Configuration

Rename or edit the `config.json` file. It should look like this:

```json
{
    "bot_token": "PASTE_YOUR_BOT_TOKEN_HERE",
    "web_port": 5000,
    "web_password": "change_this_password",
    "default_channel_id": 123456789012345678
}

```

* **bot_token:** The token you copied from the Developer Portal.
* **web_password:** The password required to access the Web UI.
* **default_channel_id:** (Optional) A fallback Channel ID. Enable Developer Mode in Discord settings, right-click a channel, and select "Copy ID".

### 4. Running the Bot

Start the bot using Python:

```bash
python bot.py

```

If successful, you will see `Logged in as [BotName]` in the console.

## Usage

1. Open your web browser.
* **Local:** Go to `http://127.0.0.1:5000`
* **Remote:** Go to `http://YOUR_SERVER_IP:5000`


2. Enter the password you set in `config.json`.
3. Select a channel, type your message, and pick a date/time.
4. Click **Schedule It**.

## Troubleshooting

* **Dropdown is empty?** Restart the bot. It scans for channels on startup and updates every minute.
* **Timezone issues?** The bot uses the system time of the machine it is running on.
* **Database Error?** If you update the code and get database errors, delete the `scheduler.db` file and restart the bot to generate a fresh one.
