"""Tests for multilingual model support (v1.0.0 RED).

The encoder must use paraphrase-multilingual-MiniLM-L12-v2 (384 dims)
to enable cross-language semantic matching.
"""

import pytest

from skill_curator.server import _get_encoder


@pytest.mark.slow
class TestMultilingualEncoder:
    def test_encoder_model_name(self) -> None:
        encoder = _get_encoder()
        # Model card name must be the multilingual variant
        model_name = (
            encoder.get_model_card()["name"]
            if hasattr(encoder, "get_model_card")
            else str(encoder)
        )
        assert "paraphrase-multilingual-MiniLM-L12-v2" in model_name

    def test_embedding_dimension_384(self) -> None:
        encoder = _get_encoder()
        vec = encoder.encode("hello world")
        assert len(vec) == 384

    def test_cross_language_match(self) -> None:
        encoder = _get_encoder()
        import numpy as np

        query_vec = encoder.encode("implantar aplicação no kubernetes")
        skill_vec = encoder.encode("deploy application to kubernetes")

        # Cosine similarity
        sim = float(
            np.dot(query_vec, skill_vec)
            / (np.linalg.norm(query_vec) * np.linalg.norm(skill_vec))
        )
        assert sim > 0.4, f"Cross-language similarity too low: {sim}"

    def test_same_language_higher_score(self) -> None:
        encoder = _get_encoder()
        import numpy as np

        skill_vec = encoder.encode("deploy application to kubernetes")
        query_en = encoder.encode("deploy application to kubernetes")
        query_pt = encoder.encode("implantar aplicação no kubernetes")

        sim_en = float(
            np.dot(query_en, skill_vec)
            / (np.linalg.norm(query_en) * np.linalg.norm(skill_vec))
        )
        sim_pt = float(
            np.dot(query_pt, skill_vec)
            / (np.linalg.norm(query_pt) * np.linalg.norm(skill_vec))
        )

        assert sim_en > sim_pt, f"EN score ({sim_en}) should be > PT score ({sim_pt})"

    def test_env_var_override_model(self, monkeypatch) -> None:
        """SKILL_CURATOR_MODEL env var should override the default model."""
        import skill_curator.server as srv

        # Reset singleton
        srv._encoder_instance = None
        monkeypatch.setenv("SKILL_CURATOR_MODEL", "all-MiniLM-L6-v2")
        try:
            encoder = srv._get_encoder()
            model_name = str(encoder)
            assert "all-MiniLM-L6-v2" in model_name
        finally:
            srv._encoder_instance = None
