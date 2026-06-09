"""Scoring: cosine similarity + EMA + profile boost."""

import math


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors.

    Args:
        a: First vector.
        b: Second vector.

    Returns:
        Cosine similarity in [0.0, 1.0].
    """
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return max(0.0, dot / (norm_a * norm_b))


def composite_score(
    similarity: float,
    effectiveness: float,
    profile_match: bool = False,
) -> float:
    """Compute composite score for skill ranking.

    Args:
        similarity: Cosine similarity (0.0-1.0).
        effectiveness: EMA effectiveness score (0.0-1.0).
        profile_match: Whether skill matches current profile.

    Returns:
        Weighted composite score.
    """
    pm = 1.0 if profile_match else 0.0
    return 0.6 * similarity + 0.2 * effectiveness + 0.2 * pm
