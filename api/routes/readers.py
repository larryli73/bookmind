"""Reader (adult user) management endpoints"""
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from db.session import get_db
from db.models import Reader

router = APIRouter()


class CreateReaderRequest(BaseModel):
    email: EmailStr
    name: Optional[str] = None


class UpdatePreferencesRequest(BaseModel):
    preferred_genres: Optional[list[str]] = None
    avoided_genres: Optional[list[str]] = None
    preferred_pace: Optional[str] = None
    reading_goal: Optional[str] = None
    digest_enabled: Optional[bool] = None


@router.post("/")
async def create_reader(req: CreateReaderRequest, db: AsyncSession = Depends(get_db)):
    """Create a new reader account"""
    reader = Reader(email=req.email, name=req.name)
    db.add(reader)
    await db.commit()
    await db.refresh(reader)
    return {"reader_id": str(reader.id), "email": reader.email}


@router.get("/{reader_id}")
async def get_reader(reader_id: UUID, db: AsyncSession = Depends(get_db)):
    reader = await db.get(Reader, reader_id)
    if not reader:
        raise HTTPException(404, "Reader not found")
    return {
        "id": str(reader.id),
        "email": reader.email,
        "name": reader.name,
        "onboarding_complete": reader.onboarding_complete,
        "children_count": len(reader.children) if reader.children else 0,
    }


@router.patch("/{reader_id}/preferences")
async def update_preferences(
    reader_id: UUID,
    req: UpdatePreferencesRequest,
    db: AsyncSession = Depends(get_db)
):
    reader = await db.get(Reader, reader_id)
    if not reader:
        raise HTTPException(404, "Reader not found")

    for field, value in req.model_dump(exclude_none=True).items():
        setattr(reader, field, value)

    await db.commit()
    return {"status": "updated"}
