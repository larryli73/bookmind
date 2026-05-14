"""
Enrich all children's books with:
  - Descriptions via Claude Haiku (knows all classic children's books)
  - Cover images via Open Library search (no quota limits)

Run: ANTHROPIC_API_KEY="sk-..." python scripts/enrich_descriptions.py
"""
import asyncio
import asyncpg
import httpx
import json
import os
import re

DB_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:eRrNwgeutWVANDhVskIKbCkOJXQhRIWn@viaduct.proxy.rlwy.net:33806/railway"
).replace("postgresql+asyncpg://", "postgresql://").replace("postgres://", "postgresql://")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
BATCH_SIZE = 20  # Claude Haiku descriptions per batch


async def fetch_open_library_cover(client: httpx.AsyncClient, title: str, author: str):
    try:
        r = await client.get(
            "https://openlibrary.org/search.json",
            params={"title": title, "author": author.split()[0], "fields": "cover_i,title", "limit": 3},
            timeout=10.0,
        )
        r.raise_for_status()
        docs = r.json().get("docs", [])
        for doc in docs:
            cover_i = doc.get("cover_i")
            if cover_i:
                return f"https://covers.openlibrary.org/b/id/{cover_i}-L.jpg"
    except Exception:
        pass
    return None


async def generate_descriptions_batch(client, books: list) -> list:
    """Ask Claude Haiku to write a 2-sentence description for each book in one call."""
    items = "\n".join(
        f'{i+1}. "{b["title"]}" by {b["author"]} (ages {b["age_min"]}-{b["age_max"]})'
        for i, b in enumerate(books)
    )
    prompt = f"""Write a short 2-sentence description for each children's book below.
Focus on plot/theme in a way that helps parents decide. Be specific, not generic.

{items}

Reply with ONLY a JSON array of strings (one description per book, same order).
Example: ["Wilbur the pig ...", "Young Pippi ..."]"""

    try:
        from anthropic import AsyncAnthropic
        ac = AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
        msg = await ac.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}]
        )
        text = msg.content[0].text.strip()
        m = re.search(r'\[.*\]', text, re.DOTALL)
        if m:
            descriptions = json.loads(m.group())
            if isinstance(descriptions, list) and len(descriptions) == len(books):
                return descriptions
    except Exception as e:
        print(f"    Claude error: {e}")
    return [""] * len(books)


async def main():
    conn = await asyncpg.connect(DB_URL)

    no_desc = await conn.fetch("""
        SELECT id, title, author, age_min, age_max
        FROM books
        WHERE is_children_book = TRUE
        AND (description IS NULL OR description = '')
        ORDER BY title
    """)
    no_cover = await conn.fetch("""
        SELECT id, title, author
        FROM books
        WHERE is_children_book = TRUE
        AND cover_url IS NULL
        ORDER BY title
    """)

    print(f"Books needing descriptions: {len(no_desc)}")
    print(f"Books needing covers:       {len(no_cover)}")
    print()

    # ── Step 1: Generate descriptions with Claude Haiku ──────────────────────
    if no_desc and ANTHROPIC_API_KEY:
        print(f"Generating descriptions in batches of {BATCH_SIZE}...")
        desc_updated = 0
        books_list = [dict(r) for r in no_desc]

        for i in range(0, len(books_list), BATCH_SIZE):
            batch = books_list[i:i + BATCH_SIZE]
            titles = [b["title"][:40] for b in batch]
            print(f"  Batch {i//BATCH_SIZE + 1}: {titles[0]} ... {titles[-1]}")

            descriptions = await generate_descriptions_batch(None, batch)

            for book, desc in zip(batch, descriptions):
                if desc and len(desc) > 20:
                    await conn.execute(
                        "UPDATE books SET description=$1 WHERE id=$2",
                        desc, book["id"]
                    )
                    desc_updated += 1

            await asyncio.sleep(0.3)  # rate limit buffer

        print(f"  ✅ Descriptions written: {desc_updated}\n")
    elif not ANTHROPIC_API_KEY:
        print("⚠️  No ANTHROPIC_API_KEY — skipping descriptions\n")

    # ── Step 2: Fetch covers from Open Library ────────────────────────────────
    if no_cover:
        print(f"Fetching covers from Open Library...")
        cover_updated = 0
        async with httpx.AsyncClient() as http:
            for i, row in enumerate(no_cover, 1):
                cover_url = await fetch_open_library_cover(http, row["title"], row["author"] or "")
                if cover_url:
                    await conn.execute(
                        "UPDATE books SET cover_url=$1 WHERE id=$2",
                        cover_url, row["id"]
                    )
                    cover_updated += 1
                if i % 20 == 0:
                    print(f"  [{i}/{len(no_cover)}] covers found so far: {cover_updated}")
                await asyncio.sleep(0.2)  # be nice to Open Library

        print(f"  ✅ Covers added: {cover_updated}\n")

    # ── Final stats ───────────────────────────────────────────────────────────
    total      = await conn.fetchval("SELECT COUNT(*) FROM books WHERE is_children_book=TRUE")
    with_cover = await conn.fetchval("SELECT COUNT(*) FROM books WHERE is_children_book=TRUE AND cover_url IS NOT NULL")
    with_desc  = await conn.fetchval("SELECT COUNT(*) FROM books WHERE is_children_book=TRUE AND description IS NOT NULL AND description != ''")

    await conn.close()

    print(f"=== FINAL STATE ===")
    print(f"  Total children's books:  {total}")
    print(f"  With cover image:        {with_cover} ({with_cover*100//total}%)")
    print(f"  With description:        {with_desc}  ({with_desc*100//total}%)")


if __name__ == "__main__":
    asyncio.run(main())
