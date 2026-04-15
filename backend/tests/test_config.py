import pytest

from config import Settings


class TestConfig:
    """Unit tests for configuration loading."""

    @pytest.mark.unit
    def test_settings_loads(self):
        from config import settings
        assert settings.collection_name == "mood_entries"
        assert settings.embedding_dim == 384
        assert settings.drift_threshold == 0.25
        assert settings.recent_window_days == 7
        assert settings.baseline_window_days == 30

    @pytest.mark.unit
    def test_default_user_id(self):
        from config import settings
        assert settings.default_user_id == "demo_user"
