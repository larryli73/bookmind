"""
Book enrichment script — adds ratings from Open Library ratings API
Free, no API key needed

Usage:
    python -m scripts.enrich_books --limit 500
"""
import asyncio, argparse, os, httpx
import asyncpg


def get_pg_url():
    url = os.getenv("DATABASE_URL", "")
    url = url.replace("postgresql+asyncpg://", "postgresql://")
    url = url.replace("postgres://", "postgresql://")
    return url


async def get_ratings(client: httpx.AsyncClient, isbn: str) -> dict:
    """Get ratings from Open Library using ISBN"""
    try:
        # Get the work key from ISBN
        r = await client.get(
            f"https://openlibrary.org/isbn/{isbn}.json",
            timeout=10.0
        )
        if r.status_code != 200:
            return {}
        
        data = r.json()
        work_key = None
        works = data.get("works", [])
        if works:
            work_key = works[0].get("key")  # e.g. /works/OL45804W
        
        if not work_key:
            return {}

        # Get ratings for the work
        r2 = await client.get(
            f"https://openlibrary.org{work_key}/ratings.json",
            timeout=10.0
        )
        if r2.status_code != 200:
            return {}
        
        ratings_data = r2.json()
        summary = ratings_data.get("summary", {})
        avg = summary.get("average")
        count = summary.get("count")

        if avg and count and count > 5:
            return {
                "goodreads_rating": round(avg, 2),
                "goodreads_count": count
            }
    except Exception:
        pass
    return {}


async def main(limit: int):
    pg_url = get_pg_url()
    conn = await asyncpg.connect(pg_url)

    books = await conn.fetch("""
        SELECT id, title, author, isbn_13, isbn_10
        FROM books
        WHERE goodreads_rating IS NULL
        AND (isbn_13 IS NOT NULL OR isbn_10 IS NOT NULL)
        ORDER BY RANDOM()
        LIMIT $1
    """, limit)

    print(f"📚 Enriching {len(books)} books with Open Library ratings...")
    enriched = 0

    async with httpx.AsyncClient() as client:
        for i, book in enumerate(books):
            isbn = book["isbn_13"] or book["isbn_10"]
            data = await get_ratings(client, isbn)

            if data.get("goodreads_rating"):
                await conn.execute(
                    "UPDATE books SET goodreads_rating=$1, goodreads_count=$2 WHERE id=$3",
                    data["goodreads_rating"], data["goodreads_count"], book["id"]
                )
                enriched += 1
                print(f"  ✅ [{i+1}/{len(books)}] {book['title'][:50]} — ⭐ {data['goodreads_rating']} ({data['goodreads_count']} ratings)")
            else:
                print(f"  ⏭  [{i+1}/{len(books)}] {book['title'][:50]}")

            await asyncio.sleep(0.5)

    await conn.close()
    print(f"\n✅ Done! Enriched {enriched}/{len(books)} books with ratings.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=200)
    args = parser.parse_args()
    asyncio.run(main(args.limit))
