"""
Run this on your Mac — fetches children's books from Open Library
and inserts directly into Railway PostgreSQL.
"""
import asyncio
import os
import json
import hashlib
import math
import httpx
import asyncpg

VOYAGE_API_KEY = os.getenv("VOYAGE_API_KEY", "")
DATABASE_URL = os.getenv("DATABASE_URL", "")
DIMS = 1024

# Every important children's book we need, organized by priority
BOOKS_TO_ADD = [
    # ── EMOTIONS (critical — only 1 book) ──────────────────────
    ("In My Heart", "Jo Witek", ["emotions","family"], (3,7)),
    ("The Feelings Book", "Todd Parr", ["emotions","kindness"], (3,7)),
    ("When Sophie Gets Angry", "Molly Bang", ["emotions","resilience"], (4,8)),
    ("Grumpy Monkey", "Suzanne Lang", ["emotions","creativity"], (3,7)),
    ("Wemberly Worried", "Kevin Henkes", ["emotions","courage"], (4,8)),
    ("Today I Feel Silly", "Jamie Lee Curtis", ["emotions","creativity"], (3,7)),
    ("The Invisible String", "Patrice Karst", ["emotions","family"], (3,8)),
    ("Scaredy Squirrel", "Melanie Watt", ["emotions","courage","problem_solving"], (4,8)),
    ("Listening to My Body", "Gabi Garcia", ["emotions","resilience"], (4,8)),
    ("A Little Spot of Emotion", "Diane Alber", ["emotions","kindness"], (3,7)),
    ("Tough Guys Have Feelings Too", "Keith Negley", ["emotions","kindness"], (3,7)),
    ("The Color Monster", "Anna Llenas", ["emotions","creativity"], (3,7)),
    ("Sometimes I'm Bombaloo", "Rachel Vail", ["emotions","resilience"], (3,7)),
    ("When I Feel Angry", "Cornelia Maude Spelman", ["emotions","resilience"], (3,7)),
    ("Breathe Like a Bear", "Kira Willey", ["emotions","resilience"], (3,8)),

    # ── KINDNESS (needs more) ───────────────────────────────────
    ("Wonder", "R.J. Palacio", ["kindness","courage","diversity"], (8,13)),
    ("Each Kindness", "Jacqueline Woodson", ["kindness","diversity"], (4,8)),
    ("Enemy Pie", "Derek Munson", ["kindness","friendship"], (4,8)),
    ("Last Stop on Market Street", "Matt de la Pena", ["kindness","diversity"], (4,8)),
    ("Chrysanthemum", "Kevin Henkes", ["kindness","friendship"], (4,8)),
    ("The Recess Queen", "Alexis O'Neill", ["kindness","courage"], (4,8)),
    ("Those Shoes", "Maribeth Boelts", ["kindness","resilience"], (4,8)),
    ("Fly Away Home", "Eve Bunting", ["kindness","resilience"], (5,9)),
    ("Stand in My Shoes", "Bob Sornson", ["kindness","empathy"], (4,8)),
    ("The Invisible Boy", "Trudy Ludwig", ["kindness","friendship"], (4,9)),
    ("Anh's Anger", "Gail Silver", ["kindness","emotions"], (4,8)),
    ("Have You Filled a Bucket Today", "Carol McCloud", ["kindness","friendship"], (4,8)),

    # ── PICTURE BOOKS (need all classics) ──────────────────────
    ("Goodnight Moon", "Margaret Wise Brown", ["creativity","family"], (0,4)),
    ("Guess How Much I Love You", "Sam McBratney", ["family","kindness"], (0,5)),
    ("The Very Hungry Caterpillar", "Eric Carle", ["creativity","science"], (2,5)),
    ("The Cat in the Hat", "Dr. Seuss", ["creativity","problem_solving"], (4,8)),
    ("Green Eggs and Ham", "Dr. Seuss", ["courage","resilience"], (4,8)),
    ("Corduroy", "Don Freeman", ["kindness","friendship"], (2,6)),
    ("Chicka Chicka Boom Boom", "Bill Martin Jr.", ["creativity"], (2,5)),
    ("The Giving Tree", "Shel Silverstein", ["kindness","family"], (4,8)),
    ("Where the Wild Things Are", "Maurice Sendak", ["emotions","creativity"], (3,7)),
    ("Oh the Places You'll Go", "Dr. Seuss", ["courage","resilience"], (4,10)),
    ("If You Give a Mouse a Cookie", "Laura Numeroff", ["creativity","problem_solving"], (3,7)),
    ("The Snowy Day", "Ezra Jack Keats", ["creativity","diversity"], (3,7)),
    ("Knuffle Bunny", "Mo Willems", ["emotions","family"], (2,6)),
    ("Don't Let the Pigeon Drive the Bus", "Mo Willems", ["emotions","problem_solving"], (2,6)),
    ("Click Clack Moo", "Doreen Cronin", ["problem_solving","creativity"], (3,7)),
    ("Stellaluna", "Janell Cannon", ["friendship","diversity","kindness"], (4,8)),
    ("The Runaway Bunny", "Margaret Wise Brown", ["family","kindness"], (0,5)),
    ("Mike Mulligan and His Steam Shovel", "Virginia Lee Burton", ["resilience","problem_solving"], (3,7)),

    # ── EARLY READERS ──────────────────────────────────────────
    ("Frog and Toad Are Friends", "Arnold Lobel", ["friendship","kindness"], (4,8)),
    ("Junie B Jones", "Barbara Park", ["friendship","problem_solving"], (6,9)),
    ("Magic Tree House", "Mary Pope Osborne", ["history","curiosity","friendship"], (6,10)),
    ("Elephant and Piggie", "Mo Willems", ["friendship","emotions"], (4,8)),
    ("Biscuit", "Alyssa Satin Capucilli", ["friendship","kindness"], (4,7)),
    ("Cam Jansen", "David Adler", ["problem_solving","courage"], (6,9)),
    ("Horrible Harry", "Suzy Kline", ["friendship","problem_solving"], (6,9)),
    ("Nate the Great", "Marjorie Sharmat", ["problem_solving","curiosity"], (5,9)),
    ("A to Z Mysteries", "Ron Roy", ["problem_solving","friendship"], (6,9)),

    # ── MIDDLE GRADE MISSING ────────────────────────────────────
    ("Charlotte's Web", "E.B. White", ["friendship","kindness","resilience"], (7,11)),
    ("Hatchet", "Gary Paulsen", ["resilience","courage","environment"], (9,13)),
    ("Number the Stars", "Lois Lowry", ["history","courage","kindness"], (9,13)),
    ("A Wrinkle in Time", "Madeleine L'Engle", ["science","courage","family"], (9,13)),
    ("Tuck Everlasting", "Natalie Babbitt", ["family","courage","resilience"], (9,13)),
    ("The Phantom Tollbooth", "Norton Juster", ["problem_solving","creativity","curiosity"], (8,12)),
    ("Bridge to Terabithia", "Katherine Paterson", ["friendship","courage","resilience"], (9,13)),
    ("Because of Winn-Dixie", "Kate DiCamillo", ["friendship","family","resilience"], (7,11)),
    ("The Chronicles of Narnia", "C.S. Lewis", ["courage","friendship"], (8,13)),
    ("Island of the Blue Dolphins", "Scott O'Dell", ["environment","resilience","courage"], (9,13)),
    ("My Side of the Mountain", "Jean Craighead George", ["environment","resilience"], (9,13)),
    ("The Westing Game", "Ellen Raskin", ["problem_solving","diversity"], (9,13)),
    ("Encyclopedia Brown", "Donald Sobol", ["problem_solving","curiosity"], (6,10)),
    ("From the Mixed-Up Files", "E.L. Konigsburg", ["problem_solving","courage"], (8,12)),
    ("The Mysterious Benedict Society", "Trenton Lee Stewart", ["problem_solving","courage","friendship"], (8,12)),
    ("Harriet the Spy", "Louise Fitzhugh", ["courage","creativity"], (8,12)),
    ("Pippi Longstocking", "Astrid Lindgren", ["courage","creativity"], (6,10)),
    ("The Great Gilly Hopkins", "Katherine Paterson", ["family","resilience","kindness"], (8,12)),

    # ── DIVERSITY MUST HAVES ────────────────────────────────────
    ("Front Desk", "Kelly Yang", ["diversity","resilience","friendship"], (8,13)),
    ("The Name Jar", "Yangsook Choi", ["diversity","courage","friendship"], (4,8)),
    ("New Kid", "Jerry Craft", ["diversity","friendship","courage"], (8,12)),
    ("Merci Suarez Changes Gears", "Meg Medina", ["diversity","family","friendship"], (10,14)),
    ("Inside Out and Back Again", "Thanhha Lai", ["history","diversity","resilience"], (8,12)),
    ("Esperanza Rising", "Pam Munoz Ryan", ["history","diversity","resilience"], (9,13)),
    ("Roll of Thunder Hear My Cry", "Mildred Taylor", ["history","diversity","resilience"], (9,13)),
    ("Bud Not Buddy", "Christopher Paul Curtis", ["history","resilience","family"], (8,12)),
    ("The Watsons Go to Birmingham", "Christopher Paul Curtis", ["history","diversity","family"], (8,12)),
    ("Each Kindness", "Jacqueline Woodson", ["kindness","diversity"], (4,8)),
    ("Last Stop on Market Street", "Matt de la Pena", ["kindness","diversity"], (4,8)),
    ("The Snowy Day", "Ezra Jack Keats", ["creativity","diversity"], (3,7)),
    ("Corduroy", "Don Freeman", ["kindness","friendship"], (2,6)),
    ("Chicken Sunday", "Patricia Polacco", ["diversity","kindness","friendship"], (5,9)),
    ("Amazing Grace", "Mary Hoffman", ["diversity","courage"], (4,8)),

    # ── SCIENCE & NATURE ───────────────────────────────────────
    ("Ada Twist Scientist", "Andrea Beaty", ["science","courage"], (4,8)),
    ("Rosie Revere Engineer", "Andrea Beaty", ["science","courage","resilience"], (4,8)),
    ("Iggy Peck Architect", "Andrea Beaty", ["science","creativity"], (4,8)),
    ("The Magic School Bus", "Joanna Cole", ["science","curiosity"], (5,9)),
    ("Watership Down", "Richard Adams", ["environment","resilience","friendship"], (11,14)),
    ("The Lorax", "Dr. Seuss", ["environment","courage"], (4,8)),
    ("Sarah Plain and Tall", "Patricia MacLachlan", ["history","family"], (6,10)),
    ("A Long Walk to Water", "Linda Sue Park", ["resilience","history","courage"], (9,13)),
    ("Hidden Figures Young Readers", "Margot Lee Shetterly", ["science","diversity","courage"], (8,13)),
    ("George's Secret Key to the Universe", "Lucy Hawking", ["science","curiosity"], (7,12)),

    # ── FRIENDSHIP ─────────────────────────────────────────────
    ("The Penderwicks", "Jeanne Birdsall", ["friendship","family"], (8,12)),
    ("Hello Universe", "Erin Entrada Kelly", ["friendship","diversity","courage"], (8,12)),
    ("The One and Only Bob", "Katherine Applegate", ["friendship","resilience"], (8,12)),
    ("Stargirl", "Jerry Spinelli", ["kindness","courage","diversity"], (10,14)),
    ("Maniac Magee", "Jerry Spinelli", ["diversity","friendship","resilience"], (9,13)),

    # ── RESILIENCE ─────────────────────────────────────────────
    ("Ghost", "Jason Reynolds", ["resilience","friendship","courage"], (10,14)),
    ("Restart", "Gordon Korman", ["resilience","friendship","kindness"], (8,12)),
    ("The One and Only Ivan", "Katherine Applegate", ["resilience","courage","environment"], (8,12)),
]


def get_pg_url():
    url = DATABASE_URL or os.getenv("DATABASE_URL", "")
    url = url.replace("postgresql+asyncpg://", "postgresql://")
    url = url.replace("postgres://", "postgresql://")
    return url


async def get_embedding(text):
    if VOYAGE_API_KEY:
        try:
            async with httpx.AsyncClient() as client:
                r = await client.post(
                    "https://api.voyageai.com/v1/embeddings",
                    headers={"Authorization": f"Bearer {VOYAGE_API_KEY}"},
                    json={"model": "voyage-3", "input": [text]},
                    timeout=30.0,
                )
                r.raise_for_status()
                return r.json()["data"][0]["embedding"][:DIMS]
        except Exception as e:
            print(f"    ⚠️ Voyage failed: {e}, using hash embedding")

    vector = []
    for i in range(DIMS):
        seed = hashlib.md5(f"{text}{i}".encode()).hexdigest()
        val = int(seed[:8], 16) / (16**8)
        vector.append(val * 2 - 1)
    magnitude = math.sqrt(sum(x**2 for x in vector))
    return [x / magnitude for x in vector]


async def search_open_library(title, author):
    async with httpx.AsyncClient() as client:
        r = await client.get(
            "https://openlibrary.org/search.json",
            params={
                "title": title,
                "author": author,
                "limit": 5,
                "fields": "key,title,author_name,isbn,cover_i,first_publish_year,subject,number_of_pages_median"
            },
            headers={"User-Agent": "BookMind/1.0 (bookmind@getbookmind.ai)"},
            timeout=20.0
        )
        r.raise_for_status()
        return r.json().get("docs", [])


async def run():
    conn = await asyncpg.connect(get_pg_url())

    # Ensure columns exist
    await conn.execute("ALTER TABLE books ADD COLUMN IF NOT EXISTS learning_goals JSONB DEFAULT '[]'::jsonb")
    await conn.execute("ALTER TABLE books ADD COLUMN IF NOT EXISTS is_children_book BOOLEAN DEFAULT FALSE")
    await conn.execute("ALTER TABLE books ADD COLUMN IF NOT EXISTS parent_note TEXT")

    print(f"\n📚 BookMind Children's Book Database Builder")
    print(f"🎯 Target: {len(BOOKS_TO_ADD)} books")
    print("─" * 55)

    added = 0
    tagged = 0
    failed = []

    for title, author, goals, age in BOOKS_TO_ADD:
        # Check if exists by title + author
        existing = await conn.fetchrow("""
            SELECT id, title, author, learning_goals FROM books
            WHERE LOWER(title) LIKE LOWER($1)
            AND LOWER(author) LIKE LOWER($2)
            LIMIT 1
        """, f"%{title.split()[0]}%", f"%{author.split()[-1]}%")

        # Also try exact title match
        if not existing:
            existing = await conn.fetchrow("""
                SELECT id, title, author, learning_goals FROM books
                WHERE LOWER(title) = LOWER($1)
                LIMIT 1
            """, title)

        if existing:
            current = json.loads(existing['learning_goals'] or '[]')
            new_goals = list(set(current + goals))
            await conn.execute("""
                UPDATE books SET
                    learning_goals = $1::jsonb,
                    is_children_book = TRUE,
                    age_min = COALESCE(age_min, $2),
                    age_max = COALESCE(age_max, $3)
                WHERE id = $4
            """, json.dumps(new_goals), age[0], age[1], existing['id'])
            print(f"  ✅ Tagged:  {existing['title'][:50]}")
            tagged += 1
            continue

        # Search Open Library
        try:
            results = await search_open_library(title, author)
        except Exception as e:
            print(f"  ⚠️  OL Error '{title}': {e}")
            failed.append(title)
            continue

        inserted = False
        for raw in results:
            isbn_list = raw.get("isbn") or []
            isbn_13 = next((x for x in isbn_list if len(x) == 13), None)
            isbn_10 = next((x for x in isbn_list if len(x) == 10), None)
            if not isbn_13 and not isbn_10:
                continue

            # Check by ISBN
            by_isbn = await conn.fetchrow(
                "SELECT id, learning_goals FROM books WHERE isbn_13=$1 OR isbn_10=$2",
                isbn_13, isbn_10
            )
            if by_isbn:
                current = json.loads(by_isbn['learning_goals'] or '[]')
                new_goals = list(set(current + goals))
                await conn.execute("""
                    UPDATE books SET learning_goals=$1::jsonb,
                    is_children_book=TRUE,
                    age_min=COALESCE(age_min,$2),
                    age_max=COALESCE(age_max,$3)
                    WHERE id=$4
                """, json.dumps(new_goals), age[0], age[1], by_isbn['id'])
                print(f"  ✅ Tagged:  {raw.get('title','')[:50]}")
                tagged += 1
                inserted = True
                break

            # Insert new book
            try:
                text = (
                    f"Title: {raw.get('title','')}\n"
                    f"Author: {', '.join(raw.get('author_name') or [author])}\n"
                    f"For children ages {age[0]}-{age[1]}\n"
                    f"Teaches: {', '.join(goals)}\n"
                    f"Subjects: {', '.join((raw.get('subject') or [])[:5])}"
                )
                emb = await get_embedding(text)
                cover_id = raw.get("cover_i")

                result = await conn.fetchval("""
                    INSERT INTO books (
                        isbn_13, isbn_10, title, author, published_year,
                        page_count, genres, cover_url, embedding, language,
                        is_series, has_violence, has_scary_content, has_adult_themes,
                        age_min, age_max, learning_goals, is_children_book
                    ) VALUES (
                        $1,$2,$3,$4,$5,$6,$7::jsonb,$8,$9::vector,
                        'en',false,false,false,false,$10,$11,$12::jsonb,TRUE
                    ) ON CONFLICT DO NOTHING RETURNING id
                """,
                    isbn_13, isbn_10,
                    raw.get("title", title),
                    (raw.get("author_name") or [author])[0],
                    raw.get("first_publish_year"),
                    raw.get("number_of_pages_median"),
                    json.dumps(raw.get("subject", [])[:10]),
                    f"https://covers.openlibrary.org/b/id/{cover_id}-L.jpg" if cover_id else None,
                    str(emb), age[0], age[1], json.dumps(goals)
                )

                if result:
                    print(f"  ➕ Added:   {raw.get('title', title)[:50]}")
                    added += 1
                    inserted = True
                    break

            except Exception as e:
                print(f"    ❌ Insert error: {e}")
                continue

        if not inserted:
            print(f"  ❌ Failed:  {title} — {author}")
            failed.append(title)

        await asyncio.sleep(0.3)

    # Final summary
    total = await conn.fetchval("SELECT COUNT(*) FROM books WHERE is_children_book=TRUE")

    print(f"\n{'═' * 55}")
    print(f"✅ Results: {added} added, {tagged} tagged, {len(failed)} failed")
    print(f"📚 Total children's books: {total}")

    if failed:
        print(f"\n❌ Still missing ({len(failed)} books):")
        for f in failed:
            print(f"   • {f}")

    print("\n📊 Books per learning goal:")
    goals_list = [
        "kindness", "courage", "friendship", "emotions", "science",
        "history", "diversity", "resilience", "problem_solving",
        "environment", "family", "creativity"
    ]
    all_good = True
    for goal in goals_list:
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM books WHERE learning_goals::text LIKE $1 AND is_children_book=TRUE",
            f"%{goal}%"
        ) or 0
        bar = "█" * min(count, 30)
        status = "✅" if count >= 10 else "⚠️ " if count >= 5 else "❌"
        if count < 10:
            all_good = False
        print(f"  {status} {goal:20} {bar} {count}")

    if all_good:
        print("\n🎉 All learning goals have 10+ books — feature ready to ship!")
    else:
        print("\n⚠️  Some goals still need more books.")

    await conn.close()


if __name__ == "__main__":
    asyncio.run(run())
