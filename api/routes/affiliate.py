"""Affiliate click tracking — logs when users click buy links"""
from uuid import UUID
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from db.session import get_db
from db.models import Recommendation
from datetime import datetime

router = APIRouter()


class AffiliateClickRequest(BaseModel):
    recommendation_id: UUID
    store: str                # "amazon" | "bookshop" | "audible"


@router.post("/click")
async def track_affiliate_click(req: AffiliateClickRequest, db: AsyncSession = Depends(get_db)):
    """
    Log affiliate link clicks for revenue tracking.
    Call this when user clicks any 'Buy' button.
    """
    rec = await db.get(Recommendation, req.recommendation_id)
    if rec:
        rec.affiliate_clicked    = True
        rec.affiliate_store      = req.store
        rec.affiliate_clicked_at = datetime.utcnow()
        await db.commit()

    return {"status": "click tracked"}


@router.get("/stats")
async def affiliate_stats(db: AsyncSession = Depends(get_db)):
    """Basic affiliate click stats — track your revenue signals"""
    from sqlalchemy import func, text
    result = await db.execute(
        text("""
            SELECT 
                affiliate_store,
                COUNT(*) as clicks,
                COUNT(*) FILTER (WHERE affiliate_clicked = true) as clicked
            FROM recommendations
            GROUP BY affiliate_store
        """)
    )
    rows = result.all()
    return [{"store": r[0], "total": r[1], "clicked": r[2]} for r in rows]
