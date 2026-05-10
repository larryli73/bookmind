"""
Safety filter — removes seed franchise books, keeps max 1, enforces kids safety
"""
from __future__ import annotations
from agent.state import AgentState, BookCandidate


def normalize(text: str) -> str:
    return (text or "").lower().strip()


def passes_kids_safety(book: BookCandidate, state: AgentState) -> bool:
    if state.avoid_scary and getattr(book, '_has_scary', False):
        return False
    if state.avoid_violence and getattr(book, '_has_violence', False):
        return False
    return True


def get_seed_keywords(user_message: str) -> list[str]:
    """Extract meaningful keywords from user message (what they're comparing to)"""
    stop = {"i", "want", "a", "an", "the", "like", "something", "similar",
            "to", "and", "or", "book", "books", "read", "love", "loved",
            "great", "good", "me", "give", "find", "recommend", "suggest",
            "adventure", "story", "novel", "fiction", "series"}
    msg = normalize(user_message)
    words = [w.strip(".,!?\"'()") for w in msg.split()]
    return [w for w in words if len(w) > 4 and w not in stop]


def book_matches_seeds(book: BookCandidate, seed_keywords: list[str]) -> bool:
    """Return True if the book title contains any seed keyword"""
    title = normalize(book.title)
    return any(kw in title for kw in seed_keywords)


async def apply_content_filters(state: AgentState) -> AgentState:
    seed_keywords = get_seed_keywords(state.user_message or "")
    
    seed_books = []
    other_books = []

    for book in state.candidates:
        if book.book_id in state.read_book_ids:
            continue
        if book.book_id in state.disliked_book_ids:
            continue
        if state.mode == "child" and not passes_kids_safety(book, state):
            continue

        if book_matches_seeds(book, seed_keywords):
            seed_books.append(book)
        else:
            other_books.append(book)

    # Keep max 1 seed book (the most similar one), rest are non-seed
    kept_seeds = seed_books[:1]
    filtered = kept_seeds + other_books

    state.filtered_candidates = filtered
    state.pipeline_steps.append(
        f"safety_filter: {len(state.candidates)} → {len(filtered)} "
        f"(kept {len(kept_seeds)}/{len(seed_books)} seed books)"
    )
    return state
