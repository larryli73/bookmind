"""
Open Library API integration — free book metadata source
Docs: https://openlibrary.org/developers/api
"""
from __future__ import annotations
import httpx
from typing import Optional


BASE_URL = "https://openlibrary.org"


async def search_books(query: str, limit: int = 10) -> list[dict]:
    """Search Open Library for books"""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{BASE_URL}/search.json",
            params={"q": query, "limit": limit, "fields": "key,title,author_name,isbn,cover_i,first_publish_year,subject,number_of_pages_median"},
            timeout=10.0
        )
        response.raise_for_status()
        data = response.json()
        return data.get("docs", [])


async def get_book_by_isbn(isbn: str) -> Optional[dict]:
    """Get full book details by ISBN"""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{BASE_URL}/api/books",
            params={"bibkeys": f"ISBN:{isbn}", "format": "json", "jscmd": "data"},
            timeout=10.0
        )
        response.raise_for_status()
        data = response.json()
        key = f"ISBN:{isbn}"
        return data.get(key)


def normalize_book(raw: dict) -> dict:
    """Normalize Open Library book data to our schema"""
    isbn_list = raw.get("isbn", [])
    return {
        "title":          raw.get("title", ""),
        "author":         (raw.get("author_name") or ["Unknown"])[0],
        "authors":        raw.get("author_name", []),
        "isbn_13":        next((i for i in isbn_list if len(i) == 13), None),
        "isbn_10":        next((i for i in isbn_list if len(i) == 10), None),
        "open_library_id": raw.get("key", "").replace("/works/", ""),
        "published_year": raw.get("first_publish_year"),
        "page_count":     raw.get("number_of_pages_median"),
        "genres":         raw.get("subject", [])[:10],
        "cover_url":      f"https://covers.openlibrary.org/b/id/{raw['cover_i']}-L.jpg" if raw.get("cover_i") else None,
    }
