"""
Claude Fallback node — when DB vector search returns poor matches,
ask Claude directly for recommendations based on its own knowledge.
Claude returns title/author/reason, we build book cards with Amazon links.
"""
from __future__ import annotations
import json
import re
import os
import uuid
import asyncpg
from anthropic import AsyncAnthropic
from agent.state import AgentState, BookCandidate

client = AsyncAnthropic()

# Similarity score below this = DB doesn't have good matches
WEAK_MATCH_THRESHOLD = 0.75

# DB URL for looking up books by title after Claude suggests them
_DB_URL = os.getenv("DATABASE_URL", "").replace("postgresql+asyncpg://", "postgresql://").replace("postgres://", "postgresql://")

AFFILIATE_TAG = os.getenv("AMAZON_AFFILIATE_TAG", "bookmind-20")
BOOKSHOP_ID = os.getenv("BOOKSHOP_AFFILIATE_ID", "124067")


def db_results_are_weak(state: AgentState) -> bool:
    """Check if vector search returned low-confidence results."""
    candidates = state.filtered_candidates or state.candidates
    if not candidates:
        return True
    # Check average similarity of top 3
    top = sorted(candidates, key=lambda c: c.similarity_score if hasattr(c, 'similarity_score') else 0, reverse=True)[:3]
    scores = [c.similarity_score for c in top if hasattr(c, 'similarity_score')]
    if not scores:
        return True
    avg_score = sum(scores) / len(scores)
    return avg_score < WEAK_MATCH_THRESHOLD


async def lookup_book_in_db(conn, title: str, author: str):
    """Try to find a Claude-suggested book in our DB for richer metadata."""
    try:
        row = await conn.fetchrow("""
            SELECT id, title, author, cover_url, description, page_count,
                   goodreads_rating, awards, genres, is_series, amazon_asin
            FROM books
            WHERE LOWER(title) = LOWER($1)
               OR (LOWER(title) LIKE LOWER($2) AND LOWER(author) LIKE LOWER($3))
            LIMIT 1
        """, title, f"%{title[:20]}%", f"%{author.split()[0]}%")
        return dict(row) if row else None
    except Exception:
        return None


def make_buy_links(title: str) -> dict:
    enc = title.replace(" ", "+").replace("'", "")
    return {
        "amazon": f"https://www.amazon.com/s?k={enc}&tag={AFFILIATE_TAG}",
        "bookshop": f"https://bookshop.org/search?keywords={enc}&affiliate={BOOKSHOP_ID}",
    }


async def claude_recommend(state: AgentState) -> AgentState:
    """Ask Claude directly for book recommendations when DB matches are weak."""

    count = state.requested_count or 5
    user_msg = state.user_message or "general reading"

    prompt = f"""A reader said: "{user_msg}"

Recommend {count} books that perfectly match this request. These should be real, well-known books a librarian or bookseller would suggest.

Return ONLY a JSON array:
[
  {{
    "title": "exact book title",
    "author": "Author Name",
    "reason": "2 sentences explaining why this fits the reader's request specifically"
  }}
]

Rules:
- Real books only — no made-up titles
- Match the genre/mood/style of what they asked for exactly
- Vary your picks — don't just list sequels or the same author
- No markdown, just the JSON array"""

    try:
        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}]
        )
        state.total_tokens_used += response.usage.input_tokens + response.usage.output_tokens
        raw = response.content[0].text.strip()

        m = re.search(r'\[.*\]', raw, re.DOTALL)
        if not m:
            state.errors.append("claude_fallback: no JSON found")
            return state

        suggestions = json.loads(m.group())

    except Exception as e:
        state.errors.append(f"claude_fallback error: {e}")
        return state

    # Try to enrich each suggestion from our DB
    conn = None
    try:
        if _DB_URL:
            conn = await asyncpg.connect(_DB_URL, timeout=5)
    except Exception:
        conn = None

    final = []
    for s in suggestions:
        title = s.get("title", "")
        author = s.get("author", "")
        reason = s.get("reason", "")
        if not title:
            continue

        buy = make_buy_links(title)
        db_row = None
        if conn:
            db_row = await lookup_book_in_db(conn, title, author)

        if db_row:
            import json as _json
            def _parse_list(val):
                if isinstance(val, list): return val
                if isinstance(val, str):
                    try: return _json.loads(val)
                    except Exception: return []
                return []
            # Use real DB data
            candidate = BookCandidate(
                book_id=db_row["id"],
                title=db_row["title"],
                author=db_row["author"],
                cover_url=db_row.get("cover_url"),
                description=db_row.get("description"),
                page_count=db_row.get("page_count"),
                goodreads_rating=db_row.get("goodreads_rating"),
                awards=_parse_list(db_row.get("awards")),
                genres=_parse_list(db_row.get("genres")),
                is_series=db_row.get("is_series") or False,
                reason=reason,
                similarity_score=0.99,  # Claude-selected = high confidence
                amazon_url=buy["amazon"],
                bookshop_url=buy["bookshop"],
            )
        else:
            # Build a lightweight card from Claude's suggestion alone
            candidate = BookCandidate(
                book_id=uuid.uuid4(),
                title=title,
                author=author,
                reason=reason,
                similarity_score=0.99,
                amazon_url=buy["amazon"],
                bookshop_url=buy["bookshop"],
            )
        final.append(candidate)

    if conn:
        await conn.close()

    if final:
        state.final_recommendations = final
        state.pipeline_steps.append(f"claude_fallback: generated {len(final)} recs from Claude knowledge")

    return state


async def maybe_claude_fallback(state: AgentState) -> AgentState:
    """
    Entry point: run fallback only when DB results are weak.
    Otherwise pass through unchanged.
    """
    if db_results_are_weak(state):
        state.pipeline_steps.append("claude_fallback: DB matches weak, using Claude knowledge")
        return await claude_recommend(state)
    state.pipeline_steps.append("claude_fallback: DB matches strong, skipping")
    return state
