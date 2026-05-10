"""
Vector similarity search tool — finds candidate books using pgvector ANN
"""
from __future__ import annotations
from sqlalchemy.ext.asyncio import AsyncSession
from db.vector_store import search_similar_books
from db.models import ReadingLevel
from db.session import AsyncSessionLocal
from agent.state import AgentState, BookCandidate


async def vector_search(state: AgentState) -> AgentState:
    """
    Search pgvector for books nearest to the query vector.
    Returns up to 50 candidates for downstream filtering and ranking.
    """
    if not state.query_vector:
        state.errors.append("vector_search: no query vector")
        return state

    reading_level = None
    if state.mode == "child" and state.child_reading_level:
        try:
            reading_level = ReadingLevel(state.child_reading_level)
        except ValueError:
            pass

    async with AsyncSessionLocal() as session:
        results = await search_similar_books(
            session=session,
            query_vector=state.query_vector,
            limit=100,
            reading_level=reading_level,
            age=state.child_age if state.mode == "child" else None,
            exclude_book_ids=state.read_book_ids,
            avoid_scary=state.avoid_scary,
            avoid_violence=state.avoid_violence,
        )

    candidates = []
    for book, score in results:
        candidates.append(BookCandidate(
            book_id=book.id,
            title=book.title,
            author=book.author,
            cover_url=book.cover_url,
            description=book.description,
            page_count=book.page_count,
            genres=book.genres or [],
            themes=book.themes or [],
            goodreads_rating=book.goodreads_rating,
            awards=book.awards or [],
            is_series=book.is_series,
            series_name=book.series_name,
            series_position=book.series_position,
            series_total=book.series_total,
            similarity_score=score,
            # Store safety flags for filter node
            _has_scary=book.has_scary_content,
            _has_violence=book.has_violence,
            # Store affiliate data
            amazon_asin=book.amazon_asin,
            amazon_price=book.amazon_price,
            bookshop_id=book.bookshop_id,
            bookshop_price=book.bookshop_price,
        ))

    state.candidates = candidates
    state.pipeline_steps.append(f"vector_search: found {len(candidates)} candidates")
    return state
