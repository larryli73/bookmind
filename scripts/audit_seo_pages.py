"""
Audit all children's books in the DB for obvious data quality issues.
Flags books that look wrong based on title/genre/goal patterns.

Run: python scripts/audit_seo_pages.py
"""
import asyncio
import asyncpg
import os
import json

DB_URL = "postgresql://postgres:eRrNwgeutWVANDhVskIKbCkOJXQhRIWn@viaduct.proxy.rlwy.net:33806/railway"

# Words in titles that strongly suggest adult/non-children books
ADULT_TITLE_SIGNALS = [
    "romance", "erotic", "therapy", "narciss", "memoir", "autobiography",
    "academic", "feminist", "dissertation", "critique",
    "paranormal romance", "mystery series", "thriller series",
    "cookbook", "recipe", "investing", "finance", "stock market",
    "leadership", "entrepreneur", "startup", "marketing",
    "war crimes", "genocide", "addiction", "alcoholi",
    "divorce guide", "grief guide", "psychiatr", "psychoanal",
]

# Genres that suggest adult books
ADULT_GENRE_SIGNALS = [
    "fiction, romance", "romance, historical", "romance, general",
    "mystery & detective", "adult", "erotica",
    "self-help", "business", "finance", "investment",
    "feminist therapy", "psychology, adult",
]

# Goals that shouldn't exist in our system
INVALID_GOALS = {"newbery", "middle_grade", "early_readers", "curiosity", "nature", "community"}

VALID_GOALS = {
    "kindness", "courage", "friendship", "emotions", "science",
    "history", "diversity", "resilience", "problem_solving",
    "environment", "family", "creativity"
}


async def main():
    conn = await asyncpg.connect(DB_URL)
    try:
        rows = await conn.fetch("""
            SELECT id, title, author, age_min, age_max, learning_goals, genres
            FROM books
            WHERE is_children_book = TRUE
            ORDER BY title
        """)

        print(f"Total children's books: {len(rows)}\n")

        flagged = []
        no_valid_goals = []
        duplicate_titles = {}

        for r in rows:
            title_lower = r['title'].lower()
            genres_str = json.dumps(r['genres'] or []).lower()
            goals = json.loads(r['learning_goals'] or '[]')

            issues = []

            # Check for adult title signals
            for signal in ADULT_TITLE_SIGNALS:
                if signal in title_lower:
                    issues.append(f"adult title signal: '{signal}'")
                    break

            # Check for adult genre signals
            for signal in ADULT_GENRE_SIGNALS:
                if signal in genres_str:
                    issues.append(f"adult genre: '{signal}'")
                    break

            # Check for invalid goals still present
            bad_goals = [g for g in goals if g in INVALID_GOALS]
            if bad_goals:
                issues.append(f"invalid goals: {bad_goals}")

            # Check for books with no valid learning goals
            valid = [g for g in goals if g in VALID_GOALS]
            if not valid:
                no_valid_goals.append(f"  {r['title']} | goals: {goals}")

            # Track duplicates
            key = r['title'].lower().strip()
            duplicate_titles.setdefault(key, []).append(r['title'])

            if issues:
                flagged.append({
                    'title': r['title'],
                    'author': r['author'],
                    'ages': f"{r['age_min']}-{r['age_max']}",
                    'goals': goals,
                    'issues': issues
                })

        # Print flagged books
        if flagged:
            print(f"=== FLAGGED ({len(flagged)} books) ===")
            for b in flagged:
                print(f"\n  ⚠️  {b['title']} by {b['author']} (ages {b['ages']})")
                print(f"     Goals: {b['goals']}")
                for issue in b['issues']:
                    print(f"     Issue: {issue}")

        # Print books with no valid goals
        if no_valid_goals:
            print(f"\n=== NO VALID LEARNING GOALS ({len(no_valid_goals)} books) ===")
            for line in no_valid_goals:
                print(line)

        # Print duplicates
        dupes = {k: v for k, v in duplicate_titles.items() if len(v) > 1}
        if dupes:
            print(f"\n=== DUPLICATE TITLES ({len(dupes)}) ===")
            for title, instances in dupes.items():
                print(f"  {instances[0]} ({len(instances)}x)")

        print(f"\n✅ Clean books (no flags): {len(rows) - len(flagged)}")

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
