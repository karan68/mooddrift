"""
Register the Telegram webhook URL.

Usage:
  cd backend && python scripts/setup_telegram.py --url https://mooddrift-api.onrender.com
"""

import argparse
import sys

import httpx

sys.path.insert(0, ".")
from config import settings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True, help="Public base URL of backend")
    args = parser.parse_args()

    token = settings.telegram_bot_token
    if not token:
        print("Error: TELEGRAM_BOT_TOKEN not set in .env")
        sys.exit(1)

    webhook_url = f"{args.url}/telegram/webhook"
    resp = httpx.post(
        f"https://api.telegram.org/bot{token}/setWebhook",
        json={"url": webhook_url},
        timeout=10,
    )
    data = resp.json()
    if data.get("ok"):
        print(f"Webhook set: {webhook_url}")
    else:
        print(f"Error: {data}")

    # Get bot info
    resp = httpx.get(f"https://api.telegram.org/bot{token}/getMe", timeout=10)
    bot = resp.json().get("result", {})
    print(f"Bot: @{bot.get('username')}")


if __name__ == "__main__":
    main()
