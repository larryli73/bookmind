"""
Book ingestion script with rate limiting for Voyage AI free tier.
Usage:
    python -m scripts.ingest_books --query "mystery thriller" --limit 100
"""
import asyncio, argparse, os, hashlib, math, httpx
from sqlalchemy.ext.asyncio import AsyncSession
from db.session import AsyncSessionLocal, engine
from db.models import Base, Book
from sqlalchemy import select

OPEN_LIBRARY_URL = "https://openlibrary.org"
VOYAGE_API_KEY   = os.getenv("VOYAGE_API_KEY", "")
VOYAGE_MODEL     = "voyage-3"
DIMS             = 1536
DELAY_SECONDS    = 0.5  # Wait between each embedding call


async def get_embedding(text: str) -> list[float]:
    if VOYAGE_API_KEY:
        for attempt in range(3):  # Retry up to 3 times
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        "https://api.voyageai.com/v1/embeddings",
                        headers={"Authorization": f"Bearer {VOYAGE_API_KEY}", "Content-Type": "application/json"},
                        json={"model": VOYAGE_MODEL, "input": text[:4000]},
                        timeout=30.0,
                    )
                    response.raise_for_status()
                    data = response.json()
                    emb = data["data"][0]["embedding"]
                    if len(emb) < DIMS:
                        emb = emb + [0.0] * (DIMS - len(emb))
                    return emb[:DIMS]
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    wait = (attempt + 1) * 2  # 2s, 4s, 6s backoff
                    print(f"    ⏳ Rate limited — waiting {wait}s...")
                    await asyncio.sleep(wait)
                else:
                    raise
        raise Exception("Failed after 3 retries")
    else:
        vector = []
        for i in range(DIMS):
            seed = hashlib.md5(f"{text}{i}".encode()).hexdigest()
            val = int(seed[:8], 16) / (16**8)
            vector.append(val * 2 - 1)
        magnitude = math.sqrt(sum(x**2 for x in vector))
        return [x / magnitude for x in vector]


async def search_open_library(query: str, limit: int) -> list[dict]:
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{OPEN_LIBRARY_URL}/search.json",
            params={"q": query, "limit": limit,
                    "fields": "key,title,author_name,isbn,cover_i,first_publish_year,subject,number_of_pages_median"},
            timeout=15.0)
        response.raise_for_status()
        return response.json().get("docs", [])


async def ingest_book(session: AsyncSession, raw: dict) -> bool:
    isbn_list = raw.get("isbn") or []
    isbn_13 = next((i for i in isbn_list if len(i) == 13), None)
    isbn_10 = next((i for i in isbn_list if len(i) == 10), None)
    if not isbn_13 and not isbn_10:
        return False
    if isbn_13:
        existing = await session.execute(select(Book).where(Book.isbn_13 == isbn_13))
        if existing.scalar_one_or_none():
            return False
    text = f"Title: {raw.get('title','')}\nAuthor: {', '.join(raw.get('author_name') or ['Unknown'])}\nSubjects: {', '.join((raw.get('subject') or [])[:8])}"
    embedding = await get_embedding(text)
    await asyncio.sleep(DELAY_SECONDS)  # Rate limit buffer
    cover_id = raw.get("cover_i")
    book = Book(
        isbn_13=isbn_13, isbn_10=isbn_10,
        title=raw.get("title", "Unknown"),
        author=(raw.get("author_name") or ["Unknown"])[0],
        authors=raw.get("author_name"),
        published_year=raw.get("first_publish_year"),
        page_count=raw.get("number_of_pages_median"),
        genres=raw.get("subject", [])[:10],
        cover_url=f"https://covers.openlibrary.org/b/id/{cover_id}-L.jpg" if cover_id else None,
        embedding=embedding,
    )
    session.add(book)
    return True


async def main(query: str, limit: int):
    if VOYAGE_API_KEY:
        print("✅ Using Voyage AI embeddings (semantic search enabled)")
        print(f"⏱  Rate limiting: {DELAY_SECONDS}s delay between requests")
    else:
        print("⚠️  No VOYAGE_API_KEY — using hash embeddings")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    print(f"🔍 Searching for: {query!r} (limit={limit})")
    raw_books = await search_open_library(query, limit)
    print(f"📚 Found {len(raw_books)} books — embedding and storing...")

    async with AsyncSessionLocal() as session:
        ingested = 0
        for i, raw in enumerate(raw_books):
            try:
                ok = await ingest_book(session, raw)
                if ok:
                    ingested += 1
                    print(f"  ✅ [{i+1}/{len(raw_books)}] {raw.get('title')}")
                else:
                    print(f"  ⏭  [{i+1}/{len(raw_books)}] Skipped: {raw.get('title')}")
            except Exception as e:
                print(f"  ❌ [{i+1}/{len(raw_books)}] Error: {e}")
                await session.rollback()
                continue
            if (i+1) % 10 == 0:
                await session.commit()
        await session.commit()
    print(f"\n✅ Done! Ingested {ingested} new books.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", default="bestseller fiction")
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args()
    asyncio.run(main(args.query, args.limit))
