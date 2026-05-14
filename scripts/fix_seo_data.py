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
    # Previously fixed
    "The Crush",
    "The settler's cookbook",
    "The Evolution of Cognition",
    "A guide to historical fiction",
    "The American Culture of War",
    "Plum Spooky",
    "Toll the hounds",
    "BILD am Sonntag Mega-Thriller 2019",
    "The American Trilogy",
    "Don't You Cry",
    "Reamde",
    "The Stand",
    "The Giver of Stars",
    "The God of Small Things",

    # Adult romance novels
    "Amazing Grace",                         # Danielle Steel
    "Because of Miss Bridgerton",            # Julia Quinn adult romance
    "Romancing Mister Bridgerton",           # Julia Quinn adult romance
    "Everything and the Moon",               # Julia Quinn adult romance
    "Saved by the Bear",                     # Paranormal romance for adults
    "Butter My Biscuit",                     # Adult western romance
    "Cat Came Back",                         # Adult mystery
    "Touch Not the Cat",                     # Adult mystery/romance
    "Storm Clouds Rolling In",               # Historical romance

    # Adult literary fiction
    "The Island of Sea Women",               # Lisa See adult fiction
    "Girls They Write Songs About",          # Adult literary fiction
    "Flush",                                 # Virginia Woolf adult fiction
    "The Scarlet Letter",                    # Adult classic literature

    # Adult mysteries/thrillers
    "In the Presence of the Enemy",          # Inspector Lynley adult mystery
    "Murder in the closet",                  # Academic literary criticism

    # Adult nonfiction / self-help / psychology
    "The Narcissistic family",               # Adult therapy book
    "Wilderness therapy for women",          # Adult therapy
    "Wilderness Therapy for Women",          # Adult therapy
    "Phantoms in the brain",                 # Adult neuroscience
    "The Einstein of money",                 # Adult finance/biography
    "45 Essential Skills to Survive Natural Disaster",  # Adult survival guide
    "Build the Perfect Bug Out Survival Skills",        # Adult survival guide
    "Shoot at Millions",                     # Adult
    "Twenty things adopted kids wish their adoptive parents knew",  # Parenting book
    "Apricots on the Nile",                  # Adult memoir
    "Beyond the kale",                       # Urban agriculture

    # Adult biographies / academic
    "Curriculum Vitae",                      # Muriel Spark autobiography
    "Mary Shelly",                           # Adult biography
    "Alternative Alices",                    # Academic literary criticism
    "Modernism, male friendship",            # Academic
    "Learning from other worlds",            # Academic sci-fi criticism
    "Learning from Other Worlds",            # Academic sci-fi criticism
    "Jimmy Page",                            # Rock biography
    "Ever by my side",                       # Adult veterinary memoir
    "Bamboo Shoots After the Rain",          # Adult short story anthology

    # Reference / study guides / meta-books
    "The Newbery & Caldecott awards",
    "The Newbery & Caldecott medal books",
    "Study Guide",                           # SuperSummary study guides
    "Successful Entrepreneurs Are Givers",   # Motivational adult coloring book

    # Harry Potter biographies (not the novels themselves)
    "Know All about J. K Rowling",
    "J.K. Rowling y Harry Potter",
    "Magic's Price",                         # Adult fantasy (Mercedes Lackey)
]


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

        # 3. Remove non-goal tags from learning_goals (newbery, middle_grade, early_readers, etc.)
        # These are category tags that snuck into the goals field — they confuse users
        print("\n--- Cleaning non-goal tags from learning_goals ---")
        rows = await conn.fetch("""
            SELECT id, title, learning_goals FROM books
            WHERE is_children_book = TRUE
            AND (
                learning_goals::text LIKE '%newbery%'
                OR learning_goals::text LIKE '%middle_grade%'
                OR learning_goals::text LIKE '%early_readers%'
                OR learning_goals::text LIKE '%curiosity%'
                OR learning_goals::text LIKE '%nature%'
                OR learning_goals::text LIKE '%community%'
            )
        """)
        VALID_GOALS = {
            "kindness", "courage", "friendship", "emotions", "science",
            "history", "diversity", "resilience", "problem_solving",
            "environment", "family", "creativity"
        }
        cleaned = 0
        for r in rows:
            import json
            goals = json.loads(r['learning_goals'] or '[]')
            new_goals = [g for g in goals if g in VALID_GOALS]
            if new_goals != goals:
                await conn.execute(
                    "UPDATE books SET learning_goals = $1 WHERE id = $2",
                    json.dumps(new_goals), r['id']
                )
                cleaned += 1
        print(f"  Cleaned goal tags on {cleaned} books")

        # 4. Audit: show remaining children's books with suspicious data
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
