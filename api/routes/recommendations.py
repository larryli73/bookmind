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

router = APIRouter()

_DB_URL = os.getenv("DATABASE_URL", "").replace("postgresql+asyncpg://", "postgresql://").replace("postgres://", "postgresql://")


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

    return {
        "recommendations": [format_book(b) for b in final_recs],
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

    return {
        "child_name":      child.name,
        "recommendations": [format_book(b) for b in final_recs],
        "series_next":     [format_book(b) for b in series_next],
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
    return {
        "recommendations": [format_book(b) for b in final_recs],
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

    conn = await asyncpg.connect(_DB_URL)
    try:
        if db_goals:
            # Build goal filter — book must match at least one selected goal
            goal_conditions = " OR ".join([
                f"learning_goals::text LIKE '%{g}%'" for g in db_goals
            ])
            rows = await conn.fetch(f"""
                SELECT id, title, author, cover_url, age_min, age_max,
                       learning_goals, page_count, genres
                FROM books
                WHERE is_children_book = TRUE
                AND age_min <= $1
                AND age_max >= $2
                AND ({goal_conditions})
                ORDER BY
                    CASE WHEN cover_url IS NOT NULL THEN 0 ELSE 1 END,
                    CASE WHEN age_min <= $3 AND age_max >= $3 THEN 0 ELSE 1 END,
                    page_count DESC NULLS LAST
                LIMIT $4
            """, age_max, age_min, age, limit)
        else:
            rows = await conn.fetch("""
                SELECT id, title, author, cover_url, age_min, age_max,
                       learning_goals, page_count, genres
                FROM books
                WHERE is_children_book = TRUE
                AND age_min <= $1
                AND age_max >= $2
                ORDER BY
                    CASE WHEN cover_url IS NOT NULL THEN 0 ELSE 1 END,
                    CASE WHEN age_min <= $3 AND age_max >= $3 THEN 0 ELSE 1 END,
                    page_count DESC NULLS LAST
                LIMIT $4
            """, age_max, age_min, age, limit)

        # If strict age window gives too few results, widen it
        if len(rows) < 3:
            rows = await conn.fetch("""
                SELECT id, title, author, cover_url, age_min, age_max,
                       learning_goals, page_count, genres
                FROM books
                WHERE is_children_book = TRUE
                AND age_min <= $1
                AND age_max >= $2
                ORDER BY
                    CASE WHEN cover_url IS NOT NULL THEN 0 ELSE 1 END,
                    page_count DESC NULLS LAST
                LIMIT $3
            """, age + 4, max(0, age - 3), limit)

    finally:
        await conn.close()

    AFFILIATE_TAG = os.getenv("AMAZON_AFFILIATE_TAG", "bookmind-20")
    BOOKSHOP_ID = os.getenv("BOOKSHOP_AFFILIATE_ID", "124067")

    recs = []
    for r in rows:
        book_goals = json.loads(r["learning_goals"] or "[]")
        title_enc = r["title"].replace(" ", "+").replace("'", "")
        recs.append({
            "book_id":   str(r["id"]),
            "title":     r["title"],
            "author":    r["author"] or "",
            "cover_url": r["cover_url"],
            "reason":    _goal_reason(book_goals, goals, r["title"]),
            "page_count": r["page_count"],
            "genres":    json.loads(r["genres"] or "[]") if r["genres"] else [],
            "is_series": False,
            "awards":    [],
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
