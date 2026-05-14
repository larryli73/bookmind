"""
Simulate all child searches (age × learning goal) and flag quality issues.
Uses the same DB query logic as the live endpoint.

Run: python scripts/simulate_searches.py
"""
import asyncio
import asyncpg
import json

DB_URL = "postgresql://postgres:eRrNwgeutWVANDhVskIKbCkOJXQhRIWn@viaduct.proxy.rlwy.net:33806/railway"

LEARNING_GOALS = [
    "kindness", "courage", "friendship", "emotions", "science",
    "history", "diversity", "resilience", "problem_solving",
    "environment", "family", "creativity"
]

AGES = [3, 4, 5, 6, 7, 8, 9, 10, 11, 12]

# Books that should never appear in children's results
BLACKLIST_SIGNALS = [
    "bible", "holy bible", "testament",
    "astrophysics for people in a hurry",
    "vingt mille lieues",
    "cookbook", "recipe",
    "study guide", "teacher guide", "literature guide",
    "newbery & caldecott", "newbery and caldecott",
]


async def search(conn, age: int, goal: str, limit: int = 6) -> list:
    age_min = max(0, age - 2)
    age_max = age + 2
    db_goal = goal.replace("-", "_")

    rows = await conn.fetch(f"""
        SELECT title, author, age_min, age_max, learning_goals
        FROM books
        WHERE is_children_book = TRUE
        AND age_min <= $1
        AND age_max >= $2
        AND learning_goals::text LIKE $3
        ORDER BY
            CASE WHEN cover_url IS NOT NULL THEN 0 ELSE 1 END,
            CASE WHEN age_min <= $4 AND age_max >= $4 THEN 0 ELSE 1 END,
            page_count DESC NULLS LAST
        LIMIT $5
    """, age_max, age_min, f"%{db_goal}%", age, limit)

    # Widen if too few
    if len(rows) < 3:
        rows = await conn.fetch("""
            SELECT title, author, age_min, age_max, learning_goals
            FROM books
            WHERE is_children_book = TRUE
            AND age_min <= $1
            AND age_max >= $2
            ORDER BY
                CASE WHEN cover_url IS NOT NULL THEN 0 ELSE 1 END,
                page_count DESC NULLS LAST
            LIMIT $3
        """, age + 4, max(0, age - 3), limit)

    return rows


def check_quality(books, age, goal) -> list:
    issues = []
    if len(books) == 0:
        issues.append("NO RESULTS")
        return issues
    if len(books) < 3:
        issues.append(f"only {len(books)} results (fell back to wide search)")

    for b in books:
        title_lower = b['title'].lower()
        for signal in BLACKLIST_SIGNALS:
            if signal in title_lower:
                issues.append(f"BAD BOOK: '{b['title']}'")
                break

        # Flag if age range is way off
        if b['age_max'] < age - 3 or b['age_min'] > age + 3:
            issues.append(f"AGE MISMATCH: '{b['title']}' (ages {b['age_min']}-{b['age_max']}) shown for age {age}")

    return issues


async def main():
    conn = await asyncpg.connect(DB_URL)

    print("BookMind Child Search Simulation")
    print(f"Testing {len(AGES)} ages × {len(LEARNING_GOALS)} goals = {len(AGES)*len(LEARNING_GOALS)} combinations\n")

    all_issues = []
    zero_results = []
    thin_results = []  # < 4 books

    for goal in LEARNING_GOALS:
        goal_issues = []
        for age in AGES:
            books = await search(conn, age, goal)
            issues = check_quality(books, age, goal)
            if issues:
                goal_issues.append((age, books, issues))
            if len(books) == 0:
                zero_results.append(f"age={age} goal={goal}")
            elif len(books) < 4:
                thin_results.append(f"age={age} goal={goal} ({len(books)} books)")

        if goal_issues:
            print(f"⚠️  {goal.upper()}")
            for age, books, issues in goal_issues:
                titles = [b['title'][:40] for b in books]
                print(f"   Age {age}: {issues}")
                print(f"   Books: {titles}")
            all_issues.extend(goal_issues)
        else:
            # Show sample result for clean goals
            sample = await search(conn, 8, goal)
            titles = [b['title'][:30] for b in sample[:3]]
            print(f"✅ {goal.upper()} — e.g. age 8: {titles}")

    print(f"\n{'='*60}")
    print(f"SUMMARY")
    print(f"  Zero results:  {len(zero_results)}")
    print(f"  Thin (<4):     {len(thin_results)}")
    print(f"  Goals with issues: {len(set(g for g,_,_ in all_issues))}")

    if zero_results:
        print(f"\nZERO RESULT COMBOS:")
        for z in zero_results:
            print(f"  {z}")

    if thin_results:
        print(f"\nTHIN RESULT COMBOS (< 4 books):")
        for t in thin_results:
            print(f"  {t}")

    await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
