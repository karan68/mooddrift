import pytest

from services.keywords import extract_keywords


class TestKeywords:
    """Unit tests for keyword extraction."""

    @pytest.mark.unit
    def test_basic_extraction(self):
        text = "I'm feeling overwhelmed. Work has been crazy this week."
        keywords = extract_keywords(text)
        assert isinstance(keywords, list)
        assert len(keywords) > 0
        assert all(isinstance(k, str) for k in keywords)

    @pytest.mark.unit
    def test_stop_words_excluded(self):
        text = "I am feeling very overwhelmed because the work is hard."
        keywords = extract_keywords(text)
        stop_words = {"the", "is", "am", "very", "because"}
        for kw in keywords:
            assert kw not in stop_words, f"Stop word '{kw}' not filtered"

    @pytest.mark.unit
    def test_max_keywords_respected(self):
        text = (
            "work sleep manager deadline stress overwhelmed "
            "anxiety pressure burnout exhaustion fatigue"
        )
        keywords = extract_keywords(text, max_keywords=3)
        assert len(keywords) <= 3

    @pytest.mark.unit
    def test_default_max_is_five(self):
        text = (
            "work sleep manager deadline stress overwhelmed "
            "anxiety pressure burnout exhaustion fatigue"
        )
        keywords = extract_keywords(text)
        assert len(keywords) <= 5

    @pytest.mark.unit
    def test_empty_string(self):
        keywords = extract_keywords("")
        assert keywords == []

    @pytest.mark.unit
    def test_short_words_excluded(self):
        """Words <=2 chars should be filtered out."""
        text = "I am an ok so we do it to go"
        keywords = extract_keywords(text)
        for kw in keywords:
            assert len(kw) > 2, f"Short word '{kw}' not filtered"

    @pytest.mark.unit
    def test_frequency_ordering(self):
        """Most frequent keyword should appear first."""
        text = "sleep sleep sleep work work stress"
        keywords = extract_keywords(text)
        assert keywords[0] == "sleep"

    @pytest.mark.unit
    def test_case_insensitive(self):
        text = "Sleep SLEEP sleep Work WORK"
        keywords = extract_keywords(text)
        assert all(kw == kw.lower() for kw in keywords)
