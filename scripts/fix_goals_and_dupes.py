"""
Fix books with missing learning goals and remove duplicates.
Run: python scripts/fix_goals_and_dupes.py
"""
import asyncio
import asyncpg
import json

DB_URL = "postgresql://postgres:eRrNwgeutWVANDhVskIKbCkOJXQhRIWn@viaduct.proxy.rlwy.net:33806/railway"

# Assign sensible goals to books that have none
ASSIGN_GOALS = {
    "Abraham Lincoln":                      ["history", "courage", "resilience"],
    "A Christmas Carol":                    ["kindness", "family"],
    "A to Z Mysteries":                     ["problem_solving", "friendship"],
    "Buffalo Before Breakfast":             ["history", "science"],
    "Camp Half-Blood Confidential":         ["courage", "friendship", "creativity"],
    "Cinderella":                           ["resilience", "kindness"],
    "Dear Mr. Henshaw":                     ["resilience", "family", "creativity"],
    "Gathering Blue":                       ["resilience", "creativity", "courage"],
    "Harry Potter and the Cursed Child":    ["courage", "friendship", "resilience"],
    "Harry Potter and the Half-Blood Prince": ["courage", "friendship", "resilience"],
    "Harry Potter and the Philosopher's Stone": ["courage", "friendship", "resilience"],
    "Harry Potter (series) 1-4":            ["courage", "friendship", "resilience"],
    "Hey, Al":                              ["family", "resilience"],
    "House of Hades":                       ["courage", "friendship", "resilience"],
    "Lon Po Po":                            ["courage", "family"],
    "Nine days to Christmas":               ["family", "diversity"],
    "One crazy summer":                     ["family", "history", "resilience"],
    "Prayer For A Child":                   ["family", "kindness"],
    "Stone soup":                           ["kindness", "creativity"],
    "Strega Nona":                          ["creativity", "problem_solving"],
    "The Biggest Bear":                     ["resilience", "environment"],
    "The Big Snow":                         ["environment", "family"],
    "The  black arrow":                     ["courage", "history"],
    "The Blood of Olympus":                 ["courage", "friendship", "resilience"],
    "The Court of the Dead":                ["courage", "friendship"],
    "The egg tree":                         ["family", "creativity"],
    "The giver":                            ["courage", "history", "problem_solving"],
    "The Hidden Oracle":                    ["courage", "friendship", "problem_solving"],
    "The Last Olympian":                    ["courage", "friendship", "resilience"],
    "The lightning thief":                  ["courage", "friendship", "resilience"],
    "The Lightning Thief":                  ["courage", "friendship", "resilience"],
    "The Lion, the Witch and the Wardrobe": ["courage", "resilience", "family"],
    "The Lost Hero":                        ["courage", "friendship", "resilience"],
    "The Mark of Athena":                   ["courage", "friendship", "resilience"],
    "The Titan's Curse":                    ["courage", "friendship", "resilience"],
    "Tuesday":                              ["creativity"],
    "Vingt mille lieues sous les mers":     ["science", "courage"],
    "Wrath of the Triple Goddess":          ["courage", "friendship", "problem_solving"],
}

# Remove from children's (actual adult books)
REMOVE_FROM_CHILDREN = [
    "The Mysterious Affair at Styles",  # Agatha Christie adult mystery
    "Where the truth lies",             # Adult Christian fiction
]


async def main():
    conn = await asyncpg.connect(DB_URL)
    try:
        # 1. Remove adult books
        for title in REMOVE_FROM_CHILDREN:
            r = await conn.execute(
                "UPDATE books SET is_children_book = FALSE WHERE title ILIKE $1 AND is_children_book = TRUE",
                f"%{title}%"
            )
            print(f"Removed '{title}': {r}")

        # 2. Assign missing goals
        for title, goals in ASSIGN_GOALS.items():
            r = await conn.execute(
                "UPDATE books SET learning_goals = $1 WHERE title = $2 AND is_children_book = TRUE AND (learning_goals IS NULL OR learning_goals::text = '[]' OR learning_goals::text = 'null')",
                json.dumps(goals), title
            )
            if "UPDATE 0" not in r:
                print(f"Goals set for '{title}': {goals} — {r}")

        # 3. Remove duplicates — keep the one with a cover_url, else keep lowest id
        dupes = await conn.fetch("""
            SELECT LOWER(title) as title_lower, COUNT(*) as cnt
            FROM books
            WHERE is_children_book = TRUE
            GROUP BY LOWER(title)
            HAVING COUNT(*) > 1
        """)
        for dupe in dupes:
            rows = await conn.fetch(
                "SELECT id, cover_url FROM books WHERE LOWER(title) = $1 AND is_children_book = TRUE ORDER BY cover_url NULLS LAST, id ASC",
                dupe['title_lower']
            )
            # Keep first (has cover or lowest id), delete the rest
            keep_id = rows[0]['id']
            delete_ids = [r['id'] for r in rows[1:]]
            for del_id in delete_ids:
                await conn.execute("DELETE FROM books WHERE id = $1", del_id)
            print(f"Deduped '{dupe['title_lower']}': kept {keep_id}, removed {len(delete_ids)}")

        # Final count
        count = await conn.fetchval("SELECT COUNT(*) FROM books WHERE is_children_book = TRUE")
        print(f"\n✅ Done. Total children's books: {count}")

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
