"""
Book ingestion script — fast version for paid Voyage AI plan
Uses raw asyncpg to bypass ORM dimension issues
"""
import asyncio, argparse, os, hashlib, math, httpx, json
import asyncpg

OPEN_LIBRARY_URL = "https://openlibrary.org"
VOYAGE_API_KEY   = os.getenv("VOYAGE_API_KEY", "")
VOYAGE_MODEL     = "voyage-3"
DIMS             = 1024
BATCH_SIZE       = 10  # embed 10 at a time for speed


def get_pg_url():
    url = os.getenv("DATABASE_URL", "")
    url = url.replace("postgresql+asyncpg://", "postgresql://")
    url = url.replace("postgres://", "postgresql://")
    return url


async def get_embeddings_batch(texts: list[str]) -> list[list[float]]:
    """Embed multiple texts in one API call — much faster"""
    if VOYAGE_API_KEY:
        for attempt in range(3):
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        "https://api.voyageai.com/v1/embeddings",
                        headers={"Authorization": f"Bearer {VOYAGE_API_KEY}",
                                "Content-Type": "application/json"},
                        json={"model": VOYAGE_MODEL, "input": texts},
                        timeout=60.0,
                    )
                    response.raise_for_status()
                    data = response.json()
                    return [item["embedding"][:DIMS] for item in data["data"]]
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    wait = (attempt + 1) * 3
                    print(f"    ⏳ Rate limited — waiting {wait}s...")
                    await asyncio.sleep(wait)
                else:
                    raise
        raise Exception("Failed after 3 retries")
    else:
        results = []
        for text in texts:
            vector = []
            for i in range(DIMS):
                seed = hashlib.md5(f"{text}{i}".encode()).hexdigest()
                val = int(seed[:8], 16) / (16**8)
                vector.append(val * 2 - 1)
            magnitude = math.sqrt(sum(x**2 for x in vector))
            results.append([x / magnitude for x in vector])
        return results


async def search_open_library(query: str, limit: int) -> list[dict]:
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{OPEN_LIBRARY_URL}/search.json",
            params={"q": query, "limit": limit,
                    "fields": "key,title,author_name,isbn,cover_i,first_publish_year,subject,number_of_pages_median"},
            timeout=20.0)
        response.raise_for_status()
        return response.json().get("docs", [])


async def main(query: str, limit: int):
    if VOYAGE_API_KEY:
        print(f"✅ Using Voyage AI embeddings (batch mode)")
    else:
        print("⚠️  No VOYAGE_API_KEY — using hash embeddings")

    pg_url = get_pg_url()
    conn = await asyncpg.connect(pg_url)
    await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS books_simple (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            isbn_13 VARCHAR(13) UNIQUE,
            isbn_10 VARCHAR(10) UNIQUE,
            title VARCHAR(500) NOT NULL,
            author VARCHAR(300) NOT NULL,
            published_year INTEGER,
            page_count INTEGER,
            genres JSONB,
            cover_url VARCHAR(1000),
            embedding vector(1024),
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    print(f"🔍 Searching for: {query!r} (limit={limit})")
    raw_books = await search_open_library(query, limit)
    print(f"📚 Found {len(raw_books)} books — filtering existing...")

    # Filter out books without ISBNs and already existing ones
    to_process = []
    for raw in raw_books:
        isbn_list = raw.get("isbn") or []
        isbn_13 = next((x for x in isbn_list if len(x) == 13), None)
        isbn_10 = next((x for x in isbn_list if len(x) == 10), None)
        if not isbn_13 and not isbn_10:
            continue
        existing = await conn.fetchrow(
            "SELECT id FROM books_simple WHERE isbn_13=$1 OR isbn_10=$2",
            isbn_13, isbn_10
        )
        if not existing:
            to_process.append((raw, isbn_13, isbn_10))

    print(f"📖 {len(to_process)} new books to embed and store...")

    ingested = 0
    # Process in batches
    for batch_start in range(0, len(to_process), BATCH_SIZE):
        batch = to_process[batch_start:batch_start + BATCH_SIZE]
        texts = []
        for raw, _, _ in batch:
            text = f"Title: {raw.get('title','')}\nAuthor: {', '.join(raw.get('author_name') or ['Unknown'])}\nSubjects: {', '.join((raw.get('subject') or [])[:8])}"
            texts.append(text)

        try:
            embeddings = await get_embeddings_batch(texts)
        except Exception as e:
            print(f"  ❌ Batch embedding failed: {e}")
            continue

        for (raw, isbn_13, isbn_10), embedding in zip(batch, embeddings):
            try:
                cover_id = raw.get("cover_i")
                await conn.execute("""
                    INSERT INTO books_simple (isbn_13, isbn_10, title, author, published_year, page_count, genres, cover_url, embedding)
                    VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8, $9::vector)
                    ON CONFLICT DO NOTHING
                """,
                    isbn_13, isbn_10,
                    raw.get("title", "Unknown"),
                    (raw.get("author_name") or ["Unknown"])[0],
                    raw.get("first_publish_year"),
                    raw.get("number_of_pages_median"),
                    json.dumps(raw.get("subject", [])[:10]),
                    f"https://covers.openlibrary.org/b/id/{cover_id}-L.jpg" if cover_id else None,
                    str(embedding)
                )
                ingested += 1
                print(f"  ✅ [{batch_start + ingested}/{len(to_process)}] {raw.get('title')}")
            except Exception as e:
                print(f"  ❌ Error: {e}")

    await conn.close()

    # Auto-copy to books table
    conn2 = await asyncpg.connect(pg_url)
    result = await conn2.execute("""
        INSERT INTO books (id, isbn_13, isbn_10, title, author, published_year, page_count, genres, cover_url, embedding, language, is_series, has_violence, has_scary_content, has_adult_themes)
        SELECT id, isbn_13, isbn_10, title, author, published_year, page_count, genres::json, cover_url, embedding, 'en', false, false, false, false
        FROM books_simple
        WHERE id NOT IN (SELECT id FROM books)
        ON CONFLICT DO NOTHING
    """)
    count = await conn2.fetchval("SELECT COUNT(*) FROM books")
    await conn2.close()

    print(f"\n✅ Done! Ingested {ingested} new books.")
    print(f"📊 Total books in database: {count}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", default="bestseller fiction")
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    asyncio.run(main(args.query, args.limit))
