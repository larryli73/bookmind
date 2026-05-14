"""
Fix bad book data that's polluting SEO pages.

Problems found:
- Adult books incorrectly flagged as is_children_book = TRUE
- Academic/reference books with wrong age ranges
- Books with wrong learning_goals

Run: python scripts/fix_seo_data.py
"""
import asyncio
import asyncpg
import os

DB_URL = os.getenv("DATABASE_URL", "").replace("postgresql+asyncpg://", "postgresql://").replace("postgres://", "postgresql://")

# Books that should NOT be children's books
NOT_CHILDREN = [
    "The Crush",                        # Sandra Brown adult romance
    "The settler's cookbook",           # Cookbook
    "The Evolution of Cognition",       # Academic
    "A guide to historical fiction",    # Academic/reference
    "The American Culture of War",      # Academic
    "Plum Spooky",                      # Adult mystery (Janet Evanovich)
    "Toll the hounds",                  # Adult fantasy
    "BILD am Sonntag Mega-Thriller 2019",
    "The American Trilogy",
    "Don't You Cry",
    "Reamde",
    "The Stand",
]

# Books with wrong age ranges (title → correct age_min, age_max)
FIX_AGE_RANGES = {
    # "The Giver of Stars" is adult fiction, not children's
    "The Giver of Stars": None,  # None = mark as not children's book
    # "The God of Small Things" is adult literary fiction
    "The God of Small Things": None,
}


async def main():
    conn = await asyncpg.connect(DB_URL)
    try:
        # 1. Fix books incorrectly marked as children's
        for title in NOT_CHILDREN:
            result = await conn.execute(
                "UPDATE books SET is_children_book = FALSE WHERE title ILIKE $1 AND is_children_book = TRUE",
                f"%{title}%"
            )
            print(f"Fixed '{title}': {result}")

        # 2. Fix specific books by title
        for title, ages in FIX_AGE_RANGES.items():
            if ages is None:
                result = await conn.execute(
                    "UPDATE books SET is_children_book = FALSE WHERE title ILIKE $1",
                    f"%{title}%"
                )
            else:
                result = await conn.execute(
                    "UPDATE books SET age_min = $1, age_max = $2 WHERE title ILIKE $3",
                    ages[0], ages[1], f"%{title}%"
                )
            print(f"Fixed '{title}': {result}")

        # 3. Audit: show remaining children's books with suspicious data
        print("\n--- Audit: Children's books with no learning_goals ---")
        rows = await conn.fetch("""
            SELECT title, author, age_min, age_max, learning_goals
            FROM books
            WHERE is_children_book = TRUE
            AND (learning_goals IS NULL OR learning_goals::text = '[]' OR learning_goals::text = 'null')
            LIMIT 20
        """)
        for r in rows:
            print(f"  {r['title']} by {r['author']} (ages {r['age_min']}-{r['age_max']})")

        print(f"\n--- Total children's books ---")
        count = await conn.fetchval("SELECT COUNT(*) FROM books WHERE is_children_book = TRUE")
        print(f"  {count} children's books")

        print("\n--- Sample kindness books after fix ---")
        rows = await conn.fetch("""
            SELECT title, author, age_min, age_max
            FROM books
            WHERE is_children_book = TRUE
            AND learning_goals::text LIKE '%kindness%'
            LIMIT 10
        """)
        for r in rows:
            print(f"  {r['title']} by {r['author']} (ages {r['age_min']}-{r['age_max']})")

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
