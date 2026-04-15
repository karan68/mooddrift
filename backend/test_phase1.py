"""
Phase 1 verification script.
Tests: embedding generation, sentiment, keywords, Qdrant upsert/scroll/search.

Usage:  cd backend && python test_phase1.py
Requires: .env file with QDRANT_URL, QDRANT_API_KEY, OPENAI_API_KEY
"""

import sys
from datetime import datetime, timezone

from config import settings
from services.embedding import generate_embedding
from services.sentiment import analyze_sentiment
from services.keywords import extract_keywords
from services.qdrant_service import (
    create_collection,
    upsert_entry,
    scroll_entries,
    search_similar,
)


def main():
    passed = 0
    failed = 0

    sample_text = (
        "I'm feeling pretty overwhelmed today. "
        "Work has been crazy this week and my manager keeps adding tasks. "
        "I can barely sleep, maybe 4 hours a night."
    )

    # --- Test 1: Sentiment analysis (local, no API) ---
    print("\n[1/6] Testing sentiment analysis...")
    try:
        score = analyze_sentiment(sample_text)
        assert -1.0 <= score <= 1.0, f"Score out of range: {score}"
        print(f"  Sentiment score: {score}")
        passed += 1
    except Exception as e:
        print(f"  FAILED: {e}")
        failed += 1

    # --- Test 2: Keyword extraction (local, no API) ---
    print("\n[2/6] Testing keyword extraction...")
    try:
        keywords = extract_keywords(sample_text)
        assert isinstance(keywords, list), "Expected list"
        assert len(keywords) > 0, "No keywords extracted"
        print(f"  Keywords: {keywords}")
        passed += 1
    except Exception as e:
        print(f"  FAILED: {e}")
        failed += 1

    # --- Test 3: Embedding generation (requires OpenAI key) ---
    print("\n[3/6] Testing embedding generation...")
    try:
        vector = generate_embedding(sample_text)
        assert isinstance(vector, list), "Expected list"
        assert len(vector) == settings.embedding_dim, (
            f"Expected {settings.embedding_dim} dims, got {len(vector)}"
        )
        print(f"  Embedding dim: {len(vector)}")
        passed += 1
    except Exception as e:
        print(f"  FAILED: {e}")
        failed += 1
        print("  Cannot continue without embedding. Exiting.")
        sys.exit(1)

    # --- Test 4: Qdrant collection creation ---
    print("\n[4/6] Testing Qdrant collection creation...")
    try:
        create_collection()
        print(f"  Collection '{settings.collection_name}' ready")
        passed += 1
    except Exception as e:
        print(f"  FAILED: {e}")
        failed += 1
        print("  Cannot continue without Qdrant. Exiting.")
        sys.exit(1)

    # --- Test 5: Upsert entry ---
    print("\n[5/6] Testing Qdrant upsert...")
    try:
        now = datetime.now(timezone.utc)
        payload = {
            "user_id": settings.default_user_id,
            "date": now.strftime("%Y-%m-%d"),
            "timestamp": int(now.timestamp()),
            "transcript": sample_text,
            "sentiment_score": score,
            "keywords": keywords,
            "week_number": now.isocalendar()[1],
            "month": now.strftime("%Y-%m"),
            "entry_type": "checkin",
        }
        point_id = upsert_entry(vector, payload)
        print(f"  Upserted point: {point_id}")
        passed += 1
    except Exception as e:
        print(f"  FAILED: {e}")
        failed += 1

    # --- Test 6: Scroll + Search ---
    print("\n[6/6] Testing Qdrant scroll & search...")
    try:
        entries = scroll_entries(user_id=settings.default_user_id)
        assert len(entries) > 0, "No entries found after upsert"
        print(f"  Scroll returned {len(entries)} entries")

        similar = search_similar(vector, user_id=settings.default_user_id, limit=1)
        assert len(similar) > 0, "No similar entries found"
        print(f"  Search returned {len(similar)} results (top score: {similar[0].score:.4f})")
        passed += 1
    except Exception as e:
        print(f"  FAILED: {e}")
        failed += 1

    # --- Summary ---
    print(f"\n{'='*40}")
    print(f"Phase 1 Results: {passed} passed, {failed} failed out of 6 tests")
    if failed == 0:
        print("All Phase 1 systems operational!")
    else:
        print("Some tests failed — check output above.")
    print(f"{'='*40}")

    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
