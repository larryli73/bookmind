"""
Add specific missing children's books directly by ISBN lookup
"""
import asyncio
import os
import json
import hashlib
import math
import httpx
import asyncpg

VOYAGE_API_KEY = os.getenv("VOYAGE_API_KEY", "")
VOYAGE_MODEL = "voyage-3"
DIMS = 1024

# Every missing book with exact search terms
MISSING_BOOKS = [
    {"search": "Each Kindness Jacqueline Woodson", "goals": ["kindness","diversity"], "age": (4,8)},
    {"search": "Enemy Pie Derek Munson", "goals": ["kindness","friendship"], "age": (4,8)},
    {"search": "Last Stop on Market Street Matt de la Pena", "goals": ["kindness","diversity"], "age": (4,8)},
    {"search": "Chrysanthemum Kevin Henkes", "goals": ["kindness","friendship"], "age": (4,8)},
    {"search": "The Recess Queen Alexis O Neill", "goals": ["kindness","courage"], "age": (4,8)},
    {"search": "Pippi Longstocking Astrid Lindgren", "goals": ["courage","creativity"], "age": (6,10)},
    {"search": "The Paper Bag Princess Robert Munsch", "goals": ["courage","diversity"], "age": (4,8)},
    {"search": "Harriet the Spy Louise Fitzhugh", "goals": ["courage","creativity"], "age": (8,12)},
    {"search": "The One and Only Ivan Katherine Applegate", "goals": ["courage","resilience"], "age": (8,12)},
    {"search": "Charlotte's Web E.B. White", "goals": ["friendship","kindness","resilience"], "age": (7,11)},
    {"search": "Frog and Toad Arnold Lobel", "goals": ["friendship","kindness"], "age": (4,8)},
    {"search": "Because of Winn-Dixie Kate DiCamillo", "goals": ["friendship","family","resilience"], "age": (7,11)},
    {"search": "Bridge to Terabithia Katherine Paterson", "goals": ["friendship","courage","resilience"], "age": (9,13)},
    {"search": "The Magic School Bus Joanna Cole", "goals": ["science","curiosity"], "age": (5,9)},
    {"search": "Ada Twist Scientist Andrea Beaty", "goals": ["science","courage"], "age": (4,8)},
    {"search": "Rosie Revere Engineer Andrea Beaty", "goals": ["science","courage","resilience"], "age": (4,8)},
    {"search": "George's Secret Key to the Universe Hawking", "goals": ["science","curiosity"], "age": (7,12)},
    {"search": "My Side of the Mountain Jean Craighead George", "goals": ["environment","resilience"], "age": (9,13)},
    {"search": "Island of the Blue Dolphins Scott O'Dell", "goals": ["environment","resilience","courage"], "age": (9,13)},
    {"search": "Number the Stars Lois Lowry", "goals": ["history","courage","kindness"], "age": (9,13)},
    {"search": "Roll of Thunder Hear My Cry Mildred Taylor", "goals": ["history","diversity","resilience"], "age": (9,13)},
    {"search": "The Watsons Go to Birmingham Christopher Paul Curtis", "goals": ["history","diversity","family"], "age": (8,12)},
    {"search": "Inside Out and Back Again Thanhha Lai", "goals": ["history","diversity","resilience"], "age": (8,12)},
    {"search": "Esperanza Rising Pam Munoz Ryan", "goals": ["history","diversity","resilience"], "age": (9,13)},
    {"search": "Bud Not Buddy Christopher Paul Curtis", "goals": ["history","resilience","family"], "age": (8,12)},
    {"search": "Sarah Plain and Tall Patricia MacLachlan", "goals": ["history","family"], "age": (6,10)},
    {"search": "Front Desk Kelly Yang", "goals": ["diversity","resilience","friendship"], "age": (8,13)},
    {"search": "The Name Jar Yangsook Choi", "goals": ["diversity","courage","friendship"], "age": (4,8)},
    {"search": "New Kid Jerry Craft graphic novel", "goals": ["diversity","friendship","courage"], "age": (8,12)},
    {"search": "Merci Suarez Changes Gears Meg Medina", "goals": ["diversity","family","friendship"], "age": (10,14)},
    {"search": "Hatchet Gary Paulsen", "goals": ["resilience","courage","environment"], "age": (9,13)},
    {"search": "A Long Walk to Water Linda Sue Park", "goals": ["resilience","history","courage"], "age": (9,13)},
    {"search": "The Great Gilly Hopkins Katherine Paterson", "goals": ["family","resilience","kindness"], "age": (8,12)},
    {"search": "From the Mixed-Up Files of Mrs. Basil E. Frankweiler", "goals": ["problem_solving","courage"], "age": (8,12)},
    {"search": "The Westing Game Ellen Raskin", "goals": ["problem_solving","diversity"], "age": (9,13)},
    {"search": "The Mysterious Benedict Society Trenton Lee Stewart", "goals": ["problem_solving","courage","friendship"], "age": (8,12)},
    {"search": "Encyclopedia Brown Donald Sobol", "goals": ["problem_solving","curiosity"], "age": (6,10)},
    {"search": "The Phantom Tollbooth Norton Juster", "goals": ["problem_solving","creativity","curiosity"], "age": (8,12)},
    {"search": "The Lorax Dr Seuss", "goals": ["environment","courage"], "age": (4,8)},
    {"search": "Watership Down Richard Adams", "goals": ["environment","resilience","friendship"], "age": (11,14)},
    {"search": "The Very Hungry Caterpillar Eric Carle", "goals": ["creativity","science"], "age": (2,5)},
    {"search": "Goodnight Moon Margaret Wise Brown", "goals": ["creativity","family"], "age": (0,4)},
    {"search": "Guess How Much I Love You Sam McBratney", "goals": ["family","kindness"], "age": (0,5)},
    {"search": "Chicka Chicka Boom Boom Bill Martin", "goals": ["creativity"], "age": (2,5)},
    {"search": "The Cat in the Hat Dr Seuss", "goals": ["creativity","problem_solving"], "age": (4,8)},
    {"search": "Green Eggs and Ham Dr Seuss", "goals": ["courage","resilience"], "age": (4,8)},
    {"search": "Corduroy Don Freeman", "goals": ["kindness","friendship"], "age": (2,6)},
    {"search": "Junie B Jones Barbara Park", "goals": ["friendship","problem_solving"], "age": (6,9)},
    {"search": "Magic Tree House Mary Pope Osborne", "goals": ["history","curiosity","friendship"], "age": (6,10)},
    {"search": "The Chronicles of Narnia C.S. Lewis", "goals": ["courage","friendship"], "age": (8,13)},
    {"search": "A Wrinkle in Time Madeleine L'Engle", "goals": ["science","courage","family"], "age": (9,13)},
    {"search": "Tuck Everlasting Natalie Babbitt", "goals": ["family","courage","resilience"], "age": (9,13)},
    {"search": "Wonder R.J. Palacio", "goals": ["kindness","courage","diversity"], "age": (8,13)},
    {"search": "The Giver Lois Lowry", "goals": ["courage","history","problem_solving"], "age": (11,14)},
]


def get_pg_url():
    url = os.getenv("DATABASE_URL", "")
    url = url.replace("postgresql+asyncpg://", "postgresql://")
    url = url.replace("postgres://", "postgresql://")
    return url


async def get_embedding(text):
    if VOYAGE_API_KEY:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                "https://api.voyageai.com/v1/embeddings",
                headers={"Authorization": f"Bearer {VOYAGE_API_KEY}"},
                json={"model": VOYAGE_MODEL, "input": [text]},
                timeout=30.0,
            )
            r.raise_for_status()
            return r.json()["data"][0]["embedding"][:DIMS]

    vector = []
    for i in range(DIMS):
        seed = hashlib.md5(f"{text}{i}".encode()).hexdigest()
        val = int(seed[:8], 16) / (16**8)
        vector.append(val * 2 - 1)
    magnitude = math.sqrt(sum(x**2 for x in vector))
    return [x / magnitude for x in vector]


async def search_open_library(query):
    async with httpx.AsyncClient() as client:
        r = await client.get(
            "https://openlibrary.org/search.json",
            params={
                "q": query, "limit": 5,
                "fields": "key,title,author_name,isbn,cover_i,first_publish_year,subject,number_of_pages_median"
            },
            timeout=20.0
        )
        r.raise_for_status()
        return r.json().get("docs", [])


async def add_missing_books():
    conn = await asyncpg.connect(get_pg_url())

    print("\n📚 Adding Missing Children's Books")
    print("─" * 50)

    added = 0
    already_exists = 0
    not_found = 0

    for book in MISSING_BOOKS:
        # First check if it exists by title
        existing = await conn.fetchrow(
            "SELECT id FROM books WHERE LOWER(title) LIKE LOWER($1) LIMIT 1",
            f"%{book['search'].split()[0]}%"
        )

        # More specific check
        words = book['search'].split()[:3]
        title_check = await conn.fetchrow("""
            SELECT id, title, learning_goals FROM books
            WHERE LOWER(title) LIKE LOWER($1)
            AND LOWER(title) LIKE LOWER($2)
            LIMIT 1
        """, f"%{words[0]}%", f"%{words[1]}%" if len(words) > 1 else "%")

        if title_check:
            # Update learning goals
            current = json.loads(title_check['learning_goals'] or '[]')
            new_goals = list(set(current + book['goals']))
            await conn.execute("""
                UPDATE books SET
                    learning_goals = $1::jsonb,
                    is_children_book = TRUE,
                    age_min = COALESCE(age_min, $2),
                    age_max = COALESCE(age_max, $3)
                WHERE id = $4
            """, json.dumps(new_goals), book['age'][0], book['age'][1], title_check['id'])
            print(f"  ✅ Updated: {title_check['title'][:45]}")
            already_exists += 1
            continue

        # Search Open Library
        try:
            results = await search_open_library(book['search'])
        except Exception as e:
            print(f"  ⚠️  Search failed for {book['search'][:40]}: {e}")
            not_found += 1
            continue

        if not results:
            print(f"  ❌ Not on Open Library: {book['search'][:45]}")
            not_found += 1
            continue

        # Try each result until we find one with ISBN
        inserted = False
        for raw in results:
            isbn_list = raw.get("isbn") or []
            isbn_13 = next((x for x in isbn_list if len(x) == 13), None)
            isbn_10 = next((x for x in isbn_list if len(x) == 10), None)

            if not isbn_13 and not isbn_10:
                continue

            # Check if already in DB by ISBN
            existing_isbn = await conn.fetchrow(
                "SELECT id, learning_goals FROM books WHERE isbn_13=$1 OR isbn_10=$2",
                isbn_13, isbn_10
            )

            if existing_isbn:
                current = json.loads(existing_isbn['learning_goals'] or '[]')
                new_goals = list(set(current + book['goals']))
                await conn.execute("""
                    UPDATE books SET
                        learning_goals = $1::jsonb,
                        is_children_book = TRUE,
                        age_min = COALESCE(age_min, $2),
                        age_max = COALESCE(age_max, $3)
                    WHERE id = $4
                """, json.dumps(new_goals), book['age'][0], book['age'][1], existing_isbn['id'])
                print(f"  ✅ Tagged existing: {raw.get('title','')[:45]}")
                already_exists += 1
                inserted = True
                break

            # Get embedding and insert
            try:
                text = f"Title: {raw.get('title','')}\nAuthor: {', '.join(raw.get('author_name') or ['Unknown'])}\nSubjects: {', '.join((raw.get('subject') or [])[:5])}"
                embedding = await get_embedding(text)
                cover_id = raw.get("cover_i")

                result = await conn.fetchval("""
                    INSERT INTO books (
                        isbn_13, isbn_10, title, author,
                        published_year, page_count, genres,
                        cover_url, embedding, language,
                        is_series, has_violence, has_scary_content,
                        has_adult_themes, age_min, age_max,
                        learning_goals, is_children_book
                    ) VALUES (
                        $1,$2,$3,$4,$5,$6,$7::jsonb,$8,$9::vector,
                        'en',false,false,false,false,$10,$11,
                        $12::jsonb,TRUE
                    )
                    ON CONFLICT DO NOTHING
                    RETURNING id
                """,
                    isbn_13, isbn_10,
                    raw.get("title", "Unknown"),
                    (raw.get("author_name") or ["Unknown"])[0],
                    raw.get("first_publish_year"),
                    raw.get("number_of_pages_median"),
                    json.dumps(raw.get("subject", [])[:10]),
                    f"https://covers.openlibrary.org/b/id/{cover_id}-L.jpg" if cover_id else None,
                    str(embedding),
                    book['age'][0], book['age'][1],
                    json.dumps(book['goals'])
                )

                if result:
                    print(f"  ➕ Added: {raw.get('title','')[:45]}")
                    added += 1
                    inserted = True
                    break

            except Exception as e:
                continue

        if not inserted:
            print(f"  ❌ Could not add: {book['search'][:45]}")
            not_found += 1

        await asyncio.sleep(0.3)

    total_children = await conn.fetchval(
        "SELECT COUNT(*) FROM books WHERE is_children_book = TRUE"
    )

    print(f"\n{'─' * 50}")
    print(f"➕ New books added: {added}")
    print(f"✅ Existing books tagged: {already_exists}")
    print(f"❌ Not found: {not_found}")
    print(f"📚 Total children's books: {total_children}")

    # Show goal counts
    print("\n📊 Books per learning goal:")
    goals = ["kindness","courage","friendship","emotions","science",
             "history","diversity","resilience","problem_solving",
             "environment","family","creativity"]
    for goal in goals:
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM books WHERE learning_goals::text LIKE $1 AND is_children_book = TRUE",
            f"%{goal}%"
        )
        bar = "█" * min(int(count or 0), 30)
        print(f"  {goal:20} {bar} {count or 0}")

    await conn.close()


if __name__ == "__main__":
    asyncio.run(add_missing_books())
