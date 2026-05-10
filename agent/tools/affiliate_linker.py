"""
Affiliate linker tool — attaches affiliate URLs to final recommendations
"""
from __future__ import annotations
import os
from urllib.parse import quote_plus
from agent.state import AgentState

AMAZON_TAG    = os.getenv("AMAZON_AFFILIATE_TAG", "bookmind88-20")
BOOKSHOP_ID   = os.getenv("BOOKSHOP_AFFILIATE_ID", "124067")
AUDIBLE_TAG   = os.getenv("AUDIBLE_AFFILIATE_TAG", "bookmind88-20")


def amazon_url(title: str, author: str, asin: str | None = None, isbn: str | None = None) -> str:
    """Build Amazon affiliate URL — always works even without ASIN"""
    if asin:
        return f"https://www.amazon.com/dp/{asin}?tag={AMAZON_TAG}"
    if isbn:
        return f"https://www.amazon.com/s?k={isbn}&tag={AMAZON_TAG}"
    # Fallback: search by title + author
    query = quote_plus(f"{title} {author}")
    return f"https://www.amazon.com/s?k={query}&tag={AMAZON_TAG}"


def bookshop_url(title: str, bookshop_id: str | None = None) -> str:
    """Build Bookshop.org affiliate URL"""
    if bookshop_id and BOOKSHOP_ID:
        return f"https://bookshop.org/a/{BOOKSHOP_ID}/{bookshop_id}"
    slug = title.lower().replace(" ", "-")[:50]
    affiliate = f"/a/{BOOKSHOP_ID}" if BOOKSHOP_ID else ""
    return f"https://bookshop.org{affiliate}/search?keywords={quote_plus(title)}"


def audible_url(asin: str | None = None) -> str | None:
    if asin:
        return f"https://www.audible.com/pd/{asin}?tag={AUDIBLE_TAG}"
    return None


async def attach_affiliate_links(state: AgentState) -> AgentState:
    """Attach affiliate URLs to every final recommendation"""
    for book in state.final_recommendations:
        if isinstance(book, dict):
            title  = book.get("title", "")
            author = book.get("author", "")
            asin   = book.get("amazon_asin")
            isbn   = book.get("isbn_13") or book.get("isbn_10")
            book["amazon_url"]   = amazon_url(title, author, asin, isbn)
            book["bookshop_url"] = bookshop_url(title, book.get("bookshop_id"))
            book["audible_url"]  = audible_url(book.get("audible_asin"))
        else:
            book.amazon_url   = amazon_url(book.title, book.author,
                                           getattr(book, 'amazon_asin', None))
            book.bookshop_url = bookshop_url(book.title,
                                             getattr(book, 'bookshop_id', None))
            book.audible_url  = audible_url(getattr(book, 'audible_asin', None))

    state.pipeline_steps.append("affiliate_links: attached")
    return state
