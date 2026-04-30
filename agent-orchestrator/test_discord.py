import os

import requests
from dotenv import load_dotenv

# Load values from .env into this Python process.
load_dotenv()

# Read the Discord webhook URL from the environment.
webhook_url = os.getenv("DISCORD_WEBHOOK_URL")

# Stop early if the webhook is missing.
if not webhook_url:
    raise RuntimeError("DISCORD_WEBHOOK_URL is missing from .env")

# This is the message Discord will receive.
payload = {
    "content": "[ORCHESTRATOR TEST] Discord webhook is working."
}

# Send the message to Discord.
response = requests.post(webhook_url, json=payload, timeout=10)

# Raise an error if Discord rejected the request.
response.raise_for_status()

print("Discord test message sent.")