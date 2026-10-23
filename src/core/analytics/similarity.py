"""Embedding computations; encoders and model lifecycle are supplied by callers."""
from collections.abc import Callable
from typing import Any

import numpy as np


def encode_texts(texts: list[str], *, encoder: Callable[..., Any] | None) -> np.ndarray:
    """Request normalized embeddings without owning a model or its resources."""
    if not texts:
        return np.zeros((0, 1))
    vectors = encoder(texts, convert_to_numpy=True, normalize_embeddings=True,
                      show_progress_bar=False, batch_size=32)
    if not isinstance(vectors, np.ndarray):
        vectors = np.asarray(vectors, dtype=float)
    return vectors


def cosine_matrix(left_vectors: np.ndarray, right_vectors: np.ndarray) -> np.ndarray:
    """Compare already normalized row vectors without changing precision or scale."""
    if left_vectors.size == 0 or right_vectors.size == 0:
        return np.zeros((left_vectors.shape[0], right_vectors.shape[0]))
    return np.matmul(left_vectors, right_vectors.T)


def top_matches(row: np.ndarray, top_k: int) -> list[tuple[int, float]]:
    """Return descending indexes and display scores clipped to the unit interval."""
    indexes = np.argsort(row)[::-1][:top_k]
    return [(int(index), float(max(0.0, min(1.0, row[int(index)])))) for index in indexes]
