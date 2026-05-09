"""
pgvector helpers — ANN similarity search for books and taste vectors
"""
from __future__ import annotations
import numpy as np
from typing import Optional
from uuid import UUID
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from db.models import Book, ReadingLevel


async def search_similar_books(
    session: AsyncSession,
    query_vector: list[float],
    limit: int = 50,
    reading_level: Optional[ReadingLevel] = None,
    age: Optional[int] = None,
    exclude_book_ids: Optional[list[UUID]] = None,
    avoid_scary: bool = False,
    avoid_violence: bool = False,
) -> list[tuple[Book, float]]:
    """
    Find books nearest to query_vector using cosine similarity (pgvector ANN).
    Returns list of (Book, similarity_score) tuples sorted by similarity desc.
    """
    stmt = (
        select(
            Book,
            Book.embedding.cosine_distance(query_vector).label("distance")
        )
        .where(Book.embedding.is_not(None))
        .order_by("distance")
        .limit(limit)
    )

    # Age filter for kids
    if age is not None:
        stmt = stmt.where(
            (Book.age_min <= age) | (Book.age_min.is_(None))
        ).where(
            (Book.age_max >= age) | (Book.age_max.is_(None))
        )

    # Reading level filter
    if reading_level is not None:
        stmt = stmt.where(Book.reading_level == reading_level)

    # Content safety filters for kids
    if avoid_scary:
        stmt = stmt.where(Book.has_scary_content == False)
    if avoid_violence:
        stmt = stmt.where(Book.has_violence == False)

    # Exclude already-read books
    if exclude_book_ids:
        stmt = stmt.where(Book.id.not_in(exclude_book_ids))

    result = await session.execute(stmt)
    rows = result.all()

    # Convert distance to similarity score (cosine distance: 0=identical, 2=opposite)
    return [(row.Book, 1 - row.distance) for row in rows]


async def compute_taste_vector(
    session: AsyncSession,
    book_ids: list[UUID],
    weights: Optional[list[float]] = None,
) -> Optional[list[float]]:
    """
    Compute a reader's taste vector as weighted average of liked book embeddings.
    weights: positive = liked, negative = disliked (down-weights those dimensions)
    """
    if not book_ids:
        return None

    stmt = select(Book.embedding).where(
        Book.id.in_(book_ids),
        Book.embedding.is_not(None)
    )
    result = await session.execute(stmt)
    embeddings = [row[0] for row in result.all()]

    if not embeddings:
        return None

    embeddings_np = np.array(embeddings)

    if weights and len(weights) == len(embeddings):
        weights_np = np.array(weights).reshape(-1, 1)
        taste = np.average(embeddings_np, axis=0, weights=np.abs(weights_np).flatten())
    else:
        taste = np.mean(embeddings_np, axis=0)

    # Normalize to unit vector
    norm = np.linalg.norm(taste)
    if norm > 0:
        taste = taste / norm

    return taste.tolist()


async def update_taste_vector(
    session: AsyncSession,
    current_vector: Optional[list[float]],
    new_book_embedding: list[float],
    signal_weight: float,
    learning_rate: float = 0.1,
) -> list[float]:
    """
    Update taste vector incrementally using exponential moving average.
    signal_weight: +1.0 = loved, -0.5 = disliked, +0.3 = wishlisted, etc.
    """
    new_emb = np.array(new_book_embedding)

    if current_vector is None:
        return (new_emb * np.sign(signal_weight)).tolist()

    current = np.array(current_vector)

    if signal_weight > 0:
        # Move taste vector toward this book
        updated = current + learning_rate * signal_weight * (new_emb - current)
    else:
        # Move taste vector away from this book
        updated = current - learning_rate * abs(signal_weight) * new_emb

    # Normalize
    norm = np.linalg.norm(updated)
    if norm > 0:
        updated = updated / norm

    return updated.tolist()


# Signal weights for feedback types
SIGNAL_WEIGHTS = {
    "loved":      1.0,
    "liked":      0.7,
    "finished":   0.5,   # implicit positive
    "wishlisted": 0.3,
    "shared":     0.8,
    "purchased":  0.9,
    "neutral":    0.0,
    "disliked":  -0.5,
    "abandoned": -0.3,
}
