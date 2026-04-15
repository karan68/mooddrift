import pytest
import numpy as np

from services.embedding import generate_embedding
from config import settings


class TestEmbedding:
    """Tests for sentence-transformers embedding service."""

    @pytest.mark.slow
    @pytest.mark.unit
    def test_output_dimension(self):
        vector = generate_embedding("Hello world")
        assert len(vector) == settings.embedding_dim  # 384

    @pytest.mark.slow
    @pytest.mark.unit
    def test_returns_list_of_floats(self):
        vector = generate_embedding("test")
        assert isinstance(vector, list)
        assert all(isinstance(v, float) for v in vector)

    @pytest.mark.slow
    @pytest.mark.unit
    def test_similar_texts_close(self):
        """Semantically similar texts should have high cosine similarity."""
        v1 = np.array(generate_embedding("I feel overwhelmed and stressed"))
        v2 = np.array(generate_embedding("I am anxious and burned out"))
        similarity = np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2))
        assert similarity > 0.5, f"Expected similar texts to be close, got {similarity}"

    @pytest.mark.slow
    @pytest.mark.unit
    def test_different_texts_less_similar(self):
        """Semantically different texts should have lower similarity."""
        v1 = np.array(generate_embedding("I feel overwhelmed and stressed"))
        v2 = np.array(generate_embedding("The recipe calls for two cups of flour"))
        v_same = np.array(generate_embedding("I am anxious and burned out"))

        sim_related = np.dot(v1, v_same) / (np.linalg.norm(v1) * np.linalg.norm(v_same))
        sim_unrelated = np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2))
        assert sim_related > sim_unrelated, (
            f"Related similarity ({sim_related:.3f}) should exceed "
            f"unrelated ({sim_unrelated:.3f})"
        )

    @pytest.mark.slow
    @pytest.mark.unit
    def test_deterministic(self):
        """Same input should produce identical vectors."""
        v1 = generate_embedding("Consistent input text")
        v2 = generate_embedding("Consistent input text")
        assert v1 == v2

    @pytest.mark.slow
    @pytest.mark.unit
    def test_empty_string(self):
        """Should not crash on empty input."""
        vector = generate_embedding("")
        assert len(vector) == settings.embedding_dim
