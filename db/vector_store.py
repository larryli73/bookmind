"""
pgvector helpers — ANN similarity search with MMR diversity
"""
from __future__ import annotations
import numpy as np
from typing import Optional
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from db.models import Book, ReadingLevel


async def search_similar_books(
    session: AsyncSession,
    query_vector: list[float],
    limit: int = 100,
    reading_level: Optional[ReadingLevel] = None,
    age: Optional[int] = None,
    exclude_book_ids: Optional[list[UUID]] = None,
    avoid_scary: bool = False,
    avoid_violence: bool = False,
) -> list[tuple[Book, float]]:
    """
    Find diverse books using Maximal Marginal Relevance (MMR).
    Balances relevance to query with diversity between results.
    """
    # Step 1: Get a large pool of candidates first (5x what we need)
    fetch_limit = limit * 5

    stmt = (
        select(
            Book,
            Book.embedding.cosine_distance(query_vector).label("distance")
        )
        .where(Book.embedding.is_not(None))
        .order_by("distance")
        .limit(fetch_limit)
    )

    if age is not None:
        stmt = stmt.where(
            (Book.age_min <= age) | (Book.age_min.is_(None))
        ).where(
            (Book.age_max >= age) | (Book.age_max.is_(None))
        )

    if reading_level is not None:
        stmt = stmt.where(Book.reading_level == reading_level)

    if avoid_scary:
        stmt = stmt.where(Book.has_scary_content == False)
    if avoid_violence:
        stmt = stmt.where(Book.has_violence == False)

    if exclude_book_ids:
        stmt = stmt.where(Book.id.not_in(exclude_book_ids))

    result = await session.execute(stmt)
    rows = result.all()

    if not rows:
        return []

    # Step 2: Apply MMR to select diverse results
    books = [row.Book for row in rows]
    distances = [row.distance for row in rows]
    similarities = [1 - d for d in distances]

    # Get embeddings for MMR calculation
    embeddings = [np.array(book.embedding) for book in books]
    query_vec = np.array(query_vector)

    # MMR algorithm
    lambda_param = 0.7  # Balance relevance (1.0) vs diversity (0.0)
    selected_indices = []
    remaining_indices = list(range(len(books)))

    while len(selected_indices) < limit and remaining_indices:
        if not selected_indices:
            # First pick: most similar to query
            best_idx = max(remaining_indices, key=lambda i: similarities[i])
        else:
            # Subsequent picks: balance similarity to query vs dissimilarity to selected
            best_score = -float('inf')
            best_idx = remaining_indices[0]

            selected_embeddings = [embeddings[i] for i in selected_indices]

            for i in remaining_indices:
                # Similarity to query
                rel_score = similarities[i]

                # Max similarity to already selected books
                max_sim_to_selected = max(
                    float(np.dot(embeddings[i], sel_emb) /
                          (np.linalg.norm(embeddings[i]) * np.linalg.norm(sel_emb) + 1e-8))
                    for sel_emb in selected_embeddings
                )

                # MMR score
                mmr_score = lambda_param * rel_score - (1 - lambda_param) * max_sim_to_selected

                if mmr_score > best_score:
                    best_score = mmr_score
                    best_idx = i

        selected_indices.append(best_idx)
        remaining_indices.remove(best_idx)

    return [(books[i], similarities[i]) for i in selected_indices]


async def compute_taste_vector(
    session: AsyncSession,
    book_ids: list[UUID],
    weights: Optional[list[float]] = None,
) -> Optional[list[float]]:
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
    new_emb = np.array(new_book_embedding)

    if current_vector is None:
        return (new_emb * np.sign(signal_weight)).tolist()

    current = np.array(current_vector)

    if signal_weight > 0:
        updated = current + learning_rate * signal_weight * (new_emb - current)
    else:
        updated = current - learning_rate * abs(signal_weight) * new_emb

    norm = np.linalg.norm(updated)
    if norm > 0:
        updated = updated / norm

    return updated.tolist()


SIGNAL_WEIGHTS = {
    "loved":      1.0,
    "liked":      0.7,
    "finished":   0.5,
    "wishlisted": 0.3,
    "shared":     0.8,
    "purchased":  0.9,
    "neutral":    0.0,
    "disliked":  -0.5,
    "abandoned": -0.3,
}
