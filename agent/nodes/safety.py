"""
Safety filter node — applies content filters and enforces author diversity
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


def mentions_in_message(book: BookCandidate, user_message: str) -> bool:
    """Check if this book's title words appear in the user's message"""
    if not user_message:
        return False
    msg = normalize(user_message)
    title = normalize(book.title)
    # Get meaningful words from title (length > 4)
    title_words = [w for w in title.split() if len(w) > 4]
    if not title_words:
        return False
    # If more than half the title words appear in the message, it's a seed
    matches = sum(1 for w in title_words if w in msg)
    return matches >= max(1, len(title_words) * 0.5)


async def apply_content_filters(state: AgentState) -> AgentState:
    """
    Filter candidates:
    - Remove already read/disliked books
    - Apply kids safety filters
    - Enforce max 1 book per author (diversity)
    """
    filtered = []
    seen_authors = {}
    seed_removed = 0

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

        # Check if this book was mentioned in user message (seed book)
        # Allow max 1 seed book in results
        is_seed = mentions_in_message(book, state.user_message or "")
        if is_seed:
            if seed_removed >= 1:  # Already kept 1 seed book
                seed_removed += 1
                continue
            seed_removed += 1

        # Enforce author diversity — max 1 book per author
        author = normalize(book.author)
        if author in seen_authors:
            continue
        seen_authors[author] = 1

        filtered.append(book)

    state.filtered_candidates = filtered
    state.pipeline_steps.append(
        f"safety_filter: {len(state.candidates)} → {len(filtered)} candidates "
        f"(1 per author enforced)"
    )
    return state
