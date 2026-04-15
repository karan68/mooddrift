"""
Script to create the MoodDrift Vapi assistant via API.

Usage:
  cd backend
  python scripts/create_assistant.py --server-url https://your-ngrok-url.ngrok.io

Requires VAPI_API_KEY and GROQ_API_KEY in .env
"""

import argparse
import json
import sys

import httpx

sys.path.insert(0, "..")
sys.path.insert(0, ".")
from config import settings

VAPI_BASE = "https://api.vapi.ai"


def add_groq_credential(api_key: str, groq_key: str) -> str | None:
    """Add Groq API key as a credential in Vapi. Returns credential ID."""
    # First check if a groq credential already exists
    resp = httpx.get(
        f"{VAPI_BASE}/credential",
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=15,
    )
    resp.raise_for_status()
    for cred in resp.json():
        if cred.get("provider") == "groq":
            print(f"  Groq credential already exists: {cred['id']}")
            return cred["id"]

    # Create new credential
    resp = httpx.post(
        f"{VAPI_BASE}/credential",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "provider": "groq",
            "apiKey": groq_key,
            "name": "groq",
        },
        timeout=15,
    )
    resp.raise_for_status()
    cred_id = resp.json()["id"]
    print(f"  Created Groq credential: {cred_id}")
    return cred_id


def create_assistant(api_key: str, server_url: str) -> dict:
    """Create the MoodDrift assistant in Vapi."""
    with open("../vapi/assistant_config.json") as f:
        config = json.load(f)

    # Set the server URL
    config["server"]["url"] = f"{server_url}/vapi/webhook"

    resp = httpx.post(
        f"{VAPI_BASE}/assistant",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=config,
        timeout=30,
    )

    if resp.status_code != 201:
        print(f"Error creating assistant: {resp.status_code}")
        print(resp.text)
        sys.exit(1)

    return resp.json()


def main():
    parser = argparse.ArgumentParser(description="Create MoodDrift Vapi assistant")
    parser.add_argument(
        "--server-url",
        required=True,
        help="Public URL of your backend (e.g. https://abc123.ngrok.io)",
    )
    args = parser.parse_args()

    api_key = settings.vapi_api_key
    groq_key = settings.groq_api_key

    if not api_key:
        print("Error: VAPI_API_KEY not set in .env")
        sys.exit(1)
    if not groq_key:
        print("Error: GROQ_API_KEY not set in .env")
        sys.exit(1)

    print("[1/2] Adding Groq credential to Vapi...")
    add_groq_credential(api_key, groq_key)

    print(f"[2/2] Creating assistant (server: {args.server_url})...")
    assistant = create_assistant(api_key, args.server_url)

    assistant_id = assistant["id"]
    print(f"\nAssistant created successfully!")
    print(f"  ID: {assistant_id}")
    print(f"  Name: {assistant.get('name')}")
    print(f"\nAdd this to your .env:")
    print(f"  VAPI_ASSISTANT_ID={assistant_id}")


if __name__ == "__main__":
    main()
