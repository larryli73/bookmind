"""
Nightly book sync worker — keeps the book catalog fresh
Runs as an ARQ background job
"""
import asyncio
from integrations.open_library import search_books, normalize_book
from scripts.ingest_books import ingest_book
from db.session import AsyncSessionLocal

DAILY_QUERIES = [
    "bestseller fiction 2024",
    "bestseller nonfiction 2024",
    "children books award winner",
    "middle grade fantasy",
    "young adult romance",
    "science nonfiction popular",
    "picture books caldecott",
    "new releases 2025",
]


async def sync_books(ctx):
    """ARQ job: run nightly to ingest fresh books"""
    print("Starting nightly book sync...")
    total = 0
    async with AsyncSessionLocal() as session:
        for query in DAILY_QUERIES:
            raw = await search_books(query, limit=50)
            for r in raw:
                ok = await ingest_book(session, normalize_book(r))
                if ok:
                    total += 1
        await session.commit()
    print(f"Sync complete — {total} new books ingested")
    return total


class WorkerSettings:
    functions  = [sync_books]
    cron_jobs  = []
    queue_name = "bookmind:book_sync"
