"""
BookMind — Database Models
SQLAlchemy models with pgvector support for books, readers, children
"""
from __future__ import annotations
import uuid, enum
from datetime import datetime
from typing import Optional
from pgvector.sqlalchemy import Vector
from sqlalchemy import (Boolean, DateTime, Float, ForeignKey, Integer,
    String, Text, JSON, Enum, UniqueConstraint, Index)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    pass


class ReadingLevel(str, enum.Enum):
    PICTURE_BOOK = "picture_book"    # Ages 2-5
    EARLY_READER = "early_reader"    # Ages 5-7
    CHAPTER_BOOK = "chapter_book"    # Ages 6-10
    MIDDLE_GRADE = "middle_grade"    # Ages 8-12
    YOUNG_ADULT  = "young_adult"     # Ages 12-18
    ADULT        = "adult"           # 18+


class FeedbackSignal(str, enum.Enum):
    LOVED      = "loved"
    LIKED      = "liked"
    NEUTRAL    = "neutral"
    DISLIKED   = "disliked"
    ABANDONED  = "abandoned"
    FINISHED   = "finished"
    WISHLISTED = "wishlisted"
    PURCHASED  = "purchased"
    SHARED     = "shared"


class Book(Base):
    __tablename__ = "books"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    isbn_13: Mapped[Optional[str]] = mapped_column(String(13), unique=True, index=True)
    isbn_10: Mapped[Optional[str]] = mapped_column(String(10), unique=True)
    open_library_id: Mapped[Optional[str]] = mapped_column(String(50), unique=True)
    google_books_id: Mapped[Optional[str]] = mapped_column(String(50), unique=True)

    # Core metadata
    title: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    subtitle: Mapped[Optional[str]] = mapped_column(String(500))
    author: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    authors: Mapped[Optional[list]] = mapped_column(JSON)
    publisher: Mapped[Optional[str]] = mapped_column(String(300))
    published_year: Mapped[Optional[int]] = mapped_column(Integer)
    page_count: Mapped[Optional[int]] = mapped_column(Integer)
    language: Mapped[str] = mapped_column(String(10), default="en")
    cover_url: Mapped[Optional[str]] = mapped_column(String(1000))
    description: Mapped[Optional[str]] = mapped_column(Text)

    # Classification
    reading_level: Mapped[Optional[ReadingLevel]] = mapped_column(Enum(ReadingLevel), index=True)
    age_min: Mapped[Optional[int]] = mapped_column(Integer)
    age_max: Mapped[Optional[int]] = mapped_column(Integer)
    genres: Mapped[Optional[list]] = mapped_column(JSON)
    themes: Mapped[Optional[list]] = mapped_column(JSON)
    mood: Mapped[Optional[list]] = mapped_column(JSON)
    pace: Mapped[Optional[str]] = mapped_column(String(50))
    writing_style: Mapped[Optional[str]] = mapped_column(String(100))

    # Series info
    is_series: Mapped[bool] = mapped_column(Boolean, default=False)
    series_name: Mapped[Optional[str]] = mapped_column(String(300), index=True)
    series_position: Mapped[Optional[int]] = mapped_column(Integer)
    series_total: Mapped[Optional[int]] = mapped_column(Integer)

    # Kids content safety
    has_violence: Mapped[bool] = mapped_column(Boolean, default=False)
    has_scary_content: Mapped[bool] = mapped_column(Boolean, default=False)
    has_adult_themes: Mapped[bool] = mapped_column(Boolean, default=False)
    common_sense_rating: Mapped[Optional[int]] = mapped_column(Integer)
    content_warnings: Mapped[Optional[list]] = mapped_column(JSON)
    awards: Mapped[Optional[list]] = mapped_column(JSON)

    # Ratings
    goodreads_rating: Mapped[Optional[float]] = mapped_column(Float)
    goodreads_count: Mapped[Optional[int]] = mapped_column(Integer)

    # Affiliate data
    amazon_asin: Mapped[Optional[str]] = mapped_column(String(20))
    amazon_price: Mapped[Optional[float]] = mapped_column(Float)
    bookshop_id: Mapped[Optional[str]] = mapped_column(String(50))
    bookshop_price: Mapped[Optional[float]] = mapped_column(Float)
    audible_asin: Mapped[Optional[str]] = mapped_column(String(20))

    # Vector embedding (1536 dims)
    embedding: Mapped[Optional[list]] = mapped_column(Vector(1024))

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    embedding_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    feedbacks: Mapped[list["ReaderFeedback"]] = relationship(back_populates="book")
    recommendations: Mapped[list["Recommendation"]] = relationship(back_populates="book")

    __table_args__ = (
        Index("ix_books_embedding", "embedding",
              postgresql_using="hnsw",
              postgresql_with={"m": 16, "ef_construction": 64},
              postgresql_ops={"embedding": "vector_cosine_ops"}),
    )


class Reader(Base):
    __tablename__ = "readers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    name: Mapped[Optional[str]] = mapped_column(String(200))
    avatar_url: Mapped[Optional[str]] = mapped_column(String(1000))

    # Preferences
    preferred_genres: Mapped[Optional[list]] = mapped_column(JSON)
    avoided_genres: Mapped[Optional[list]] = mapped_column(JSON)
    preferred_pace: Mapped[Optional[str]] = mapped_column(String(50))
    preferred_formats: Mapped[Optional[list]] = mapped_column(JSON)
    reading_goal: Mapped[Optional[str]] = mapped_column(String(200))

    # Computed signals
    avg_rating_given: Mapped[Optional[float]] = mapped_column(Float)
    finish_rate: Mapped[Optional[float]] = mapped_column(Float)
    reads_per_month: Mapped[Optional[float]] = mapped_column(Float)

    # Taste vector — updates on every feedback signal
    taste_vector: Mapped[Optional[list]] = mapped_column(Vector(1024))

    onboarding_complete: Mapped[bool] = mapped_column(Boolean, default=False)
    onboarding_books: Mapped[Optional[list]] = mapped_column(JSON)

    digest_enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    last_active_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    children: Mapped[list["Child"]] = relationship(back_populates="parent")
    feedbacks: Mapped[list["ReaderFeedback"]] = relationship(back_populates="reader")
    recommendations: Mapped[list["Recommendation"]] = relationship(back_populates="reader")


class Child(Base):
    __tablename__ = "children"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    parent_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("readers.id"), nullable=False, index=True)

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    age: Mapped[int] = mapped_column(Integer, nullable=False)
    grade: Mapped[Optional[int]] = mapped_column(Integer)
    avatar_emoji: Mapped[Optional[str]] = mapped_column(String(10))

    reading_level: Mapped[ReadingLevel] = mapped_column(Enum(ReadingLevel), nullable=False)
    reads_independently: Mapped[bool] = mapped_column(Boolean, default=True)
    attention_span: Mapped[Optional[str]] = mapped_column(String(20))

    interests: Mapped[Optional[list]] = mapped_column(JSON)

    # Mom's safety filters
    avoid_scary: Mapped[bool] = mapped_column(Boolean, default=False)
    avoid_violence: Mapped[bool] = mapped_column(Boolean, default=False)
    avoid_sad_endings: Mapped[bool] = mapped_column(Boolean, default=False)
    custom_avoid_topics: Mapped[Optional[list]] = mapped_column(JSON)

    preferred_formats: Mapped[Optional[list]] = mapped_column(JSON)
    mom_goals: Mapped[Optional[list]] = mapped_column(JSON)

    taste_vector: Mapped[Optional[list]] = mapped_column(Vector(1024))

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    parent: Mapped["Reader"] = relationship(back_populates="children")
    feedbacks: Mapped[list["ChildFeedback"]] = relationship(back_populates="child")
    series_progress: Mapped[list["SeriesProgress"]] = relationship(back_populates="child")
    recommendations: Mapped[list["Recommendation"]] = relationship(back_populates="child")


class SeriesProgress(Base):
    __tablename__ = "series_progress"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    child_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("children.id"), nullable=False, index=True)

    series_name: Mapped[str] = mapped_column(String(300), nullable=False)
    books_read: Mapped[int] = mapped_column(Integer, default=0)
    total_books: Mapped[Optional[int]] = mapped_column(Integer)
    last_book_read: Mapped[Optional[str]] = mapped_column(String(500))
    next_book_isbn: Mapped[Optional[str]] = mapped_column(String(13))

    started_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    child: Mapped["Child"] = relationship(back_populates="series_progress")

    __table_args__ = (UniqueConstraint("child_id", "series_name"),)


class ReaderFeedback(Base):
    __tablename__ = "reader_feedbacks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    reader_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("readers.id"), nullable=False, index=True)
    book_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("books.id"), nullable=False, index=True)

    signal: Mapped[FeedbackSignal] = mapped_column(Enum(FeedbackSignal), nullable=False)
    rating: Mapped[Optional[int]] = mapped_column(Integer)
    review: Mapped[Optional[str]] = mapped_column(Text)
    percent_read: Mapped[Optional[int]] = mapped_column(Integer)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    reader: Mapped["Reader"] = relationship(back_populates="feedbacks")
    book: Mapped["Book"] = relationship(back_populates="feedbacks")

    __table_args__ = (UniqueConstraint("reader_id", "book_id"),)


class ChildFeedback(Base):
    __tablename__ = "child_feedbacks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    child_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("children.id"), nullable=False, index=True)
    book_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("books.id"), nullable=False, index=True)

    signal: Mapped[FeedbackSignal] = mapped_column(Enum(FeedbackSignal), nullable=False)
    child_rating: Mapped[Optional[int]] = mapped_column(Integer)  # 1-3 (simpler for kids)
    mom_notes: Mapped[Optional[str]] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    child: Mapped["Child"] = relationship(back_populates="feedbacks")

    __table_args__ = (UniqueConstraint("child_id", "book_id"),)


class Recommendation(Base):
    __tablename__ = "recommendations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    reader_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("readers.id"), index=True)
    child_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("children.id"), index=True)
    book_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("books.id"), nullable=False)

    reason: Mapped[Optional[str]] = mapped_column(Text)
    similarity_score: Mapped[Optional[float]] = mapped_column(Float)
    rank_in_session: Mapped[Optional[int]] = mapped_column(Integer)
    session_id: Mapped[Optional[str]] = mapped_column(String(100))
    trigger: Mapped[Optional[str]] = mapped_column(String(50))

    # Affiliate tracking
    affiliate_clicked: Mapped[bool] = mapped_column(Boolean, default=False)
    affiliate_store: Mapped[Optional[str]] = mapped_column(String(50))
    affiliate_clicked_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    reader: Mapped[Optional["Reader"]] = relationship(back_populates="recommendations")
    child: Mapped[Optional["Child"]] = relationship(back_populates="recommendations")
    book: Mapped["Book"] = relationship(back_populates="recommendations")
