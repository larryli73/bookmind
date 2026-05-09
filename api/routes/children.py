"""Child profile management — Mom adds and manages her children"""
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from db.session import get_db
from db.models import Child, ReadingLevel, SeriesProgress

router = APIRouter()


class CreateChildRequest(BaseModel):
    parent_id: UUID
    name: str
    age: int
    grade: Optional[int] = None
    reading_level: ReadingLevel
    reads_independently: bool = True
    interests: Optional[list[str]] = None
    avoid_scary: bool = False
    avoid_violence: bool = False
    avoid_sad_endings: bool = False
    mom_goals: Optional[list[str]] = None
    avatar_emoji: Optional[str] = None


class UpdateSeriesProgressRequest(BaseModel):
    series_name: str
    books_read: int
    total_books: Optional[int] = None
    next_book_isbn: Optional[str] = None


@router.post("/")
async def create_child(req: CreateChildRequest, db: AsyncSession = Depends(get_db)):
    """Mom adds a child profile"""
    child = Child(**req.model_dump())
    db.add(child)
    await db.commit()
    await db.refresh(child)
    return {"child_id": str(child.id), "name": child.name}


@router.get("/{child_id}")
async def get_child(child_id: UUID, db: AsyncSession = Depends(get_db)):
    child = await db.get(Child, child_id)
    if not child:
        raise HTTPException(404, "Child not found")
    return {
        "id": str(child.id),
        "name": child.name,
        "age": child.age,
        "reading_level": child.reading_level,
        "interests": child.interests,
        "avatar_emoji": child.avatar_emoji,
    }


@router.get("/{child_id}/series")
async def get_series_progress(child_id: UUID, db: AsyncSession = Depends(get_db)):
    """Get all in-progress series for a child — Mom's favorite dashboard feature"""
    result = await db.execute(
        select(SeriesProgress).where(SeriesProgress.child_id == child_id)
    )
    series_list = result.scalars().all()
    return [
        {
            "series_name":    sp.series_name,
            "books_read":     sp.books_read,
            "total_books":    sp.total_books,
            "next_book_isbn": sp.next_book_isbn,
            "progress_pct":   round(sp.books_read / sp.total_books * 100) if sp.total_books else None,
        }
        for sp in series_list
    ]


@router.post("/{child_id}/series")
async def update_series_progress(
    child_id: UUID,
    req: UpdateSeriesProgressRequest,
    db: AsyncSession = Depends(get_db)
):
    """Update a child's progress in a series"""
    result = await db.execute(
        select(SeriesProgress).where(
            SeriesProgress.child_id == child_id,
            SeriesProgress.series_name == req.series_name
        )
    )
    sp = result.scalar_one_or_none()

    if sp:
        sp.books_read     = req.books_read
        sp.total_books    = req.total_books or sp.total_books
        sp.next_book_isbn = req.next_book_isbn or sp.next_book_isbn
    else:
        sp = SeriesProgress(child_id=child_id, **req.model_dump())
        db.add(sp)

    await db.commit()
    return {"status": "updated", "series": req.series_name}
