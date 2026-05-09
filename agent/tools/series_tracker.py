"""
Series tracker tool — injects next-in-series books for children
"""
from __future__ import annotations
from agent.state import AgentState, BookCandidate
from db.session import AsyncSessionLocal
from db.models import SeriesProgress, Book, Child
from sqlalchemy import select


async def inject_series_next(state: AgentState) -> AgentState:
    """
    For child mode: find any in-progress series and inject the next book
    at the top of recommendations. Mom loves this feature.
    """
    if not state.child_id or state.mode != "child":
        return state

    async with AsyncSessionLocal() as session:
        # Get all in-progress series for this child
        result = await session.execute(
            select(SeriesProgress).where(SeriesProgress.child_id == state.child_id)
        )
        series_list = result.scalars().all()

        series_books = []
        for sp in series_list:
            if sp.next_book_isbn:
                # Find the next book in DB
                book_result = await session.execute(
                    select(Book).where(Book.isbn_13 == sp.next_book_isbn)
                )
                book = book_result.scalar_one_or_none()
                if book and book.embedding:
                    series_books.append(BookCandidate(
                        book_id=book.id,
                        title=book.title,
                        author=book.author,
                        cover_url=book.cover_url,
                        genres=book.genres or [],
                        themes=book.themes or [],
                        goodreads_rating=book.goodreads_rating,
                        awards=book.awards or [],
                        is_series=True,
                        series_name=sp.series_name,
                        series_position=sp.books_read + 1,
                        series_total=sp.total_books,
                        similarity_score=1.0,  # Always top priority
                        reason=f"📚 Next in {sp.series_name}! "
                               f"{state.child_name} is on book {sp.books_read} of {sp.total_books or '?'}.",
                    ))

    state.series_next_books = series_books
    state.pipeline_steps.append(f"series_inject: found {len(series_books)} next-in-series books")
    return state
