"""
Collaborative filter — re-ranks candidates and enforces diversity
"""
from __future__ import annotations
from agent.state import AgentState


def is_quality_book(book) -> bool:
    if isinstance(book, dict):
        cover = book.get("cover_url")
        genres = book.get("genres") or []
        title = book.get("title", "")
        page_count = book.get("page_count") or 0
    else:
        cover = book.cover_url
        genres = book.genres or []
        title = book.title
        page_count = book.page_count or 0

    if not cover:
        return False
    if not genres:
        return False
    if page_count and page_count < 50:
        return False
    return True


def quality_score(book) -> float:
    if isinstance(book, dict):
        rating = book.get("goodreads_rating")
        genres = book.get("genres") or []
        page_count = book.get("page_count") or 0
        awards = book.get("awards") or []
    else:
        rating = book.goodreads_rating
        genres = book.genres or []
        page_count = book.page_count or 0
        awards = book.awards or []

    score = 0.0
    if rating:
        score += (rating - 3.5) * 0.1
    if len(genres) >= 3:
        score += 0.1
    if page_count > 200:
        score += 0.05
    if awards:
        score += 0.15
    return score


async def collaborative_rerank(state: AgentState) -> AgentState:
    candidates = state.filtered_candidates or state.candidates

    # Score all candidates
    scored = []
    for book in candidates:
        if not is_quality_book(book):
            continue
        base = book.get("similarity_score", 0) if isinstance(book, dict) else book.similarity_score
        q = quality_score(book)
        final = base + q
        if isinstance(book, dict):
            book["final_score"] = final
        else:
            book.final_score = final
        scored.append((final, book))

    scored.sort(key=lambda x: x[0], reverse=True)

    # ENFORCE DIVERSITY — max 1 book per author
    seen_authors = {}
    diverse = []
    for score, book in scored:
        author = (book.get("author", "") if isinstance(book, dict) else book.author or "").lower().strip()
        # Allow max 1 book per author
        if author not in seen_authors:
            seen_authors[author] = 1
            diverse.append(book)
        # Allow at most 1 more from very prolific authors if we need more candidates
        elif seen_authors[author] < 1:
            seen_authors[author] += 1
            diverse.append(book)

    state.filtered_candidates = diverse
    state.pipeline_steps.append(
        f"collab_rerank: {len(candidates)} → {len(diverse)} (1 book per author enforced)"
    )
    return state
