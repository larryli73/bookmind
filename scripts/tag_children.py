"""
BookMind Children's Book Tagger
Tags existing books in database with learning goals and age ranges
Much faster than re-ingesting — just updates existing records
"""
import asyncio
import os
import json
import asyncpg
from datetime import datetime

# Books to tag: {title_fragment: {learning_goals, age_min, age_max}}
CHILDREN_BOOKS = [
    # KINDNESS & EMPATHY
    {"title": "Wonder", "author": "Palacio", "goals": ["kindness","courage","diversity"], "age": (8,13)},
    {"title": "Each Kindness", "author": "Woodson", "goals": ["kindness","diversity"], "age": (4,8)},
    {"title": "Enemy Pie", "author": "Munson", "goals": ["kindness","friendship"], "age": (4,8)},
    {"title": "Last Stop on Market Street", "author": "de la Pena", "goals": ["kindness","diversity"], "age": (4,8)},
    {"title": "Chrysanthemum", "author": "Henkes", "goals": ["kindness","friendship"], "age": (4,8)},
    {"title": "Recess Queen", "author": "O'Neill", "goals": ["kindness","courage"], "age": (4,8)},

    # COURAGE & CONFIDENCE
    {"title": "Matilda", "author": "Dahl", "goals": ["courage","resilience","creativity"], "age": (7,12)},
    {"title": "Pippi Longstocking", "author": "Lindgren", "goals": ["courage","creativity"], "age": (6,10)},
    {"title": "Paper Bag Princess", "author": "Munsch", "goals": ["courage","diversity"], "age": (4,8)},
    {"title": "Harriet the Spy", "author": "Fitzhugh", "goals": ["courage","friendship","creativity"], "age": (8,12)},
    {"title": "One and Only Ivan", "author": "Applegate", "goals": ["courage","resilience","environment"], "age": (8,12)},

    # FRIENDSHIP
    {"title": "Charlotte's Web", "author": "White", "goals": ["friendship","kindness","resilience"], "age": (7,11)},
    {"title": "Frog and Toad", "author": "Lobel", "goals": ["friendship","kindness"], "age": (4,8)},
    {"title": "Winnie-the-Pooh", "author": "Milne", "goals": ["friendship","creativity"], "age": (4,9)},
    {"title": "Because of Winn-Dixie", "author": "DiCamillo", "goals": ["friendship","family","resilience"], "age": (7,11)},
    {"title": "Bridge to Terabithia", "author": "Paterson", "goals": ["friendship","courage","resilience"], "age": (9,13)},
    {"title": "Anne of Green Gables", "author": "Montgomery", "goals": ["friendship","courage","family"], "age": (10,14)},

    # SCIENCE & NATURE
    {"title": "Magic School Bus", "author": "Cole", "goals": ["science","curiosity"], "age": (5,9)},
    {"title": "Wild Robot", "author": "Brown", "goals": ["science","environment","resilience"], "age": (8,12)},
    {"title": "Ada Twist", "author": "Beaty", "goals": ["science","courage"], "age": (4,8)},
    {"title": "Rosie Revere", "author": "Beaty", "goals": ["science","courage","resilience"], "age": (4,8)},
    {"title": "George's Secret Key", "author": "Hawking", "goals": ["science","curiosity"], "age": (7,12)},
    {"title": "My Side of the Mountain", "author": "George", "goals": ["environment","resilience","courage"], "age": (9,13)},
    {"title": "Island of the Blue Dolphins", "author": "O'Dell", "goals": ["environment","resilience","courage"], "age": (9,13)},

    # HISTORY & CULTURE
    {"title": "Number the Stars", "author": "Lowry", "goals": ["history","courage","kindness"], "age": (9,13)},
    {"title": "Roll of Thunder", "author": "Taylor", "goals": ["history","diversity","resilience"], "age": (9,13)},
    {"title": "Watsons Go to Birmingham", "author": "Curtis", "goals": ["history","diversity","family"], "age": (8,12)},
    {"title": "Inside Out and Back Again", "author": "Lai", "goals": ["history","diversity","resilience"], "age": (8,12)},
    {"title": "Esperanza Rising", "author": "Ryan", "goals": ["history","diversity","resilience"], "age": (9,13)},
    {"title": "Bud, Not Buddy", "author": "Curtis", "goals": ["history","resilience","family"], "age": (8,12)},
    {"title": "Little House", "author": "Wilder", "goals": ["history","family","resilience"], "age": (7,11)},
    {"title": "Sarah, Plain and Tall", "author": "MacLachlan", "goals": ["history","family"], "age": (6,10)},

    # DIVERSITY & INCLUSION
    {"title": "Front Desk", "author": "Yang", "goals": ["diversity","resilience","friendship"], "age": (8,13)},
    {"title": "Name Jar", "author": "Choi", "goals": ["diversity","courage","friendship"], "age": (4,8)},
    {"title": "New Kid", "author": "Craft", "goals": ["diversity","friendship","courage"], "age": (8,12)},
    {"title": "Merci Suarez", "author": "Medina", "goals": ["diversity","family","friendship"], "age": (10,14)},
    {"title": "Inside Out and Back Again", "author": "Lai", "goals": ["diversity","resilience"], "age": (8,12)},

    # RESILIENCE & GRIT
    {"title": "Hatchet", "author": "Paulsen", "goals": ["resilience","courage","environment"], "age": (9,13)},
    {"title": "Holes", "author": "Sachar", "goals": ["resilience","friendship","problem_solving"], "age": (9,13)},
    {"title": "Long Walk to Water", "author": "Park", "goals": ["resilience","history","courage"], "age": (9,13)},
    {"title": "Crossover", "author": "Alexander", "goals": ["resilience","family","friendship"], "age": (9,13)},

    # PROBLEM SOLVING
    {"title": "From the Mixed-Up Files", "author": "Konigsburg", "goals": ["problem_solving","courage","creativity"], "age": (8,12)},
    {"title": "Westing Game", "author": "Raskin", "goals": ["problem_solving","diversity"], "age": (9,13)},
    {"title": "Mysterious Benedict Society", "author": "Stewart", "goals": ["problem_solving","courage","friendship"], "age": (8,12)},
    {"title": "Encyclopedia Brown", "author": "Sobol", "goals": ["problem_solving","curiosity"], "age": (6,10)},
    {"title": "Phantom Tollbooth", "author": "Juster", "goals": ["problem_solving","creativity","curiosity"], "age": (8,12)},
    {"title": "Diary of a Wimpy Kid", "author": "Kinney", "goals": ["problem_solving","friendship"], "age": (7,12)},

    # ENVIRONMENT
    {"title": "Lorax", "author": "Seuss", "goals": ["environment","courage"], "age": (4,8)},
    {"title": "Hoot", "author": "Hiaasen", "goals": ["environment","courage","problem_solving"], "age": (9,13)},
    {"title": "Watership Down", "author": "Adams", "goals": ["environment","resilience","friendship"], "age": (11,14)},

    # FAMILY
    {"title": "Little Women", "author": "Alcott", "goals": ["family","friendship","resilience"], "age": (10,14)},
    {"title": "Secret Garden", "author": "Burnett", "goals": ["family","resilience","nature"], "age": (8,12)},
    {"title": "Great Gilly Hopkins", "author": "Paterson", "goals": ["family","resilience","kindness"], "age": (8,12)},

    # CREATIVITY
    {"title": "Very Hungry Caterpillar", "author": "Carle", "goals": ["creativity","science"], "age": (2,5)},
    {"title": "Where the Wild Things Are", "author": "Sendak", "goals": ["creativity","emotions"], "age": (3,7)},
    {"title": "James and the Giant Peach", "author": "Dahl", "goals": ["creativity","courage"], "age": (7,11)},
    {"title": "Charlie and the Chocolate Factory", "author": "Dahl", "goals": ["creativity","resilience"], "age": (7,11)},
    {"title": "Inkheart", "author": "Funke", "goals": ["creativity","courage","family"], "age": (10,14)},
    {"title": "BFG", "author": "Dahl", "goals": ["creativity","courage","kindness"], "age": (7,11)},

    # PICTURE BOOKS
    {"title": "Goodnight Moon", "author": "Brown", "goals": ["creativity","family"], "age": (0,4)},
    {"title": "Guess How Much I Love You", "author": "McBratney", "goals": ["family","kindness"], "age": (0,5)},
    {"title": "Chicka Chicka Boom Boom", "author": "Martin", "goals": ["creativity"], "age": (2,5)},
    {"title": "Cat in the Hat", "author": "Seuss", "goals": ["creativity","problem_solving"], "age": (4,8)},
    {"title": "Green Eggs and Ham", "author": "Seuss", "goals": ["courage","resilience"], "age": (4,8)},
    {"title": "Corduroy", "author": "Freeman", "goals": ["kindness","friendship"], "age": (2,6)},
    {"title": "Madeline", "author": "Bemelmans", "goals": ["courage","resilience"], "age": (3,7)},

    # EARLY READERS
    {"title": "Biscuit", "author": "Capucilli", "goals": ["friendship","kindness"], "age": (4,7)},
    {"title": "Fly Guy", "author": "Arnold", "goals": ["friendship","creativity"], "age": (5,8)},
    {"title": "Junie B. Jones", "author": "Park", "goals": ["friendship","problem_solving"], "age": (6,9)},
    {"title": "Magic Tree House", "author": "Osborne", "goals": ["history","curiosity","friendship"], "age": (6,10)},
    {"title": "Nate the Great", "author": "Sharmat", "goals": ["problem_solving","curiosity"], "age": (5,9)},

    # MIDDLE GRADE CLASSICS
    {"title": "Percy Jackson", "author": "Riordan", "goals": ["courage","friendship","resilience"], "age": (9,13)},
    {"title": "Harry Potter", "author": "Rowling", "goals": ["courage","friendship","resilience"], "age": (9,14)},
    {"title": "Chronicles of Narnia", "author": "Lewis", "goals": ["courage","friendship","history"], "age": (8,13)},
    {"title": "Wrinkle in Time", "author": "L'Engle", "goals": ["science","courage","family"], "age": (9,13)},
    {"title": "Giver", "author": "Lowry", "goals": ["courage","history","problem_solving"], "age": (11,14)},
    {"title": "Tuck Everlasting", "author": "Babbitt", "goals": ["family","courage","resilience"], "age": (9,13)},
    {"title": "Treasure Island", "author": "Stevenson", "goals": ["courage","problem_solving"], "age": (10,14)},
]


def get_pg_url():
    url = os.getenv("DATABASE_URL", "")
    url = url.replace("postgresql+asyncpg://", "postgresql://")
    url = url.replace("postgres://", "postgresql://")
    return url


async def tag_children_books():
    conn = await asyncpg.connect(get_pg_url())

    print("\n🏷️  BookMind Children's Book Tagger")
    print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("─" * 50)

    # Ensure columns exist
    await conn.execute("ALTER TABLE books ADD COLUMN IF NOT EXISTS learning_goals JSONB DEFAULT '[]'::jsonb")
    await conn.execute("ALTER TABLE books ADD COLUMN IF NOT EXISTS is_children_book BOOLEAN DEFAULT FALSE")
    await conn.execute("ALTER TABLE books ADD COLUMN IF NOT EXISTS parent_note TEXT")
    print("✅ Columns ready\n")

    tagged = 0
    not_found = 0

    for book in CHILDREN_BOOKS:
        # Search by title (partial match, case insensitive)
        rows = await conn.fetch("""
            SELECT id, title, author, learning_goals
            FROM books
            WHERE LOWER(title) LIKE LOWER($1)
            LIMIT 5
        """, f"%{book['title']}%")

        if not rows:
            print(f"  ❌ Not found: {book['title']} — {book['author']}")
            not_found += 1
            continue

        # Pick best match (closest author name)
        best = rows[0]
        if len(rows) > 1:
            for row in rows:
                if any(part.lower() in row['author'].lower()
                       for part in book['author'].split()):
                    best = row
                    break

        # Update learning goals
        current = json.loads(best['learning_goals'] or '[]')
        new_goals = list(set(current + book['goals']))

        await conn.execute("""
            UPDATE books SET
                learning_goals = $1::jsonb,
                is_children_book = TRUE,
                age_min = COALESCE(age_min, $2),
                age_max = COALESCE(age_max, $3)
            WHERE id = $4
        """, json.dumps(new_goals), book['age'][0], book['age'][1], best['id'])

        print(f"  ✅ Tagged: {best['title'][:45]} → {', '.join(book['goals'][:3])}")
        tagged += 1

    # Show summary by goal
    print(f"\n{'─' * 50}")
    print(f"✅ Tagged {tagged} books ({not_found} not found in database)")

    # Count by goal
    print("\n📊 Books per learning goal:")
    goals = ["kindness","courage","friendship","emotions","science",
             "history","diversity","resilience","problem_solving",
             "environment","family","creativity"]

    for goal in goals:
        count = await conn.fetchval("""
            SELECT COUNT(*) FROM books
            WHERE learning_goals::text LIKE $1
            AND is_children_book = TRUE
        """, f"%{goal}%")
        bar = "█" * min(int(count or 0), 20)
        print(f"  {goal:20} {bar} {count or 0}")

    total_children = await conn.fetchval(
        "SELECT COUNT(*) FROM books WHERE is_children_book = TRUE"
    )
    print(f"\n📚 Total children's books tagged: {total_children}")
    await conn.close()


if __name__ == "__main__":
    asyncio.run(tag_children_books())
