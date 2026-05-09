"""Feedback endpoints — captures reading signals to improve recommendations"""
from uuid import UUID
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from db.session import get_db
from db.models import FeedbackSignal
from agent.nodes.feedback import process_adult_feedback, process_child_feedback

router = APIRouter()


class AdultFeedbackRequest(BaseModel):
    reader_id: UUID
    book_id: UUID
    signal: FeedbackSignal
    rating: Optional[int] = None          # 1-5
    percent_read: Optional[int] = None    # 0-100


class ChildFeedbackRequest(BaseModel):
    child_id: UUID
    book_id: UUID
    signal: FeedbackSignal
    child_rating: Optional[int] = None    # 1-3
    mom_notes: Optional[str] = None


@router.post("/adult")
async def submit_adult_feedback(req: AdultFeedbackRequest, db: AsyncSession = Depends(get_db)):
    """Submit feedback for an adult reader — updates their taste vector"""
    await process_adult_feedback(
        session=db,
        reader_id=req.reader_id,
        book_id=req.book_id,
        signal=req.signal,
        rating=req.rating,
    )
    return {"status": "feedback recorded", "taste_vector_updated": True}


@router.post("/child")
async def submit_child_feedback(req: ChildFeedbackRequest, db: AsyncSession = Depends(get_db)):
    """Submit feedback for a child's book — updates their taste vector"""
    await process_child_feedback(
        session=db,
        child_id=req.child_id,
        book_id=req.book_id,
        signal=req.signal,
        child_rating=req.child_rating,
        mom_notes=req.mom_notes,
    )
    return {"status": "feedback recorded", "taste_vector_updated": True}
