"""
Affiliate linker tool — attaches affiliate URLs to final recommendations
"""
from __future__ import annotations
import os
from agent.state import AgentState

AMAZON_TAG    = os.getenv("AMAZON_AFFILIATE_TAG",    "bookmind-20")
BOOKSHOP_ID   = os.getenv("BOOKSHOP_AFFILIATE_ID",   "")
AUDIBLE_TAG   = os.getenv("AUDIBLE_AFFILIATE_TAG",   "bookmind-audible-20")


def amazon_url(asin: str | None, isbn: str | None = None) -> str | None:
    if asin:
        return f"https://www.amazon.com/dp/{asin}?tag={AMAZON_TAG}"
    if isbn:
        return f"https://www.amazon.com/s?k={isbn}&tag={AMAZON_TAG}"
    return None


def bookshop_url(bookshop_id: str | None, title: str = "") -> str | None:
    if bookshop_id:
        return f"https://bookshop.org/a/{BOOKSHOP_ID}/{bookshop_id}"
    if title:
        slug = title.lower().replace(" ", "-")[:50]
        return f"https://bookshop.org/a/{BOOKSHOP_ID}/search?keywords={slug}"
    return None


def audible_url(asin: str | None) -> str | None:
    if asin:
        return f"https://www.audible.com/pd/{asin}?tag={AUDIBLE_TAG}"
    return None


async def attach_affiliate_links(state: AgentState) -> AgentState:
    """Attach affiliate URLs to every final recommendation"""
    for book in state.final_recommendations:
        book.amazon_url  = amazon_url(getattr(book, 'amazon_asin', None))
        book.bookshop_url = bookshop_url(getattr(book, 'bookshop_id', None), book.title)
        book.audible_url  = audible_url(getattr(book, 'audible_asin', None))

    state.pipeline_steps.append("affiliate_links: attached")
    return state
