"""
BookMind Agent State — the shared state that flows through the LangGraph pipeline
"""
from __future__ import annotations
from typing import Optional, Literal
from uuid import UUID
from pydantic import BaseModel, Field


class BookCandidate(BaseModel):
    """A candidate book with its similarity score and affiliate links"""
    book_id: UUID
    title: str
    author: str
    cover_url: Optional[str] = None
    description: Optional[str] = None
    page_count: Optional[int] = None
    genres: list[str] = []
    themes: list[str] = []
    goodreads_rating: Optional[float] = None
    awards: list[str] = []
    is_series: bool = False
    series_name: Optional[str] = None
    series_position: Optional[int] = None
    series_total: Optional[int] = None

    # Scores
    similarity_score: float = 0.0
    collab_score: float = 0.0
    final_score: float = 0.0

    # Claude's reasoning
    reason: Optional[str] = None   # "Why this book is perfect for YOU"

    # Affiliate links
    amazon_url: Optional[str] = None
    amazon_price: Optional[float] = None
    bookshop_url: Optional[str] = None
    bookshop_price: Optional[float] = None
    audible_url: Optional[str] = None


class AgentState(BaseModel):
    """
    Full state flowing through the LangGraph recommendation pipeline.
    Every node reads from and writes to this state.
    """

    # ── Who is this for? ─────────────────────────────────────
    mode: Literal["adult", "child"] = "adult"
    reader_id: Optional[UUID] = None
    child_id: Optional[UUID] = None
    session_id: str = ""

    # ── Reader context ────────────────────────────────────────
    reader_name: Optional[str] = None
    taste_vector: Optional[list[float]] = None

    # ── Child context (when mode == "child") ─────────────────
    child_name: Optional[str] = None
    child_age: Optional[int] = None
    child_reading_level: Optional[str] = None
    child_interests: list[str] = []
    avoid_scary: bool = False
    avoid_violence: bool = False
    avoid_sad_endings: bool = False

    # ── Extracted intent ─────────────────────────────────────
    seed_titles: list[str] = []              # Books/authors user mentioned
    loved_because: list[str] = []            # What they loved
    mood: Optional[str] = None               # Current mood
    constraints: list[str] = []             # Any constraints

    # ── Request ───────────────────────────────────────────────
    user_message: Optional[str] = None       # e.g. "I loved Dune, what's next?"
    trigger: str = "chat"                    # chat / taste_quiz / digest / series_next
    requested_count: int = 5

    # ── Already read (to exclude) ────────────────────────────
    read_book_ids: list[UUID] = []
    disliked_book_ids: list[UUID] = []

    # ── Pipeline data ─────────────────────────────────────────
    query_vector: Optional[list[float]] = None     # Computed from message or taste
    candidates: list[BookCandidate] = []            # 50 from vector search
    filtered_candidates: list[BookCandidate] = []   # After content filter
    final_recommendations: list[BookCandidate] = [] # Top 5 with reasons

    # ── Series (for kids) ─────────────────────────────────────
    series_next_books: list[BookCandidate] = []    # Next in series being read

    # ── Conversation history ──────────────────────────────────
    messages: list[dict] = Field(default_factory=list)

    # ── Pipeline metadata ─────────────────────────────────────
    errors: list[str] = []
    pipeline_steps: list[str] = []
    total_tokens_used: int = 0

    class Config:
        arbitrary_types_allowed = True
