"""
Analytics routes — track searches, clicks, and buy link events
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from db.session import get_db
from datetime import datetime

router = APIRouter()


class SearchLogRequest(BaseModel):
    reader_id: str
    query: str
    results_count: int
    session_id: Optional[str] = None


class ClickLogRequest(BaseModel):
    reader_id: str
    session_id: Optional[str] = None
    book_id: str
    book_title: str
    book_author: str
    click_type: str  # "amazon", "bookshop", "liked", "disliked", "wishlisted"
    position: Optional[int] = None  # Which position in results (1-8)
    query: Optional[str] = None


@router.post("/search")
async def log_search(req: SearchLogRequest, db: AsyncSession = Depends(get_db)):
    """Log a search query"""
    try:
        await db.execute(text("""
            INSERT INTO search_logs (reader_id, query, results_count, session_id, created_at)
            VALUES (:reader_id, :query, :results_count, :session_id, :created_at)
        """), {
            "reader_id": req.reader_id,
            "query": req.query,
            "results_count": req.results_count,
            "session_id": req.session_id,
            "created_at": datetime.utcnow()
        })
        await db.commit()
    except Exception:
        pass  # Never fail on analytics
    return {"status": "ok"}


@router.post("/click")
async def log_click(req: ClickLogRequest, db: AsyncSession = Depends(get_db)):
    """Log a book click or buy link click"""
    try:
        await db.execute(text("""
            INSERT INTO click_logs (reader_id, session_id, book_id, book_title, book_author, 
                                   click_type, position, query, created_at)
            VALUES (:reader_id, :session_id, :book_id, :book_title, :book_author,
                    :click_type, :position, :query, :created_at)
        """), {
            "reader_id": req.reader_id,
            "session_id": req.session_id,
            "book_id": req.book_id,
            "book_title": req.book_title,
            "book_author": req.book_author,
            "click_type": req.click_type,
            "position": req.position,
            "query": req.query,
            "created_at": datetime.utcnow()
        })
        await db.commit()
    except Exception:
        pass
    return {"status": "ok"}


@router.get("/summary")
async def get_summary(db: AsyncSession = Depends(get_db)):
    """Get analytics summary — top queries, popular books, click rates"""
    try:
        # Top queries
        top_queries = await db.execute(text("""
            SELECT query, COUNT(*) as count, AVG(results_count) as avg_results
            FROM search_logs
            WHERE created_at > NOW() - INTERVAL '7 days'
            GROUP BY query
            ORDER BY count DESC
            LIMIT 20
        """))

        # Zero result queries
        zero_results = await db.execute(text("""
            SELECT query, COUNT(*) as count
            FROM search_logs
            WHERE results_count = 0
            AND created_at > NOW() - INTERVAL '7 days'
            GROUP BY query
            ORDER BY count DESC
            LIMIT 10
        """))

        # Most clicked books
        top_books = await db.execute(text("""
            SELECT book_title, book_author, click_type, COUNT(*) as clicks
            FROM click_logs
            WHERE created_at > NOW() - INTERVAL '7 days'
            GROUP BY book_title, book_author, click_type
            ORDER BY clicks DESC
            LIMIT 20
        """))

        # Amazon vs Bookshop clicks
        buy_clicks = await db.execute(text("""
            SELECT click_type, COUNT(*) as count
            FROM click_logs
            WHERE click_type IN ('amazon', 'bookshop')
            AND created_at > NOW() - INTERVAL '7 days'
            GROUP BY click_type
        """))

        # Total stats
        totals = await db.execute(text("""
            SELECT 
                (SELECT COUNT(*) FROM search_logs WHERE created_at > NOW() - INTERVAL '7 days') as searches,
                (SELECT COUNT(DISTINCT reader_id) FROM search_logs WHERE created_at > NOW() - INTERVAL '7 days') as unique_users,
                (SELECT COUNT(*) FROM click_logs WHERE click_type = 'amazon' AND created_at > NOW() - INTERVAL '7 days') as amazon_clicks,
                (SELECT COUNT(*) FROM click_logs WHERE click_type = 'bookshop' AND created_at > NOW() - INTERVAL '7 days') as bookshop_clicks,
                (SELECT COUNT(*) FROM click_logs WHERE click_type = 'liked' AND created_at > NOW() - INTERVAL '7 days') as likes
        """))

        total_row = totals.fetchone()

        return {
            "period": "last 7 days",
            "totals": {
                "searches": total_row.searches,
                "unique_users": total_row.unique_users,
                "amazon_clicks": total_row.amazon_clicks,
                "bookshop_clicks": total_row.bookshop_clicks,
                "likes": total_row.likes
            },
            "top_queries": [{"query": r.query, "count": r.count} for r in top_queries],
            "zero_result_queries": [{"query": r.query, "count": r.count} for r in zero_results],
            "top_books": [{"title": r.book_title, "author": r.book_author, "click_type": r.click_type, "clicks": r.clicks} for r in top_books],
            "buy_clicks": {r.click_type: r.count for r in buy_clicks}
        }
    except Exception as e:
        return {"error": str(e)}
