"""Book search and lookup endpoints"""
from uuid import UUID
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from db.session import get_db
from db.models import Book

router = APIRouter()


@router.get("/search")
async def search_books(
    q: str = Query(..., min_length=2),
    db: AsyncSession = Depends(get_db)
):
    """Search books by title or author"""
    result = await db.execute(
        select(Book).where(
            or_(
                Book.title.ilike(f"%{q}%"),
                Book.author.ilike(f"%{q}%"),
            )
        ).limit(20)
    )
    books = result.scalars().all()
    return [
        {"id": str(b.id), "title": b.title, "author": b.author,
         "cover_url": b.cover_url, "published_year": b.published_year}
        for b in books
    ]


@router.get("/{book_id}")
async def get_book(book_id: UUID, db: AsyncSession = Depends(get_db)):
    book = await db.get(Book, book_id)
    if not book:
        from fastapi import HTTPException
        raise HTTPException(404, "Book not found")
    return {
        "id": str(book.id), "title": book.title, "author": book.author,
        "description": book.description, "cover_url": book.cover_url,
        "genres": book.genres, "themes": book.themes,
        "reading_level": book.reading_level, "age_min": book.age_min,
        "age_max": book.age_max, "page_count": book.page_count,
        "goodreads_rating": book.goodreads_rating, "awards": book.awards,
        "is_series": book.is_series, "series_name": book.series_name,
    }
