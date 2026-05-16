"""
Recommendation endpoints
"""
from __future__ import annotations
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from db.session import get_db
from db.models import Reader, Child
from agent.state import AgentState, BookCandidate
from agent.graph import get_recommendations
import uuid
import asyncpg
import os
import json
import httpx

router = APIRouter()

_DB_URL = os.getenv("DATABASE_URL", "").replace("postgresql+asyncpg://", "postgresql://").replace("postgres://", "postgresql://")
_GOOGLE_BOOKS_KEY = os.getenv("GOOGLE_BOOKS_API_KEY", "")


async def _fetch_cover_url(title: str, author: str) -> Optional[str]:
    """
    Fetch a cover image URL for a given title/author.
    Uses Open Library (no API key needed) with Google Books as fallback.
    """
    # 1. Try Open Library
    try:
        params = {"title": title, "author": author.split()[0], "limit": 1, "fields": "cover_i"}
        async with httpx.AsyncClient(timeout=4.0) as client:
            r = await client.get("https://openlibrary.org/search.json", params=params)
            data = r.json()
        docs = data.get("docs", [])
        if docs and docs[0].get("cover_i"):
            cover_id = docs[0]["cover_i"]
            return f"https://covers.openlibrary.org/b/id/{cover_id}-L.jpg"
    except Exception:
        pass

    # 2. Fallback: Google Books (requires API key for reliable access)
    if _GOOGLE_BOOKS_KEY:
        try:
            params = {"q": f"{title} {author}", "maxResults": 1,
                      "fields": "items/volumeInfo/imageLinks", "key": _GOOGLE_BOOKS_KEY}
            async with httpx.AsyncClient(timeout=4.0) as client:
                r = await client.get("https://www.googleapis.com/books/v1/volumes", params=params)
                data = r.json()
            items = data.get("items", [])
            if items:
                links = items[0].get("volumeInfo", {}).get("imageLinks", {})
                for size in ("large", "medium", "thumbnail", "smallThumbnail"):
                    if size in links:
                        return links[size].replace("http://", "https://").replace("&edge=curl", "")
        except Exception:
            pass

    return None


async def _enrich_covers(books: list, conn) -> list:
    """
    For any book missing a cover_url, fetch all covers concurrently then persist.
    Sequential fetching (old approach) caused Railway request timeouts.
    """
    import asyncio

    missing = [(i, b) for i, b in enumerate(books) if not b.get("cover_url") and b.get("title")]
    if not missing:
        return books

    # Fetch all missing covers in parallel
    covers = await asyncio.gather(
        *[_fetch_cover_url(b.get("title", ""), b.get("author", "")) for _, b in missing],
        return_exceptions=True
    )

    for (i, book), cover in zip(missing, covers):
        if not cover or isinstance(cover, Exception):
            continue
        book["cover_url"] = cover
        book_id = book.get("book_id")
        if book_id and conn:
            try:
                await conn.execute(
                    "UPDATE books SET cover_url=$1 WHERE id=$2 AND cover_url IS NULL",
                    cover, uuid.UUID(str(book_id))
                )
            except Exception:
                pass

    return books


class RecommendRequest(BaseModel):
    message: Optional[str] = None
    count: int = 5
    trigger: str = "chat"
    # Child-specific params (sent by frontend child mode)
    child_age: Optional[int] = None
    reading_level: Optional[str] = None
    learning_goals: Optional[List[str]] = None
    content_concerns: Optional[List[str]] = None


class ChildRecommendRequest(BaseModel):
    child_id: UUID
    message: Optional[str] = None
    count: int = 5
    trigger: str = "chat"


def format_book(b) -> dict:
    """Safely format a book candidate whether it's an object or dict"""
    if isinstance(b, dict):
        buy_links = b.get("buy_links", {}) or {}
        return {
            "book_id":          str(b.get("book_id", "")),
            "title":            b.get("title", ""),
            "author":           b.get("author", ""),
            "cover_url":        b.get("cover_url"),
            "reason":           b.get("reason"),
            "goodreads_rating": b.get("goodreads_rating"),
            "page_count":       b.get("page_count"),
            "genres":           b.get("genres", []),
            "is_series":        b.get("is_series", False),
            "series_name":      b.get("series_name"),
            "series_position":  b.get("series_position"),
            "awards":           b.get("awards", []),
            "buy_links": {
                "amazon":   b.get("amazon_url") or buy_links.get("amazon"),
                "bookshop": b.get("bookshop_url") or buy_links.get("bookshop"),
                "audible":  b.get("audible_url") or buy_links.get("audible"),
            }
        }
    else:
        return {
            "book_id":          str(b.book_id),
            "title":            b.title,
            "author":           b.author,
            "cover_url":        b.cover_url,
            "reason":           b.reason,
            "goodreads_rating": b.goodreads_rating,
            "page_count":       b.page_count,
            "genres":           b.genres,
            "is_series":        b.is_series,
            "series_name":      b.series_name,
            "series_position":  b.series_position,
            "awards":           b.awards,
            "buy_links": {
                "amazon":   b.amazon_url,
                "bookshop": b.bookshop_url,
                "audible":  b.audible_url,
            }
        }


@router.post("/for-me")
async def recommend_for_reader(
    req: RecommendRequest,
    reader_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    reader = await db.get(Reader, reader_id)
    if not reader:
        raise HTTPException(status_code=404, detail="Reader not found")

    state = AgentState(
        mode="adult",
        reader_id=reader_id,
        reader_name=reader.name,
        session_id=str(uuid.uuid4()),
        user_message=req.message,
        trigger=req.trigger,
        requested_count=req.count,
        taste_vector=reader.taste_vector,
        read_book_ids=[],
    )

    result = await get_recommendations(state)

    # Handle both dict and AgentState returns from LangGraph
    if isinstance(result, dict):
        final_recs = result.get("final_recommendations", [])
        pipeline_steps = result.get("pipeline_steps", [])
        errors = result.get("errors", [])
    else:
        final_recs = result.final_recommendations
        pipeline_steps = result.pipeline_steps
        errors = result.errors

    formatted = [format_book(b) for b in final_recs]

    # Fetch missing covers and cache them in DB
    try:
        conn = await asyncpg.connect(_DB_URL, timeout=5) if _DB_URL else None
        formatted = await _enrich_covers(formatted, conn)
        if conn:
            await conn.close()
    except Exception:
        pass

    return {
        "recommendations": formatted,
        "session_id":      state.session_id,
        "pipeline_steps":  pipeline_steps,
        "errors":          errors,
    }


@router.post("/for-child")
async def recommend_for_child(
    req: ChildRecommendRequest,
    reader_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    child = await db.get(Child, req.child_id)
    if not child or child.parent_id != reader_id:
        raise HTTPException(status_code=404, detail="Child not found")

    state = AgentState(
        mode="child",
        reader_id=reader_id,
        child_id=req.child_id,
        child_name=child.name,
        child_age=child.age,
        child_reading_level=child.reading_level.value,
        child_interests=child.interests or [],
        avoid_scary=child.avoid_scary,
        avoid_violence=child.avoid_violence,
        avoid_sad_endings=child.avoid_sad_endings,
        session_id=str(uuid.uuid4()),
        user_message=req.message,
        trigger=req.trigger,
        requested_count=req.count,
        taste_vector=child.taste_vector,
        read_book_ids=[],
    )

    result = await get_recommendations(state)

    if isinstance(result, dict):
        final_recs = result.get("final_recommendations", [])
        series_next = result.get("series_next_books", [])
    else:
        final_recs = result.final_recommendations
        series_next = result.series_next_books

    formatted      = [format_book(b) for b in final_recs]
    formatted_next = [format_book(b) for b in series_next]
    try:
        conn = await asyncpg.connect(_DB_URL, timeout=5) if _DB_URL else None
        formatted      = await _enrich_covers(formatted, conn)
        formatted_next = await _enrich_covers(formatted_next, conn)
        if conn:
            await conn.close()
    except Exception:
        pass

    return {
        "child_name":      child.name,
        "recommendations": formatted,
        "series_next":     formatted_next,
        "session_id":      state.session_id,
    }


@router.post("/{reader_id}")
async def recommend_unified(reader_id: UUID, req: RecommendRequest):
    """
    Unified endpoint called by the frontend for both adult and child searches.
    Child searches (trigger='child_search') query the structured books DB directly.
    Adult searches fall through to the LLM agent.
    """
    if req.trigger == "child_search" and req.child_age is not None:
        return await _child_search_from_db(reader_id, req)

    # Adult search — use LLM agent via for-me
    state = AgentState(
        mode="adult",
        reader_id=reader_id,
        session_id=str(uuid.uuid4()),
        user_message=req.message,
        trigger=req.trigger,
        requested_count=req.count,
        taste_vector=None,
        read_book_ids=[],
    )
    result = await get_recommendations(state)
    if isinstance(result, dict):
        final_recs = result.get("final_recommendations", [])
    else:
        final_recs = result.final_recommendations

    formatted = [format_book(b) for b in final_recs]
    try:
        conn = await asyncpg.connect(_DB_URL, timeout=5) if _DB_URL else None
        formatted = await _enrich_covers(formatted, conn)
        if conn:
            await conn.close()
    except Exception:
        pass

    return {
        "recommendations": formatted,
        "session_id": state.session_id,
    }


async def _child_search_from_db(reader_id: UUID, req: RecommendRequest) -> dict:
    """Query the books DB directly for children's books by age and learning goals."""
    age = req.child_age
    goals = req.learning_goals or []
    concerns = req.content_concerns or []
    limit = req.count or 6

    # Map reading level to age window
    if req.reading_level == "together":
        age_min, age_max = max(0, age - 2), age + 1
    elif req.reading_level == "help":
        age_min, age_max = max(0, age - 1), age + 2
    else:  # independent
        age_min, age_max = max(0, age - 1), age + 3

    # Normalise goals for DB (problem-solving → problem_solving)
    db_goals = [g.replace("-", "_") for g in goals]

    conn = await asyncpg.connect(_DB_URL, timeout=5)
    try:
        if db_goals:
            # Use regex match with parameterized value — safe from injection
            goal_regex = "|".join(db_goals)
            rows = await conn.fetch("""
                SELECT id, title, author, cover_url, age_min, age_max,
                       learning_goals, page_count, genres, awards, description
                FROM books
                WHERE is_children_book = TRUE
                AND age_min <= $1
                AND age_max >= $2
                AND learning_goals::text ~ $5
                ORDER BY
                    CASE WHEN cover_url IS NOT NULL THEN 0 ELSE 1 END,
                    CASE WHEN age_min <= $3 AND age_max >= $3 THEN 0 ELSE 1 END,
                    CASE WHEN awards IS NOT NULL AND awards::text != '[]' THEN 0 ELSE 1 END,
                    (age_max - age_min) ASC,
                    CASE WHEN description IS NOT NULL THEN 0 ELSE 1 END,
                    RANDOM()
                LIMIT $4
            """, age_max, age_min, age, limit, goal_regex)
        else:
            rows = await conn.fetch("""
                SELECT id, title, author, cover_url, age_min, age_max,
                       learning_goals, page_count, genres, awards, description
                FROM books
                WHERE is_children_book = TRUE
                AND age_min <= $1
                AND age_max >= $2
                ORDER BY
                    CASE WHEN cover_url IS NOT NULL THEN 0 ELSE 1 END,
                    CASE WHEN age_min <= $3 AND age_max >= $3 THEN 0 ELSE 1 END,
                    CASE WHEN awards IS NOT NULL AND awards::text != '[]' THEN 0 ELSE 1 END,
                    (age_max - age_min) ASC,
                    CASE WHEN description IS NOT NULL THEN 0 ELSE 1 END,
                    RANDOM()
                LIMIT $4
            """, age_max, age_min, age, limit)

        # If strict age window gives too few results, widen it
        if len(rows) < 3:
            rows = await conn.fetch("""
                SELECT id, title, author, cover_url, age_min, age_max,
                       learning_goals, page_count, genres, awards, description
                FROM books
                WHERE is_children_book = TRUE
                AND age_min <= $1
                AND age_max >= $2
                ORDER BY
                    CASE WHEN cover_url IS NOT NULL THEN 0 ELSE 1 END,
                    CASE WHEN awards IS NOT NULL AND awards::text != '[]' THEN 0 ELSE 1 END,
                    (age_max - age_min) ASC,
                    RANDOM()
                LIMIT $3
            """, age + 4, max(0, age - 3), limit)

    finally:
        await conn.close()

    AFFILIATE_TAG = os.getenv("AMAZON_AFFILIATE_TAG", "bookmind-20")
    BOOKSHOP_ID = os.getenv("BOOKSHOP_AFFILIATE_ID", "124067")

    def _safe_list(val):
        if isinstance(val, list): return val
        if isinstance(val, str):
            try: return json.loads(val)
            except Exception: return []
        return []

    recs = []
    for r in rows:
        book_goals = _safe_list(r["learning_goals"])
        title_enc = r["title"].replace(" ", "+").replace("'", "")
        awards = _safe_list(r["awards"])
        recs.append({
            "book_id":    str(r["id"]),
            "title":      r["title"],
            "author":     r["author"] or "",
            "cover_url":  r["cover_url"],
            "description": r["description"],
            "reason":     _goal_reason(book_goals, goals, r["title"]),
            "page_count": r["page_count"],
            "genres":     _safe_list(r["genres"]),
            "is_series":  False,
            "awards":     awards,
            "buy_links": {
                "amazon":   f"https://www.amazon.com/s?k={title_enc}&tag={AFFILIATE_TAG}",
                "bookshop": f"https://bookshop.org/search?keywords={title_enc}&affiliate={BOOKSHOP_ID}",
            }
        })

    return {
        "recommendations": recs,
        "session_id": str(uuid.uuid4()),
    }


def _goal_reason(book_goals: list, requested_goals: list, title: str) -> str:
    """Generate a short reason string based on matched goals."""
    GOAL_LABELS = {
        "kindness": "kindness and empathy",
        "courage": "courage and confidence",
        "friendship": "friendship and loyalty",
        "emotions": "emotional intelligence",
        "science": "curiosity and science",
        "history": "history and culture",
        "diversity": "diversity and inclusion",
        "resilience": "resilience and grit",
        "problem_solving": "problem-solving",
        "environment": "love of nature",
        "family": "family and belonging",
        "creativity": "creativity and imagination",
    }
    db_requested = [g.replace("-", "_") for g in requested_goals]
    matched = [GOAL_LABELS[g] for g in book_goals if g in db_requested and g in GOAL_LABELS]
    if matched:
        return f"Teaches {', '.join(matched[:2])}"
    if book_goals:
        labels = [GOAL_LABELS.get(g, g) for g in book_goals[:2] if g in GOAL_LABELS]
        if labels:
            return f"Develops {', '.join(labels)}"
    return "A great pick for this age group"
