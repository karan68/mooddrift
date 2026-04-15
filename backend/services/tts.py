"""Text-to-speech via Microsoft Edge TTS (free, high quality)."""

import asyncio
import io
import edge_tts

VOICE = "en-IN-NeerjaNeural"  # Indian English female voice


async def _generate_speech(text: str) -> bytes:
    """Generate speech audio bytes from text."""
    communicate = edge_tts.Communicate(text, VOICE)
    buffer = io.BytesIO()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            buffer.write(chunk["data"])
    return buffer.getvalue()


def text_to_speech(text: str) -> bytes:
    """Synchronous wrapper: convert text to MP3 audio bytes."""
    return asyncio.run(_generate_speech(text))
