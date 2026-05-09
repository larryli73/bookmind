"""
Collaborative filter tool — re-ranks candidates based on what similar readers loved
"""
from __future__ import annotations
from agent.state import AgentState


async def collaborative_rerank(state: AgentState) -> AgentState:
    """
    Re-rank filtered candidates using collaborative filtering signals.
    
    In Phase 1 (MVP): boost books with high Goodreads ratings + award winners.
    In Phase 2: implement full SVD/matrix factorization with user-item matrix.
    """
    candidates = state.filtered_candidates or state.candidates

    def collab_score(book) -> float:
        score = book.similarity_score

        # Boost for high Goodreads rating
        if book.goodreads_rating:
            score += (book.goodreads_rating - 3.5) * 0.05

        # Boost for award winners (parents and readers trust awards)
        if book.awards:
            score += 0.05 * min(len(book.awards), 3)

        # Slight boost for series Book 1 (high chance of repeat purchase)
        if book.is_series and book.series_position == 1:
            score += 0.03

        return score

    for book in candidates:
        book.collab_score = collab_score(book)
        book.final_score = book.collab_score

    # Re-sort by final score
    state.filtered_candidates = sorted(candidates, key=lambda b: b.final_score, reverse=True)
    state.pipeline_steps.append("collab_rerank: complete")
    return state
