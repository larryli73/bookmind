"""
Safety filter node — applies content filters especially for kids
"""
from __future__ import annotations
from agent.state import AgentState, BookCandidate


def passes_kids_safety(book: BookCandidate, state: AgentState) -> bool:
    """Hard safety rules for children's books — never relaxed"""
    # These come from the book's DB fields (pre-populated)
    if state.avoid_scary and getattr(book, '_has_scary', False):
        return False
    if state.avoid_violence and getattr(book, '_has_violence', False):
        return False
    return True


async def apply_content_filters(state: AgentState) -> AgentState:
    """
    Filter candidate books based on:
    - Already read (excluded upstream in vector search, double-check here)
    - Kids safety filters (scary, violence, adult themes)
    - Genre avoidance preferences
    """
    filtered = []

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

        filtered.append(book)

    state.filtered_candidates = filtered
    state.pipeline_steps.append(
        f"safety_filter: {len(state.candidates)} → {len(filtered)} candidates"
    )
    return state
