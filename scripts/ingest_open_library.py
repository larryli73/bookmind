"""
Automated Open Library ingestion with strict Claude quality gate.
Pulls children's books by subject, validates each with Claude Haiku
before inserting. Skips anything already in the DB.

Run: ANTHROPIC_API_KEY="sk-..." python scripts/ingest_open_library.py
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

VALID_GOALS = [
    "kindness", "courage", "friendship", "emotions", "science",
    "history", "diversity", "resilience", "problem_solving",
    "environment", "family", "creativity"
]

# Open Library subject searches — specific enough to be mostly children's
SEARCH_QUERIES = [
    # By subject
    ("Juvenile fiction", 3, 14),
    ("Children's stories", 3, 12),
    ("Picture books", 2, 7),
    ("Easy readers", 4, 8),
    ("Children's poetry", 4, 12),
    ("Fairy tales", 4, 10),
    ("Folklore", 5, 12),
    ("Animals fiction children", 4, 12),
    ("Adventure stories juvenile", 8, 14),
    ("Historical fiction juvenile", 8, 14),
    ("Fantasy fiction children", 8, 14),
    ("Mystery fiction juvenile", 8, 14),
    ("Science fiction juvenile", 8, 14),
    ("School stories children", 6, 12),
    ("Family life fiction juvenile", 4, 12),
    ("Friendship fiction juvenile", 4, 12),
    ("Nature children nonfiction", 5, 12),
    ("Biography juvenile", 8, 14),
    ("African American children fiction", 5, 14),
    ("Immigrants fiction children", 6, 14),
]

# Hard filters — if any of these appear in title, skip without Claude
TITLE_BLACKLIST = [
    "study guide", "teacher guide", "teacher's guide", "literature guide",
    "test prep", "workbook", "worksheet", "curriculum",
    "holy bible", "bible stories", "testament",
    "cookbook", "recipe", "guide to cooking",
    "investing", "finance", "business",
    "pregnancy", "divorce", "addiction",
    "erotica", "romance novel",
    "anthology vol", "complete works",
    "cliff notes", "sparknotes",
]

# Must have at least this many pages (filters out pamphlets, board books without content)
MIN_PAGES = 16
MAX_PAGES = 800


async def search_open_library(client: httpx.AsyncClient, subject: str, offset: int = 0, limit: int = 100):
    try:
        r = await client.get(
            "https://openlibrary.org/search.json",
            params={
                "subject": subject,
                "fields": "key,title,author_name,isbn,cover_i,first_publish_year,number_of_pages_median,subject,edition_count",
                "limit": limit,
                "offset": offset,
                "language": "eng",
            },
            timeout=20.0
        )
        r.raise_for_status()
        return r.json().get("docs", [])
    except Exception as e:
        print(f"    Search error: {e}")
        return []


def passes_hard_filter(doc: dict) -> bool:
    title = (doc.get("title") or "").lower()
    pages = doc.get("number_of_pages_median") or 0
    editions = doc.get("edition_count") or 0

    # Title blacklist
    for bad in TITLE_BLACKLIST:
        if bad in title:
            return False

    # Skip books with no ISBN (can't reliably dedup)
    isbn_list = doc.get("isbn") or []
    if not isbn_list:
        return False

    # Skip unpopular obscure editions (proxy for quality)
    if editions < 2:
        return False

    # Page count sanity
    if pages and (pages < MIN_PAGES or pages > MAX_PAGES):
        return False

    return True


async def claude_validate_batch(client, books: list) -> list:
    """
    Ask Claude Haiku to validate a batch of books.
    Returns list of dicts with: is_children_book, age_min, age_max, learning_goals, reason
    """
    if not books:
        return []

    items = []
    for i, b in enumerate(books):
        subjects = ", ".join((b.get("subject") or [])[:6])
        items.append(
            f'{i+1}. Title: "{b["title"]}" | Author: {b.get("author", "Unknown")} | '
            f'Pages: {b.get("pages", "?")} | Subjects: {subjects}'
        )

    prompt = f"""You are a children's librarian. Evaluate each book below.

For each book decide:
1. Is it a genuine children's book a parent would want to recommend? (not a study guide, adult novel, textbook, religious tract, or obscure reprint)
2. If yes: what age range fits (age_min, age_max between 2-16)?
3. If yes: pick 1-4 learning goals from: kindness, courage, friendship, emotions, science, history, diversity, resilience, problem_solving, environment, family, creativity

Books:
{chr(10).join(items)}

Reply with ONLY a JSON array, one object per book, same order:
[
  {{"ok": true, "age_min": 8, "age_max": 12, "goals": ["courage", "friendship"]}},
  {{"ok": false}},
  ...
]

Be strict. When in doubt, set ok=false. Study guides, teacher editions, religious books, adult books = false."""

    try:
        from anthropic import AsyncAnthropic
        ac = AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
        msg = await ac.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}]
        )
        text = msg.content[0].text.strip()
        m = re.search(r'\[.*\]', text, re.DOTALL)
        if m:
            results = json.loads(m.group())
            if isinstance(results, list) and len(results) == len(books):
                return results
    except Exception as e:
        print(f"    Claude error: {e}")

    return [{"ok": False}] * len(books)


async def generate_description(client, title: str, author: str, age_min: int, age_max: int) -> str:
    prompt = f'Write a 2-sentence description of the children\'s book "{title}" by {author} (ages {age_min}-{age_max}). Focus on plot and themes. Be specific.'
    try:
        from anthropic import AsyncAnthropic
        ac = AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
        msg = await ac.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=150,
            messages=[{"role": "user", "content": prompt}]
        )
        return msg.content[0].text.strip()
    except Exception:
        return ""


async def get_existing_titles(conn) -> set:
    rows = await conn.fetch("SELECT LOWER(title) FROM books WHERE is_children_book = TRUE")
    return {r[0] for r in rows}


async def main():
    conn = await asyncpg.connect(DB_URL)
    before = await conn.fetchval("SELECT COUNT(*) FROM books WHERE is_children_book = TRUE")
    print(f"BookMind Open Library Ingestion (strict Claude gate)")
    print(f"Starting books: {before}\n")

    existing_titles = await get_existing_titles(conn)
    print(f"Existing titles to skip: {len(existing_titles)}\n")

    total_seen = total_passed_hard = total_passed_claude = total_inserted = 0
    VALIDATE_BATCH = 15  # books per Claude call

    async with httpx.AsyncClient() as http:
        for subject, default_age_min, default_age_max in SEARCH_QUERIES:
            print(f"\n── Subject: '{subject}' ──────────────────")
            subject_inserted = 0

            # Fetch up to 3 pages (300 books) per subject
            for page in range(3):
                docs = await search_open_library(http, subject, offset=page * 100, limit=100)
                if not docs:
                    break

                # Hard filter + dedup
                candidates = []
                for doc in docs:
                    total_seen += 1
                    title = doc.get("title", "")
                    if not title:
                        continue
                    if title.lower() in existing_titles:
                        continue
                    if not passes_hard_filter(doc):
                        continue

                    isbn_list = doc.get("isbn") or []
                    isbn_13 = next((x for x in isbn_list if len(x) == 13), None)
                    isbn_10 = next((x for x in isbn_list if len(x) == 10), None)

                    candidates.append({
                        "title": title,
                        "author": (doc.get("author_name") or ["Unknown"])[0],
                        "isbn_13": isbn_13,
                        "isbn_10": isbn_10,
                        "cover_i": doc.get("cover_i"),
                        "published_year": doc.get("first_publish_year"),
                        "pages": doc.get("number_of_pages_median"),
                        "subject": doc.get("subject") or [],
                        "default_age_min": default_age_min,
                        "default_age_max": default_age_max,
                    })

                total_passed_hard += len(candidates)

                if not candidates:
                    continue

                # Claude validation in batches
                for i in range(0, len(candidates), VALIDATE_BATCH):
                    batch = candidates[i:i + VALIDATE_BATCH]
                    verdicts = await claude_validate_batch(None, batch)
                    await asyncio.sleep(0.2)

                    for book, verdict in zip(batch, verdicts):
                        if not verdict.get("ok"):
                            continue

                        total_passed_claude += 1
                        age_min = verdict.get("age_min", book["default_age_min"])
                        age_max = verdict.get("age_max", book["default_age_max"])
                        goals = [g for g in verdict.get("goals", []) if g in VALID_GOALS]
                        if not goals:
                            continue

                        # Generate description
                        desc = await generate_description(
                            None, book["title"], book["author"], age_min, age_max
                        )
                        await asyncio.sleep(0.1)

                        cover_url = (
                            f"https://covers.openlibrary.org/b/id/{book['cover_i']}-L.jpg"
                            if book["cover_i"] else None
                        )

                        try:
                            result = await conn.fetchval("""
                                INSERT INTO books (
                                    title, author, age_min, age_max,
                                    cover_url, description, page_count,
                                    published_year, isbn_13, isbn_10,
                                    learning_goals, is_children_book, awards,
                                    is_series, has_violence, has_scary_content,
                                    has_adult_themes, language
                                ) VALUES (
                                    $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,
                                    $11::jsonb, TRUE, '[]'::jsonb,
                                    FALSE, FALSE, FALSE, FALSE, 'en'
                                )
                                ON CONFLICT DO NOTHING
                                RETURNING id
                            """,
                                book["title"], book["author"], age_min, age_max,
                                cover_url, desc, book["pages"],
                                book["published_year"], book["isbn_13"], book["isbn_10"],
                                json.dumps(goals)
                            )
                            if result:
                                total_inserted += 1
                                subject_inserted += 1
                                existing_titles.add(book["title"].lower())
                                if total_inserted % 25 == 0:
                                    current = await conn.fetchval(
                                        "SELECT COUNT(*) FROM books WHERE is_children_book=TRUE")
                                    print(f"  [{total_inserted} inserted so far | DB total: {current}]")
                        except Exception as e:
                            pass

                await asyncio.sleep(0.3)  # Open Library rate limit

            print(f"  Inserted for '{subject}': {subject_inserted}")

    after = await conn.fetchval("SELECT COUNT(*) FROM books WHERE is_children_book = TRUE")
    await conn.close()

    print(f"\n{'='*55}")
    print(f"DONE")
    print(f"  Total scanned:        {total_seen}")
    print(f"  Passed hard filter:   {total_passed_hard}")
    print(f"  Passed Claude gate:   {total_passed_claude}")
    print(f"  Inserted:             {total_inserted}")
    print(f"  Children's books: {before} → {after} (+{after - before})")


if __name__ == "__main__":
    asyncio.run(main())
