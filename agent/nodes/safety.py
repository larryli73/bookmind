"""
Safety filter node — applies content filters and enforces author/series diversity
"""
from __future__ import annotations
from agent.state import AgentState, BookCandidate


def passes_kids_safety(book: BookCandidate, state: AgentState) -> bool:
    if state.avoid_scary and getattr(book, '_has_scary', False):
        return False
    if state.avoid_violence and getattr(book, '_has_violence', False):
        return False
    return True


def normalize(text: str) -> str:
    return (text or "").lower().strip()


def get_series_key(book: BookCandidate) -> str:
    """Get a key representing the book's series or franchise"""
    title = normalize(book.title)
    series = normalize(getattr(book, 'series_name', '') or '')
    
    # Extract franchise from title (e.g. "Indiana Jones" from "Indiana Jones Adventures")
    # Take first 2-3 meaningful words as franchise key
    words = [w for w in title.split() if len(w) > 2]
    if len(words) >= 2:
        return " ".join(words[:2])
    return title


def mentions_in_message(book: BookCandidate, user_message: str) -> bool:
    """Check if this book's franchise appears in the user's message"""
    if not user_message:
        return False
    msg = normalize(user_message)
    franchise = get_series_key(book)
    franchise_words = [w for w in franchise.split() if len(w) > 4]
    if not franchise_words:
        return False
    matches = sum(1 for w in franchise_words if w in msg)
    return matches >= 1


async def apply_content_filters(state: AgentState) -> AgentState:
    """
    Filter candidates:
    - Remove already read/disliked books
    - Apply kids safety filters  
    - Enforce max 1 book per author
    - Enforce max 1 book per franchise/series
    - Allow max 1 seed book (from user's message)
    """
    filtered = []
    seen_authors = {}
    seen_franchises = {}
    seed_count = 0

    for book in state.candidates:
        # Skip already-read books
        if book.book_id in state.read_book_ids:
            continue

        # Skip explicitly disliked books
        if book.book_id in state.disliked_book_ids:
            continue

        # Apply kids safety filters
        if state.mode == "child":
            if not passes_kids_safety(book, state):
                continue

        # Check if this book is from a mentioned franchise
        is_seed = mentions_in_message(book, state.user_message or "")
        if is_seed:
            if seed_count >= 1:  # Already kept 1 seed book
                continue
            seed_count += 1

        # Enforce author diversity — max 1 book per author
        author = normalize(book.author)
        if author and author in seen_authors:
            continue

        # Enforce franchise diversity — max 1 book per franchise
        franchise = get_series_key(book)
        if franchise in seen_franchises:
            continue

        seen_authors[author] = 1
        seen_franchises[franchise] = 1
        filtered.append(book)

    state.filtered_candidates = filtered
    state.pipeline_steps.append(
        f"safety_filter: {len(state.candidates)} → {len(filtered)} "
        f"(author+franchise diversity enforced)"
    )
    return state
