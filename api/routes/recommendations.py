"""
Recommendation endpoints
"""
from __future__ import annotations
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from db.session import get_db
from db.models import Reader, Child
from agent.state import AgentState, BookCandidate
from agent.graph import get_recommendations
import uuid

router = APIRouter()


class RecommendRequest(BaseModel):
    message: Optional[str] = None
    count: int = 5
    trigger: str = "chat"


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
