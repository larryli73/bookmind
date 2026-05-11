"""
BookMind Auto-Ingestion Bot
Runs automatically on a schedule — no human needed!

Usage:
    python -m scripts.auto_ingest                    # Run once
    python -m scripts.auto_ingest --continuous       # Run forever every 6 hours
    python -m scripts.auto_ingest --batch 500        # Ingest 500 books per run
"""
import asyncio
import argparse
import os
import json
import hashlib
import math
import httpx
import asyncpg
from datetime import datetime

# ─── ALL QUERIES TO CYCLE THROUGH ────────────────────────────────────────────
QUERY_LIST = [
    # Romance
    "Julia Quinn Bridgerton Regency romance",
    "Sarah MacLean Regency romance",
    "Tessa Dare Regency romance",
    "Eloisa James historical romance duchess",
    "Lisa Kleypas historical romance Wallflowers",
    "Courtney Milan historical romance",
    "Mimi Matthews Regency romance Victorian",
    "Colleen Hoover romance contemporary",
    "Emily Henry beach read romance",
    "Ali Hazelwood STEM romance",
    "Helen Hoang Kiss Quotient romance",
    "Talia Hibbert romance diverse",
    "Kennedy Ryan romance contemporary",
    "Ana Huang Twisted romance dark",
    
    # Thriller/Mystery
    "Gillian Flynn Gone Girl Dark Places",
    "Paula Hawkins Girl on the Train",
    "Ruth Ware thriller mystery locked room",
    "Lucy Foley Guest List thriller",
    "Karin Slaughter Will Trent thriller",
    "Michael Connelly Harry Bosch detective",
    "Tana French Dublin Murder Squad",
    "Louise Penny Chief Inspector Gamache",
    "Anthony Horowitz Magpie Murders",
    "Richard Osman Thursday Murder Club",
    
    # Fantasy/Sci-Fi
    "Brandon Sanderson Stormlight Archive",
    "Robert Jordan Wheel of Time",
    "Patrick Rothfuss Kingkiller Chronicle",
    "Joe Abercrombie First Law grimdark",
    "N K Jemisin Fifth Season Broken Earth",
    "Robin Hobb Farseer Trilogy",
    "Andy Weir Project Hail Mary",
    "Liu Cixin Three Body Problem",
    "Ted Chiang Exhalation stories",
    "Ursula Le Guin Earthsea fantasy",
    
    # Literary Fiction
    "Hanya Yanagihara Little Life",
    "Sally Rooney Normal People",
    "Kazuo Ishiguro Remains Day",
    "Colson Whitehead Underground Railroad",
    "Yaa Gyasi Homegoing Ghana",
    "Madeline Miller Circe Song Achilles",
    "Anthony Doerr All Light Cannot See",
    "Amor Towles Gentleman Moscow",
    "Fredrik Backman Anxious People",
    "Matt Haig Midnight Library",
    
    # Nonfiction
    "James Clear Atomic Habits productivity",
    "Malcolm Gladwell Outliers Tipping Point",
    "Daniel Kahneman Thinking Fast Slow",
    "Brene Brown Daring Greatly vulnerability",
    "Ryan Holiday Obstacle is the Way Stoicism",
    "Adam Grant Think Again organizational",
    "Walter Isaacson Steve Jobs biography",
    "Erik Larson Devil White City narrative",
    "David Grann Killers Flower Moon",
    "Michael Lewis Moneyball Flash Boys",
    
    # Young Adult
    "John Green Fault in Stars",
    "Rainbow Rowell Fangirl Eleanor Park",
    "Angie Thomas Hate U Give",
    "Jason Reynolds Long Way Down",
    "Becky Albertalli Simon vs Agenda",
    "Adam Silvera They Both Die End",
    "Leigh Bardugo Six of Crows Grishaverse",
    "Holly Black Cruel Prince Folk Air",
    "Maggie Stiefvater Raven Boys",
    "Victoria Schwab Shades Magic",
    
    # Children
    "Rick Riordan Percy Jackson Greek gods",
    "Jeff Kinney Diary Wimpy Kid",
    "Dav Pilkey Dog Man Captain Underpants",
    "Roald Dahl Charlie Chocolate Factory",
    "Lemony Snicket Series Unfortunate Events",
    "Philip Pullman His Dark Materials",
    "Cornelia Funke Inkheart Dragon Rider",
    "Christopher Paolini Eragon Inheritance",
    "Gordon Korman Swindle Island adventure",
    "Anthony Horowitz Alex Rider spy",
]

VOYAGE_API_KEY = os.getenv("VOYAGE_API_KEY", "")
VOYAGE_MODEL   = "voyage-3"
DIMS           = 1024
BATCH_SIZE     = 10


def get_pg_url():
    url = os.getenv("DATABASE_URL", "")
    url = url.replace("postgresql+asyncpg://", "postgresql://")
    url = url.replace("postgres://", "postgresql://")
    return url


async def get_embeddings_batch(texts: list[str]) -> list[list[float]]:
    if VOYAGE_API_KEY:
        for attempt in range(3):
            try:
                async with httpx.AsyncClient() as client:
                    r = await client.post(
                        "https://api.voyageai.com/v1/embeddings",
                        headers={"Authorization": f"Bearer {VOYAGE_API_KEY}",
                                "Content-Type": "application/json"},
                        json={"model": VOYAGE_MODEL, "input": texts},
                        timeout=60.0,
                    )
                    r.raise_for_status()
                    return [item["embedding"][:DIMS] for item in r.json()["data"]]
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    await asyncio.sleep((attempt + 1) * 3)
                else:
                    raise
    # Fallback hash embeddings
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
        r = await client.get(
            "https://openlibrary.org/search.json",
            params={"q": query, "limit": limit,
                    "fields": "key,title,author_name,isbn,cover_i,first_publish_year,subject,number_of_pages_median"},
            timeout=20.0)
        r.raise_for_status()
        return r.json().get("docs", [])


async def ingest_query(conn: asyncpg.Connection, query: str, limit: int) -> int:
    """Ingest books for a single query. Returns number of new books added."""
    try:
        raw_books = await search_open_library(query, limit)
    except Exception as e:
        print(f"    ⚠️  Search failed for '{query}': {e}")
        return 0

    # Filter books without ISBNs and already existing
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

    if not to_process:
        return 0

    ingested = 0
    for batch_start in range(0, len(to_process), BATCH_SIZE):
        batch = to_process[batch_start:batch_start + BATCH_SIZE]
        texts = []
        for raw, _, _ in batch:
            text = f"Title: {raw.get('title','')}\nAuthor: {', '.join(raw.get('author_name') or ['Unknown'])}\nSubjects: {', '.join((raw.get('subject') or [])[:8])}"
            texts.append(text)

        try:
            embeddings = await get_embeddings_batch(texts)
        except Exception as e:
            print(f"    ❌ Embedding failed: {e}")
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
            except Exception:
                continue

    return ingested


async def copy_to_books_table(conn: asyncpg.Connection) -> int:
    """Copy new books from staging to main books table"""
    result = await conn.execute("""
        INSERT INTO books (id, isbn_13, isbn_10, title, author, published_year, 
                          page_count, genres, cover_url, embedding, language, 
                          is_series, has_violence, has_scary_content, has_adult_themes)
        SELECT id, isbn_13, isbn_10, title, author, published_year, 
               page_count, genres::json, cover_url, embedding, 'en', 
               false, false, false, false
        FROM books_simple
        WHERE id NOT IN (SELECT id FROM books)
        ON CONFLICT DO NOTHING
    """)
    return int(result.split()[-1]) if result else 0


async def get_next_query(conn: asyncpg.Connection) -> str:
    """Get the next query to run — cycles through all queries"""
    # Track which queries we've run using a simple counter in DB
    try:
        row = await conn.fetchrow("SELECT value FROM ingest_state WHERE key='query_index'")
        idx = int(row['value']) if row else 0
    except Exception:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS ingest_state (
                key VARCHAR PRIMARY KEY,
                value TEXT
            )
        """)
        idx = 0

    query = QUERY_LIST[idx % len(QUERY_LIST)]
    next_idx = (idx + 1) % len(QUERY_LIST)
    
    await conn.execute("""
        INSERT INTO ingest_state (key, value) VALUES ('query_index', $1)
        ON CONFLICT (key) DO UPDATE SET value=$1
    """, str(next_idx))
    
    return query


async def run_once(books_per_run: int = 200):
    """Run one ingestion cycle"""
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

    # Figure out how many queries to run
    queries_to_run = max(1, books_per_run // 50)
    
    print(f"\n🤖 BookMind Auto-Ingest Bot")
    print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"📚 Running {queries_to_run} queries (~{books_per_run} books target)")
    print("─" * 50)
    
    total_new = 0
    for i in range(queries_to_run):
        query = await get_next_query(conn)
        print(f"\n🔍 [{i+1}/{queries_to_run}] '{query}'")
        new = await ingest_query(conn, query, 50)
        total_new += new
        print(f"    ✅ {new} new books added")
        await asyncio.sleep(1)  # Be nice to Open Library

    # Copy to main books table
    print(f"\n📋 Copying to books table...")
    copied = await copy_to_books_table(conn)
    
    total = await conn.fetchval("SELECT COUNT(*) FROM books")
    await conn.close()
    
    print(f"✅ Done! Added {total_new} new books → {total} total in database")
    print("─" * 50)
    return total_new


async def run_continuous(books_per_run: int, interval_hours: int = 6):
    """Run continuously every N hours"""
    print(f"🤖 BookMind Auto-Ingest Bot — Continuous Mode")
    print(f"⏰ Running every {interval_hours} hours")
    
    while True:
        await run_once(books_per_run)
        print(f"\n💤 Sleeping {interval_hours} hours until next run...")
        await asyncio.sleep(interval_hours * 3600)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BookMind Auto-Ingestion Bot")
    parser.add_argument("--continuous", action="store_true", 
                        help="Run continuously every 6 hours")
    parser.add_argument("--batch", type=int, default=200,
                        help="Books to ingest per run (default: 200)")
    parser.add_argument("--interval", type=int, default=6,
                        help="Hours between runs in continuous mode (default: 6)")
    args = parser.parse_args()

    if args.continuous:
        asyncio.run(run_continuous(args.batch, args.interval))
    else:
        asyncio.run(run_once(args.batch))
