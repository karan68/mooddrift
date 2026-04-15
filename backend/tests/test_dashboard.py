import pytest
import json
import uuid

from fastapi.testclient import TestClient

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from main import app

client = TestClient(app)


class TestGetEntries:
    @pytest.mark.integration
    def test_get_entries_default_user(self):
        resp = client.get("/api/entries")
        assert resp.status_code == 200
        data = resp.json()
        assert "entries" in data
        assert "total" in data
        assert isinstance(data["entries"], list)

    @pytest.mark.integration
    def test_get_entries_with_days(self):
        resp = client.get("/api/entries?days=30")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data["entries"], list)

    @pytest.mark.integration
    def test_get_entries_sorted_descending(self):
        resp = client.get("/api/entries?days=90")
        entries = resp.json()["entries"]
        if len(entries) >= 2:
            dates = [e["timestamp"] for e in entries]
            assert dates == sorted(dates, reverse=True)

    @pytest.mark.integration
    def test_get_entries_has_required_fields(self):
        resp = client.get("/api/entries?days=90")
        entries = resp.json()["entries"]
        if entries:
            entry = entries[0]
            assert "id" in entry
            assert "date" in entry
            assert "transcript" in entry
            assert "sentiment_score" in entry
            assert "keywords" in entry

    @pytest.mark.integration
    def test_get_entries_nonexistent_user(self):
        resp = client.get(f"/api/entries?user_id=nonexistent_{uuid.uuid4().hex[:8]}")
        assert resp.status_code == 200
        assert resp.json()["total"] == 0


class TestDriftTimeline:
    @pytest.mark.integration
    def test_drift_timeline(self):
        resp = client.get("/api/drift-timeline")
        assert resp.status_code == 200
        data = resp.json()
        assert "timeline" in data

    @pytest.mark.integration
    def test_drift_timeline_has_fields(self):
        resp = client.get("/api/drift-timeline?days=90")
        timeline = resp.json()["timeline"]
        if timeline:
            point = timeline[0]
            assert "week" in point
            assert "drift_score" in point
            assert "avg_sentiment" in point
            assert "entry_count" in point

    @pytest.mark.integration
    def test_drift_timeline_scores_range(self):
        resp = client.get("/api/drift-timeline?days=90")
        for point in resp.json()["timeline"]:
            assert 0.0 <= point["drift_score"] <= 2.0


class TestDriftCurrent:
    @pytest.mark.integration
    def test_drift_current(self):
        resp = client.get("/api/drift-current")
        assert resp.status_code == 200
        data = resp.json()
        assert "detected" in data
        assert "drift_score" in data
        assert "severity" in data
        assert "message" in data

    @pytest.mark.integration
    def test_drift_current_near_threshold_with_seed_data(self):
        """Drift score should be near/above threshold with seeded data.
        May be marginally below if other tests added demo_user entries."""
        resp = client.get("/api/drift-current")
        data = resp.json()
        assert data["drift_score"] >= 0.22, (
            f"Drift score too low: {data['drift_score']}"
        )


class TestVisualization:
    @pytest.mark.integration
    @pytest.mark.slow
    def test_visualization(self):
        resp = client.get("/api/visualization?days=90")
        assert resp.status_code == 200
        data = resp.json()
        assert "points" in data

    @pytest.mark.integration
    @pytest.mark.slow
    def test_visualization_has_coordinates(self):
        resp = client.get("/api/visualization?days=90")
        points = resp.json()["points"]
        if points:
            p = points[0]
            assert "x" in p
            assert "y" in p
            assert "date" in p
            assert "sentiment_score" in p
            assert isinstance(p["x"], float)
            assert isinstance(p["y"], float)

    @pytest.mark.integration
    @pytest.mark.slow
    def test_visualization_nonexistent_user(self):
        resp = client.get(f"/api/visualization?user_id=nonexistent_{uuid.uuid4().hex[:8]}")
        assert resp.status_code == 200
        assert resp.json()["points"] == []
