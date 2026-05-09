"""
Feedback processor node — updates taste vectors based on reader signals
"""
from __future__ import annotations
from sqlalchemy.ext.asyncio import AsyncSession
from db.vector_store import update_taste_vector, SIGNAL_WEIGHTS
from db.models import Reader, Child, Book, ReaderFeedback, ChildFeedback, FeedbackSignal
from sqlalchemy import select
import uuid


async def process_adult_feedback(
    session: AsyncSession,
    reader_id: uuid.UUID,
    book_id: uuid.UUID,
    signal: FeedbackSignal,
    rating: int | None = None,
) -> None:
    """
    Handle adult reader feedback:
    1. Save feedback to DB
    2. Update reader's taste vector
    """
    # Get reader and book
    reader = await session.get(Reader, reader_id)
    book = await session.get(Book, book_id)

    if not reader or not book or not book.embedding:
        return

    # Determine signal weight
    weight = SIGNAL_WEIGHTS.get(signal.value, 0.0)
    if rating:
        # Override with explicit rating weight
        weight = (rating - 3) / 2.0   # Maps 1-5 to -1.0 to +1.0

    # Update taste vector
    reader.taste_vector = await update_taste_vector(
        session=session,
        current_vector=reader.taste_vector,
        new_book_embedding=book.embedding,
        signal_weight=weight,
    )

    # Save feedback record
    feedback = ReaderFeedback(
        reader_id=reader_id,
        book_id=book_id,
        signal=signal,
        rating=rating,
    )
    session.add(feedback)
    await session.commit()


async def process_child_feedback(
    session: AsyncSession,
    child_id: uuid.UUID,
    book_id: uuid.UUID,
    signal: FeedbackSignal,
    child_rating: int | None = None,
    mom_notes: str | None = None,
) -> None:
    """Handle feedback for a child's reading — updates child's taste vector"""
    child = await session.get(Child, child_id)
    book = await session.get(Book, book_id)

    if not child or not book or not book.embedding:
        return

    weight = SIGNAL_WEIGHTS.get(signal.value, 0.0)
    if child_rating:
        # Kids rating is 1-3, map to weight
        weight = (child_rating - 2) / 1.0  # Maps 1-3 to -1.0 to +1.0

    child.taste_vector = await update_taste_vector(
        session=session,
        current_vector=child.taste_vector,
        new_book_embedding=book.embedding,
        signal_weight=weight,
    )

    feedback = ChildFeedback(
        child_id=child_id,
        book_id=book_id,
        signal=signal,
        child_rating=child_rating,
        mom_notes=mom_notes,
    )
    session.add(feedback)
    await session.commit()
