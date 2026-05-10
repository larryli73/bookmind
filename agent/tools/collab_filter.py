"""
Collaborative filter — re-ranks candidates, filters low quality books
"""
from __future__ import annotations
from agent.state import AgentState


def quality_score(book) -> float:
    """Score book quality — filter out obscure self-published books"""
    if isinstance(book, dict):
        cover = book.get("cover_url")
        rating = book.get("goodreads_rating")
        genres = book.get("genres") or []
        title = book.get("title", "")
        page_count = book.get("page_count") or 0
    else:
        cover = book.cover_url
        rating = book.goodreads_rating
        genres = book.genres or []
        title = book.title
        page_count = book.page_count or 0

    score = 0.0

    # Must have a cover image — no cover = likely obscure/low quality
    if not cover:
        score -= 0.5

    # Must have genres
    if not genres:
        score -= 0.3

    # Prefer books with ratings
    if rating:
        score += (rating - 3.5) * 0.1

    # Prefer reasonable page counts (not too short)
    if page_count > 100:
        score += 0.1

    # Penalize titles that look like self-published (colons, very long titles)
    if title.count(':') > 1:
        score -= 0.2
    if len(title) > 80:
        score -= 0.2

    return score


async def collaborative_rerank(state: AgentState) -> AgentState:
    candidates = state.filtered_candidates or state.candidates

    scored = []
    for book in candidates:
        base = book.get("similarity_score", 0) if isinstance(book, dict) else book.similarity_score
        q = quality_score(book)
        final = base + q

        if isinstance(book, dict):
            book["collab_score"] = q
            book["final_score"] = final
        else:
            book.collab_score = q
            book.final_score = final

        # Only include books with a cover image
        cover = book.get("cover_url") if isinstance(book, dict) else book.cover_url
        if cover:
            scored.append((final, book))

    # Sort by final score
    scored.sort(key=lambda x: x[0], reverse=True)
    state.filtered_candidates = [b for _, b in scored]

    state.pipeline_steps.append(
        f"collab_rerank: {len(candidates)} → {len(state.filtered_candidates)} (filtered no-cover books)"
    )
    return state
