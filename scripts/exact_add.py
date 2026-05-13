"""
Add missing children's books using exact Open Library title search
"""
import asyncio
import os
import json
import hashlib
import math
import httpx
import asyncpg

VOYAGE_API_KEY = os.getenv("VOYAGE_API_KEY", "")
DIMS = 1024

MISSING = [
    ("Each Kindness", "Woodson", ["kindness","diversity"], (4,8)),
    ("Enemy Pie", "Munson", ["kindness","friendship"], (4,8)),
    ("Last Stop on Market Street", "de la Pena", ["kindness","diversity"], (4,8)),
    ("Chrysanthemum", "Henkes", ["kindness","friendship"], (4,8)),
    ("Pippi Longstocking", "Lindgren", ["courage","creativity"], (6,10)),
    ("Harriet the Spy", "Fitzhugh", ["courage","creativity"], (8,12)),
    ("The One and Only Ivan", "Applegate", ["courage","resilience"], (8,12)),
    ("Charlotte's Web", "White", ["friendship","kindness","resilience"], (7,11)),
    ("Frog and Toad Are Friends", "Lobel", ["friendship","kindness"], (4,8)),
    ("Because of Winn-Dixie", "DiCamillo", ["friendship","family","resilience"], (7,11)),
    ("Bridge to Terabithia", "Paterson", ["friendship","courage","resilience"], (9,13)),
    ("The Magic School Bus", "Cole", ["science","curiosity"], (5,9)),
    ("Ada Twist Scientist", "Beaty", ["science","courage"], (4,8)),
    ("Rosie Revere Engineer", "Beaty", ["science","courage"], (4,8)),
    ("My Side of the Mountain", "George", ["environment","resilience"], (9,13)),
    ("Island of the Blue Dolphins", "O'Dell", ["environment","resilience","courage"], (9,13)),
    ("Number the Stars", "Lowry", ["history","courage","kindness"], (9,13)),
    ("Roll of Thunder Hear My Cry", "Taylor", ["history","diversity","resilience"], (9,13)),
    ("The Watsons Go to Birmingham", "Curtis", ["history","diversity","family"], (8,12)),
    ("Inside Out and Back Again", "Lai", ["history","diversity","resilience"], (8,12)),
    ("Esperanza Rising", "Ryan", ["history","diversity","resilience"], (9,13)),
    ("Bud Not Buddy", "Curtis", ["history","resilience","family"], (8,12)),
    ("Sarah Plain and Tall", "MacLachlan", ["history","family"], (6,10)),
    ("Front Desk", "Yang", ["diversity","resilience","friendship"], (8,13)),
    ("The Name Jar", "Choi", ["diversity","courage","friendship"], (4,8)),
    ("New Kid", "Craft", ["diversity","friendship","courage"], (8,12)),
    ("Merci Suarez Changes Gears", "Medina", ["diversity","family","friendship"], (10,14)),
    ("Hatchet", "Paulsen", ["resilience","courage","environment"], (9,13)),
    ("A Long Walk to Water", "Park", ["resilience","history","courage"], (9,13)),
    ("The Westing Game", "Raskin", ["problem_solving","diversity"], (9,13)),
    ("Encyclopedia Brown", "Sobol", ["problem_solving","curiosity"], (6,10)),
    ("The Phantom Tollbooth", "Juster", ["problem_solving","creativity"], (8,12)),
    ("The Lorax", "Seuss", ["environment","courage"], (4,8)),
    ("Watership Down", "Adams", ["environment","resilience","friendship"], (11,14)),
    ("The Very Hungry Caterpillar", "Carle", ["creativity","science"], (2,5)),
    ("Goodnight Moon", "Brown", ["creativity","family"], (0,4)),
    ("Guess How Much I Love You", "McBratney", ["family","kindness"], (0,5)),
    ("The Cat in the Hat", "Seuss", ["creativity","problem_solving"], (4,8)),
    ("Green Eggs and Ham", "Seuss", ["courage","resilience"], (4,8)),
    ("Corduroy", "Freeman", ["kindness","friendship"], (2,6)),
    ("Junie B Jones", "Park", ["friendship","problem_solving"], (6,9)),
    ("Magic Tree House", "Osborne", ["history","curiosity","friendship"], (6,10)),
    ("The Chronicles of Narnia", "Lewis", ["courage","friendship"], (8,13)),
    ("A Wrinkle in Time", "L'Engle", ["science","courage","family"], (9,13)),
    ("Tuck Everlasting", "Babbitt", ["family","courage","resilience"], (9,13)),
    ("Wonder", "Palacio", ["kindness","courage","diversity"], (8,13)),
    ("The Mysterious Benedict Society", "Stewart", ["problem_solving","courage","friendship"], (8,12)),
    ("The Great Gilly Hopkins", "Paterson", ["family","resilience","kindness"], (8,12)),
    ("From the Mixed-Up Files", "Konigsburg", ["problem_solving","courage","creativity"], (8,12)),
    ("Chicka Chicka Boom Boom", "Martin", ["creativity"], (2,5)),
    ("Pippi Longstocking", "Lindgren", ["courage","creativity"], (6,10)),
]

def get_pg_url():
    url = os.getenv("DATABASE_URL", "")
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
        except:
            pass
    vector = []
    for i in range(DIMS):
        seed = hashlib.md5(f"{text}{i}".encode()).hexdigest()
        val = int(seed[:8], 16) / (16**8)
        vector.append(val * 2 - 1)
    magnitude = math.sqrt(sum(x**2 for x in vector))
    return [x / magnitude for x in vector]

async def search_by_title(title, author):
    """Search Open Library with title and author separately for better results"""
    async with httpx.AsyncClient() as client:
        # Try title + author search
        r = await client.get(
            "https://openlibrary.org/search.json",
            params={
                "title": title,
                "author": author,
                "limit": 5,
                "fields": "key,title,author_name,isbn,cover_i,first_publish_year,subject,number_of_pages_median"
            },
            timeout=20.0
        )
        r.raise_for_status()
        docs = r.json().get("docs", [])
        
        # Filter to books with ISBNs
        with_isbn = [d for d in docs if d.get("isbn")]
        return with_isbn if with_isbn else docs

async def run():
    conn = await asyncpg.connect(get_pg_url())
    print("\n📚 Adding Missing Children's Books (Exact Search)")
    print("─" * 55)

    added = 0
    tagged = 0
    failed = 0

    for title, author, goals, age in MISSING:
        # Check if already exists by exact title
        existing = await conn.fetchrow("""
            SELECT id, title, learning_goals FROM books
            WHERE LOWER(title) = LOWER($1)
            LIMIT 1
        """, title)

        if not existing:
            # Try partial match with author hint
            existing = await conn.fetchrow("""
                SELECT id, title, learning_goals FROM books
                WHERE LOWER(title) LIKE LOWER($1)
                AND LOWER(author) LIKE LOWER($2)
                LIMIT 1
            """, f"%{title.split()[0]}%", f"%{author.split()[0]}%")

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
            results = await search_by_title(title, author)
        except Exception as e:
            print(f"  ⚠️  Search error for '{title}': {e}")
            failed += 1
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
                    age_min=COALESCE(age_min,$2), age_max=COALESCE(age_max,$3)
                    WHERE id=$4
                """, json.dumps(new_goals), age[0], age[1], by_isbn['id'])
                print(f"  ✅ Tagged:  {raw.get('title','')[:50]}")
                tagged += 1
                inserted = True
                break

            # Insert new
            try:
                text = f"Title: {raw.get('title','')}\nAuthor: {', '.join(raw.get('author_name') or ['Unknown'])}"
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
                    raw.get("title","Unknown"),
                    (raw.get("author_name") or ["Unknown"])[0],
                    raw.get("first_publish_year"),
                    raw.get("number_of_pages_median"),
                    json.dumps(raw.get("subject",[])[:10]),
                    f"https://covers.openlibrary.org/b/id/{cover_id}-L.jpg" if cover_id else None,
                    str(emb), age[0], age[1], json.dumps(goals)
                )
                if result:
                    print(f"  ➕ Added:   {raw.get('title','')[:50]}")
                    added += 1
                    inserted = True
                    break
            except Exception as e:
                continue

        if not inserted:
            print(f"  ❌ Failed:  {title} — {author}")
            failed += 1

        await asyncio.sleep(0.5)

    total = await conn.fetchval("SELECT COUNT(*) FROM books WHERE is_children_book=TRUE")
    print(f"\n{'─'*55}")
    print(f"➕ Added: {added}  ✅ Tagged: {tagged}  ❌ Failed: {failed}")
    print(f"📚 Total children's books: {total}")

    print("\n📊 Books per learning goal:")
    for goal in ["kindness","courage","friendship","emotions","science",
                 "history","diversity","resilience","problem_solving",
                 "environment","family","creativity"]:
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM books WHERE learning_goals::text LIKE $1 AND is_children_book=TRUE",
            f"%{goal}%"
        ) or 0
        bar = "█" * min(count, 25)
        print(f"  {goal:20} {bar} {count}")

    await conn.close()

if __name__ == "__main__":
    asyncio.run(run())
