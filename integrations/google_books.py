"""
Google Books API integration — richer descriptions and metadata
Docs: https://developers.google.com/books
"""
from __future__ import annotations
import httpx
import os
from typing import Optional

API_KEY  = os.getenv("GOOGLE_BOOKS_API_KEY", "")
BASE_URL = "https://www.googleapis.com/books/v1"


async def search_books(query: str, max_results: int = 10) -> list[dict]:
    async with httpx.AsyncClient() as client:
        params = {"q": query, "maxResults": max_results, "printType": "books"}
        if API_KEY:
            params["key"] = API_KEY
        response = await client.get(f"{BASE_URL}/volumes", params=params, timeout=10.0)
        response.raise_for_status()
        return response.json().get("items", [])


async def get_book_by_isbn(isbn: str) -> Optional[dict]:
    async with httpx.AsyncClient() as client:
        params = {"q": f"isbn:{isbn}"}
        if API_KEY:
            params["key"] = API_KEY
        response = await client.get(f"{BASE_URL}/volumes", params=params, timeout=10.0)
        response.raise_for_status()
        items = response.json().get("items", [])
        return items[0] if items else None


def normalize_book(raw: dict) -> dict:
    info = raw.get("volumeInfo", {})
    idents = {i["type"]: i["identifier"] for i in info.get("industryIdentifiers", [])}
    return {
        "title":           info.get("title", ""),
        "subtitle":        info.get("subtitle"),
        "author":          (info.get("authors") or ["Unknown"])[0],
        "authors":         info.get("authors", []),
        "google_books_id": raw.get("id"),
        "isbn_13":         idents.get("ISBN_13"),
        "isbn_10":         idents.get("ISBN_10"),
        "publisher":       info.get("publisher"),
        "published_year":  int(info.get("publishedDate", "0")[:4]) if info.get("publishedDate") else None,
        "page_count":      info.get("pageCount"),
        "description":     info.get("description"),
        "genres":          info.get("categories", []),
        "language":        info.get("language", "en"),
        "cover_url":       info.get("imageLinks", {}).get("thumbnail"),
        "goodreads_rating": info.get("averageRating"),
        "goodreads_count": info.get("ratingsCount"),
    }
