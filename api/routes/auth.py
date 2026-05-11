"""
Auth routes — signup, login, me
No login required to use BookMind — auth is optional for personalization
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
import bcrypt
import jwt
import os
from datetime import datetime, timedelta
from db.session import get_db
from db.models import Reader

router = APIRouter()

SECRET_KEY = os.getenv("JWT_SECRET", "bookmind-secret-change-in-production")
ALGORITHM = "HS256"
TOKEN_EXPIRE_DAYS = 30


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def create_token(reader_id: str) -> str:
    payload = {
        "reader_id": reader_id,
        "exp": datetime.utcnow() + timedelta(days=TOKEN_EXPIRE_DAYS)
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> Optional[str]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload.get("reader_id")
    except Exception:
        return None


class SignupRequest(BaseModel):
    email: EmailStr
    password: str
    name: Optional[str] = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class AnonymousRequest(BaseModel):
    """Create anonymous session — no email needed"""
    pass


@router.post("/signup")
async def signup(req: SignupRequest, db: AsyncSession = Depends(get_db)):
    """Create new account with email + password"""
    # Check if email already exists
    result = await db.execute(select(Reader).where(Reader.email == req.email))
    existing = result.scalar_one_or_none()

    if existing:
        if existing.password_hash:
            raise HTTPException(400, "Email already registered. Please login.")
        else:
            # Anonymous user upgrading to full account
            existing.password_hash = hash_password(req.password)
            existing.name = req.name or existing.name
            await db.commit()
            token = create_token(str(existing.id))
            return {
                "token": token,
                "reader_id": str(existing.id),
                "email": existing.email,
                "name": existing.name,
                "is_new": False
            }

    # Create new reader
    reader = Reader(
        email=req.email,
        name=req.name,
        password_hash=hash_password(req.password)
    )
    db.add(reader)
    await db.commit()
    await db.refresh(reader)

    token = create_token(str(reader.id))
    return {
        "token": token,
        "reader_id": str(reader.id),
        "email": reader.email,
        "name": reader.name,
        "is_new": True
    }


@router.post("/login")
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Login with email + password"""
    result = await db.execute(select(Reader).where(Reader.email == req.email))
    reader = result.scalar_one_or_none()

    if not reader or not reader.password_hash:
        raise HTTPException(401, "Invalid email or password")

    if not verify_password(req.password, reader.password_hash):
        raise HTTPException(401, "Invalid email or password")

    token = create_token(str(reader.id))
    return {
        "token": token,
        "reader_id": str(reader.id),
        "email": reader.email,
        "name": reader.name
    }


@router.post("/anonymous")
async def create_anonymous(db: AsyncSession = Depends(get_db)):
    """Create anonymous session — no email needed, used for first-time visitors"""
    import uuid
    fake_email = f"anon_{uuid.uuid4().hex[:12]}@bookmind.app"
    reader = Reader(email=fake_email, name="Guest")
    db.add(reader)
    await db.commit()
    await db.refresh(reader)

    token = create_token(str(reader.id))
    return {
        "token": token,
        "reader_id": str(reader.id),
        "is_anonymous": True
    }


@router.get("/me")
async def get_me(token: str, db: AsyncSession = Depends(get_db)):
    """Get current user from token"""
    reader_id = decode_token(token)
    if not reader_id:
        raise HTTPException(401, "Invalid or expired token")

    reader = await db.get(Reader, reader_id)
    if not reader:
        raise HTTPException(404, "User not found")

    return {
        "reader_id": str(reader.id),
        "email": reader.email,
        "name": reader.name,
        "is_anonymous": reader.email.endswith("@bookmind.app"),
        "onboarding_complete": reader.onboarding_complete
    }
