"""Scoring functions — cosine similarity and composite ranking."""
from __future__ import annotations

import math


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors.

    Args:
        a: First vector.
        b: Second vector.

    Returns:
        Cosine similarity in range [-1, 1], or 0.0 if either is zero-length.
    """
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def composite_score(similarity: float, effectiveness: float, profile_match: bool) -> float:
    """Compute weighted composite score.

    Formula: 0.6 * similarity + 0.2 * effectiveness + 0.2 * profile_match

    Args:
        similarity: Cosine similarity (0-1).
        effectiveness: Skill effectiveness (0-1).
        profile_match: Whether skill matches profile (True=1.0, False=0.0).

    Returns:
        Weighted score.
    """
    pm = 1.0 if profile_match else 0.0
    return 0.6 * similarity + 0.2 * effectiveness + 0.2 * pm
