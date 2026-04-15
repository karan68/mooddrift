"""Generate natural-language summaries using Groq LLM (Llama)."""

import httpx
from config import settings

GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"


def generate_summary(prompt: str) -> str:
    """Send a prompt to Groq LLM and return the response text."""
    resp = httpx.post(
        GROQ_CHAT_URL,
        headers={
            "Authorization": f"Bearer {settings.groq_api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": "llama-3.3-70b-versatile",
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a warm, empathetic emotional wellness companion. "
                        "You speak like a supportive friend, not a clinician. "
                        "Keep responses under 100 words. Never diagnose. "
                        "Be specific about what the user shared. "
                        "If coping strategies exist, mention them gently as suggestions."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.7,
            "max_tokens": 200,
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()
