import pytest
import numpy as np

from services.drift_engine import (
    compute_centroid,
    cosine_similarity,
    _severity_label,
    _cluster_dates,
)


class TestComputeCentroid:
    @pytest.mark.unit
    def test_single_vector(self):
        vectors = [[1.0, 2.0, 3.0]]
        centroid = compute_centroid(vectors)
        np.testing.assert_array_almost_equal(centroid, [1.0, 2.0, 3.0])

    @pytest.mark.unit
    def test_two_vectors(self):
        vectors = [[1.0, 0.0], [0.0, 1.0]]
        centroid = compute_centroid(vectors)
        np.testing.assert_array_almost_equal(centroid, [0.5, 0.5])

    @pytest.mark.unit
    def test_identical_vectors(self):
        vectors = [[1.0, 2.0, 3.0]] * 5
        centroid = compute_centroid(vectors)
        np.testing.assert_array_almost_equal(centroid, [1.0, 2.0, 3.0])

    @pytest.mark.unit
    def test_many_vectors(self):
        np.random.seed(42)
        vectors = np.random.randn(100, 384).tolist()
        centroid = compute_centroid(vectors)
        assert len(centroid) == 384


class TestCosineSimilarity:
    @pytest.mark.unit
    def test_identical_vectors(self):
        a = np.array([1.0, 2.0, 3.0])
        assert cosine_similarity(a, a) == pytest.approx(1.0)

    @pytest.mark.unit
    def test_opposite_vectors(self):
        a = np.array([1.0, 0.0])
        b = np.array([-1.0, 0.0])
        assert cosine_similarity(a, b) == pytest.approx(-1.0)

    @pytest.mark.unit
    def test_orthogonal_vectors(self):
        a = np.array([1.0, 0.0])
        b = np.array([0.0, 1.0])
        assert cosine_similarity(a, b) == pytest.approx(0.0)

    @pytest.mark.unit
    def test_zero_vector(self):
        a = np.array([0.0, 0.0])
        b = np.array([1.0, 2.0])
        assert cosine_similarity(a, b) == 0.0

    @pytest.mark.unit
    def test_range(self):
        np.random.seed(42)
        a = np.random.randn(384)
        b = np.random.randn(384)
        sim = cosine_similarity(a, b)
        assert -1.0 <= sim <= 1.0


class TestSeverityLabel:
    @pytest.mark.unit
    def test_none(self):
        assert _severity_label(0.0) == "none"
        assert _severity_label(0.24) == "none"

    @pytest.mark.unit
    def test_mild(self):
        assert _severity_label(0.25) == "mild"
        assert _severity_label(0.39) == "mild"

    @pytest.mark.unit
    def test_moderate(self):
        assert _severity_label(0.40) == "moderate"
        assert _severity_label(0.59) == "moderate"

    @pytest.mark.unit
    def test_significant(self):
        assert _severity_label(0.60) == "significant"
        assert _severity_label(1.0) == "significant"


class TestClusterDates:
    @pytest.mark.unit
    def test_single_date(self):
        result = _cluster_dates(["2026-02-12"])
        assert result == "2026-02-12"

    @pytest.mark.unit
    def test_same_month(self):
        result = _cluster_dates(["2026-02-10", "2026-02-15", "2026-02-12"])
        assert result == "Feb 10-15"

    @pytest.mark.unit
    def test_cross_month(self):
        result = _cluster_dates(["2026-02-28", "2026-03-05"])
        assert result == "Feb 28 - Mar 05"

    @pytest.mark.unit
    def test_empty(self):
        result = _cluster_dates([])
        assert result == "unknown period"
