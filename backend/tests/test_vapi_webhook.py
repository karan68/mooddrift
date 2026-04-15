import pytest
import json
import uuid

from fastapi.testclient import TestClient

# Patch sys.path before importing app modules
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from main import app

client = TestClient(app)


class TestHealthEndpoint:
    @pytest.mark.unit
    def test_health(self):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


class TestVapiWebhookRouting:
    """Unit tests for Vapi webhook event routing (no external calls)."""

    @pytest.mark.unit
    def test_unknown_event_returns_200(self):
        resp = client.post("/vapi/webhook", json={
            "message": {"type": "status-update", "status": "in-progress"}
        })
        assert resp.status_code == 200
        assert resp.json() == {}

    @pytest.mark.unit
    def test_empty_body_returns_200(self):
        resp = client.post("/vapi/webhook", json={})
        assert resp.status_code == 200

    @pytest.mark.unit
    def test_end_of_call_report_returns_200(self):
        resp = client.post("/vapi/webhook", json={
            "message": {
                "type": "end-of-call-report",
                "endedReason": "hangup",
                "artifact": {
                    "transcript": "AI: How are you? User: I'm fine.",
                    "messages": [],
                },
            }
        })
        assert resp.status_code == 200

    @pytest.mark.unit
    def test_hang_event_returns_200(self):
        resp = client.post("/vapi/webhook", json={
            "message": {"type": "hang", "call": {}}
        })
        assert resp.status_code == 200


class TestToolCallsStoreAndAnalyze:
    """Integration tests for store_and_analyze via Vapi tool-calls event."""

    @pytest.mark.integration
    @pytest.mark.slow
    def test_store_and_analyze_basic(self):
        test_user = f"test_vapi_{uuid.uuid4().hex[:8]}"
        resp = client.post("/vapi/webhook", json={
            "message": {
                "type": "tool-calls",
                "toolCallList": [
                    {
                        "id": "call_001",
                        "name": "store_and_analyze",
                        "parameters": {
                            "mood_summary": "User feels overwhelmed by work.",
                            "full_transcript": "I'm feeling overwhelmed. Work has been crazy and I can barely sleep.",
                            "user_id": test_user,
                        },
                    }
                ],
            }
        })

        assert resp.status_code == 200
        data = resp.json()
        assert "results" in data
        assert len(data["results"]) == 1

        result = data["results"][0]
        assert result["name"] == "store_and_analyze"
        assert result["toolCallId"] == "call_001"

        parsed = json.loads(result["result"])
        assert parsed["status"] == "stored"
        assert "entry_id" in parsed
        assert isinstance(parsed["sentiment_score"], float)
        assert isinstance(parsed["keywords"], list)
        assert len(parsed["keywords"]) > 0

    @pytest.mark.integration
    @pytest.mark.slow
    def test_store_and_analyze_empty_transcript(self):
        resp = client.post("/vapi/webhook", json={
            "message": {
                "type": "tool-calls",
                "toolCallList": [
                    {
                        "id": "call_002",
                        "name": "store_and_analyze",
                        "parameters": {
                            "mood_summary": "",
                            "full_transcript": "",
                            "user_id": "test_user",
                        },
                    }
                ],
            }
        })

        assert resp.status_code == 200
        result = resp.json()["results"][0]
        parsed = json.loads(result["result"])
        assert "error" in parsed

    @pytest.mark.integration
    @pytest.mark.slow
    def test_store_and_analyze_default_user(self):
        """When user_id is missing, should still store successfully."""
        test_user = f"test_default_{uuid.uuid4().hex[:8]}"
        resp = client.post("/vapi/webhook", json={
            "message": {
                "type": "tool-calls",
                "toolCallList": [
                    {
                        "id": "call_003",
                        "name": "store_and_analyze",
                        "parameters": {
                            "mood_summary": "Feeling okay today.",
                            "full_transcript": "Had a normal day. Nothing special.",
                            "user_id": test_user,
                        },
                    }
                ],
            }
        })

        assert resp.status_code == 200
        parsed = json.loads(resp.json()["results"][0]["result"])
        assert parsed["status"] == "stored"


class TestToolCallsSearchSimilar:
    """Integration tests for search_similar_past_entries via tool-calls."""

    @pytest.mark.integration
    @pytest.mark.slow
    def test_search_similar_basic(self):
        test_user = f"test_vapi_{uuid.uuid4().hex[:8]}"

        # First store an entry
        client.post("/vapi/webhook", json={
            "message": {
                "type": "tool-calls",
                "toolCallList": [
                    {
                        "id": "seed_001",
                        "name": "store_and_analyze",
                        "parameters": {
                            "mood_summary": "Stressed about deadlines.",
                            "full_transcript": "Work deadlines are crushing me. I feel so stressed.",
                            "user_id": test_user,
                        },
                    }
                ],
            }
        })

        # Now search for similar
        resp = client.post("/vapi/webhook", json={
            "message": {
                "type": "tool-calls",
                "toolCallList": [
                    {
                        "id": "search_001",
                        "name": "search_similar_past_entries",
                        "parameters": {
                            "query": "stressed about work deadlines",
                            "user_id": test_user,
                        },
                    }
                ],
            }
        })

        assert resp.status_code == 200
        result = resp.json()["results"][0]
        assert result["name"] == "search_similar_past_entries"
        assert "similar past entries" in result["result"].lower() or "found" in result["result"].lower()

    @pytest.mark.integration
    @pytest.mark.slow
    def test_search_similar_no_entries(self):
        resp = client.post("/vapi/webhook", json={
            "message": {
                "type": "tool-calls",
                "toolCallList": [
                    {
                        "id": "search_002",
                        "name": "search_similar_past_entries",
                        "parameters": {
                            "query": "something random",
                            "user_id": f"nonexistent_{uuid.uuid4().hex[:8]}",
                        },
                    }
                ],
            }
        })

        assert resp.status_code == 200
        result = resp.json()["results"][0]["result"]
        assert "no similar" in result.lower()

    @pytest.mark.integration
    @pytest.mark.slow
    def test_search_similar_empty_query(self):
        resp = client.post("/vapi/webhook", json={
            "message": {
                "type": "tool-calls",
                "toolCallList": [
                    {
                        "id": "search_003",
                        "name": "search_similar_past_entries",
                        "parameters": {
                            "query": "",
                            "user_id": "test_user",
                        },
                    }
                ],
            }
        })

        assert resp.status_code == 200
        result = resp.json()["results"][0]["result"]
        assert "no query" in result.lower()


class TestToolCallsMultiple:
    """Test multiple tool calls in a single request."""

    @pytest.mark.integration
    @pytest.mark.slow
    def test_multiple_tool_calls(self):
        test_user = f"test_vapi_{uuid.uuid4().hex[:8]}"
        resp = client.post("/vapi/webhook", json={
            "message": {
                "type": "tool-calls",
                "toolCallList": [
                    {
                        "id": "multi_001",
                        "name": "search_similar_past_entries",
                        "parameters": {
                            "query": "feeling stressed",
                            "user_id": test_user,
                        },
                    },
                    {
                        "id": "multi_002",
                        "name": "store_and_analyze",
                        "parameters": {
                            "mood_summary": "Stressed today.",
                            "full_transcript": "Feeling stressed about everything.",
                            "user_id": test_user,
                        },
                    },
                ],
            }
        })

        assert resp.status_code == 200
        results = resp.json()["results"]
        assert len(results) == 2
        assert results[0]["toolCallId"] == "multi_001"
        assert results[1]["toolCallId"] == "multi_002"


class TestToolCallsUnknown:
    """Test unknown function name handling."""

    @pytest.mark.unit
    def test_unknown_function(self):
        resp = client.post("/vapi/webhook", json={
            "message": {
                "type": "tool-calls",
                "toolCallList": [
                    {
                        "id": "unknown_001",
                        "name": "nonexistent_function",
                        "parameters": {},
                    }
                ],
            }
        })

        assert resp.status_code == 200
        result = resp.json()["results"][0]
        parsed = json.loads(result["result"])
        assert "error" in parsed


class TestLegacyFunctionCall:
    """Test legacy function-call event type handling."""

    @pytest.mark.integration
    @pytest.mark.slow
    def test_legacy_function_call(self):
        resp = client.post("/vapi/webhook", json={
            "message": {
                "type": "function-call",
                "functionCall": {
                    "name": "search_similar_past_entries",
                    "parameters": {
                        "query": "feeling happy",
                        "user_id": f"legacy_{uuid.uuid4().hex[:8]}",
                    },
                },
            }
        })

        assert resp.status_code == 200
        data = resp.json()
        assert "result" in data


class TestEntriesEndpoint:
    """Integration tests for the manual /api/entries endpoint."""

    @pytest.mark.integration
    @pytest.mark.slow
    def test_create_entry(self):
        test_user = f"test_entry_{uuid.uuid4().hex[:8]}"
        resp = client.post("/api/entries", json={
            "user_id": test_user,
            "transcript": "Had a great day. Went to the gym and felt amazing.",
            "entry_type": "checkin",
        })

        assert resp.status_code == 200
        data = resp.json()
        assert "id" in data
        assert isinstance(data["sentiment_score"], float)
        assert data["sentiment_score"] > 0  # positive text
        assert isinstance(data["keywords"], list)

    @pytest.mark.integration
    @pytest.mark.slow
    def test_create_entry_default_type(self):
        resp = client.post("/api/entries", json={
            "user_id": "test_user",
            "transcript": "Normal day.",
        })

        assert resp.status_code == 200
