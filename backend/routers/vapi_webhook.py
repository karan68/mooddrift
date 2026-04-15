import json
from datetime import datetime, timezone

from fastapi import APIRouter, Request

from config import settings
from services.embedding import generate_embedding
from services.sentiment import analyze_sentiment
from services.keywords import extract_keywords
from services.qdrant_service import upsert_entry, search_similar
from services.drift_engine import detect_drift

router = APIRouter()


@router.post("/vapi/webhook")
async def vapi_webhook(request: Request):
    """Main Vapi webhook — handles all server event types."""
    body = await request.json()
    message = body.get("message", {})
    msg_type = message.get("type")

    if msg_type == "tool-calls":
        return handle_tool_calls(message)
    elif msg_type == "function-call":
        return handle_function_call(message)
    elif msg_type == "end-of-call-report":
        handle_end_of_call(message)

    # All other events (status-update, transcript, hang, etc.): acknowledge
    return {}


def handle_tool_calls(message: dict) -> dict:
    """Handle Vapi tool-calls event. Returns results for each tool call."""
    results = []
    for tool_call in message.get("toolCallList", []):
        name = tool_call.get("name")
        params = tool_call.get("parameters", {})
        call_id = tool_call.get("id")

        if name == "store_and_analyze":
            result = _store_and_analyze(params)
        elif name == "search_similar_past_entries":
            result = _search_similar_past(params)
        else:
            result = json.dumps({"error": f"Unknown function: {name}"})

        results.append({
            "name": name,
            "toolCallId": call_id,
            "result": result,
        })

    return {"results": results}


def handle_function_call(message: dict) -> dict:
    """Handle legacy Vapi function-call event."""
    fc = message.get("functionCall", message.get("function_call", {}))
    name = fc.get("name", "")
    params = fc.get("parameters", {})

    if name == "store_and_analyze":
        result = _store_and_analyze(params)
    elif name == "search_similar_past_entries":
        result = _search_similar_past(params)
    else:
        result = json.dumps({"error": f"Unknown function: {name}"})

    return {"result": result}


def handle_end_of_call(message: dict):
    """Process end-of-call report (logging only for now)."""
    artifact = message.get("artifact", {})
    transcript = artifact.get("transcript", "")
    if transcript:
        print(f"[end-of-call] transcript length: {len(transcript)}")


# --------------- Function implementations ---------------


def _store_and_analyze(params: dict) -> str:
    """Embed, analyze, and store a mood entry. Returns JSON result string."""
    user_id = params.get("user_id", settings.default_user_id)
    transcript = params.get("full_transcript", "")
    mood_summary = params.get("mood_summary", "")

    # Use mood_summary + transcript for richer embedding
    text_to_embed = f"{mood_summary} {transcript}".strip()
    if not text_to_embed:
        return json.dumps({"error": "No transcript provided"})

    # 1. Generate embedding
    vector = generate_embedding(text_to_embed)

    # 2. Analyze sentiment
    sentiment = analyze_sentiment(text_to_embed)

    # 3. Extract keywords
    keywords = extract_keywords(text_to_embed)

    # 4. Build payload
    now = datetime.now(timezone.utc)
    payload = {
        "user_id": user_id,
        "date": now.strftime("%Y-%m-%d"),
        "timestamp": int(now.timestamp()),
        "transcript": transcript,
        "sentiment_score": sentiment,
        "keywords": keywords,
        "week_number": now.isocalendar()[1],
        "month": now.strftime("%Y-%m"),
        "entry_type": "checkin",
    }

    # 5. Upsert to Qdrant
    point_id = upsert_entry(vector, payload)

    # 6. Run drift detection
    drift_result = detect_drift(user_id, new_entry_vector=vector)

    # 7. Build response
    response = {
        "status": "stored",
        "entry_id": point_id,
        "sentiment_score": sentiment,
        "keywords": keywords,
    }

    if drift_result["detected"]:
        response["drift_detected"] = True
        response["drift_severity"] = drift_result["severity"]
        response["drift_score"] = drift_result["drift_score"]
        response["message"] = drift_result["message"]
    elif drift_result["skipped"]:
        response["message"] = drift_result["message"]
    else:
        response["message"] = (
            f"Entry stored. Sentiment: {sentiment:.2f}. "
            f"Keywords: {', '.join(keywords)}. "
            f"{drift_result['message']}"
        )

    return json.dumps(response)


def _search_similar_past(params: dict) -> str:
    """Search Qdrant for past entries similar to the query. Returns formatted string."""
    query = params.get("query", "")
    user_id = params.get("user_id", settings.default_user_id)

    if not query:
        return "No query provided to search past entries."

    # 1. Generate embedding for query
    vector = generate_embedding(query)

    # 2. Search Qdrant
    results = search_similar(vector, user_id=user_id, limit=3)

    if not results:
        return (
            "No similar past entries found. "
            "This might be your first check-in or a new topic."
        )

    # 3. Format results for the agent
    entries = []
    for r in results:
        date = r.payload.get("date", "unknown date")
        transcript = r.payload.get("transcript", "")
        snippet = transcript[:150]
        entries.append(f"On {date}: \"{snippet}\"")

    return "I found similar past entries:\n" + "\n".join(entries)
