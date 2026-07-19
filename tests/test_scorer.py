"""Tests for skill_curator.scoring — cosine similarity and composite score."""

import pytest

from skill_curator.scoring import composite_score, cosine_similarity


class TestCosineSimilarity:
    def test_identical_vectors(self) -> None:
        vec = [1.0, 2.0, 3.0]
        assert cosine_similarity(vec, vec) == pytest.approx(1.0, abs=1e-6)

    def test_orthogonal_vectors(self) -> None:
        a = [1.0, 0.0, 0.0]
        b = [0.0, 1.0, 0.0]
        assert cosine_similarity(a, b) == pytest.approx(0.0, abs=1e-6)

    def test_zero_vector(self) -> None:
        a = [1.0, 2.0, 3.0]
        zero = [0.0, 0.0, 0.0]
        assert cosine_similarity(a, zero) == pytest.approx(0.0, abs=1e-6)


class TestCompositeScore:
    def test_perfect_score(self) -> None:
        """similarity=1, effectiveness=1, profile_match=True → 1.0."""
        score = composite_score(similarity=1.0, effectiveness=1.0, profile_match=True)
        assert score == pytest.approx(1.0, abs=1e-6)

    def test_minimal_score(self) -> None:
        """similarity=0, effectiveness=0.5, profile_match=False → 0.6*0 + 0.2*0.5 + 0.2*0 = 0.1."""
        score = composite_score(similarity=0.0, effectiveness=0.5, profile_match=False)
        assert score == pytest.approx(0.1, abs=1e-6)
