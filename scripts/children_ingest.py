"""
BookMind Children's Book Ingestion Script
Adds high-quality children's books with learning goal tags
"""
import asyncio
import os
import json
import hashlib
import math
import httpx
import asyncpg
from datetime import datetime

VOYAGE_API_KEY = os.getenv("VOYAGE_API_KEY", "")
VOYAGE_MODEL = "voyage-3"
DIMS = 1024

# ── Children's Book Queries by Learning Goal ──────────────────

CHILDREN_QUERIES = {
    "kindness": [
        "Wonder R.J. Palacio kindness bullying children",
        "Each Kindness Jacqueline Woodson picture book",
        "Enemy Pie Derek Munson friendship kindness",
        "The Invisible String Lori Karmel comfort",
        "Stand in My Shoes Bob Sornson empathy",
        "Last Stop on Market Street Matt de la Pena",
        "Those Shoes Maribeth Boelts wants needs",
        "Fly Away Home Eve Bunting homeless kindness",
        "The Recess Queen Alexis O'Neill bully kindness",
        "Chrysanthemum Kevin Henkes name teasing",
    ],
    "courage": [
        "Matilda Roald Dahl courage standing up",
        "Pippi Longstocking Astrid Lindgren independent",
        "The Paper Bag Princess Robert Munsch courage",
        "I Am Malala young readers courage education",
        "The One and Only Ivan Katherine Applegate",
        "Hatchet Gary Paulsen survival courage",
        "My Side of the Mountain Jean Craighead George",
        "Island of the Blue Dolphins courage survival",
        "The True Confessions Charlotte Doyle Avi adventure",
        "Harriet the Spy Louise Fitzhugh courage",
    ],
    "friendship": [
        "Charlotte's Web E.B. White friendship loyalty",
        "Frog and Toad Arnold Lobel friendship series",
        "Winnie the Pooh A.A. Milne friendship classic",
        "The Penderwicks Jeanne Birdsall sisters friendship",
        "Anne of Green Gables L.M. Montgomery friendship",
        "Bridge to Terabithia Katherine Paterson friendship loss",
        "Holes Louis Sachar friendship unlikely",
        "Because of Winn-Dixie Kate DiCamillo friendship dog",
        "The One and Only Bob friendship animals",
        "Hello Universe Erin Entrada Kelly friendship diverse",
    ],
    "emotions": [
        "In My Heart Jo Witek emotions picture book",
        "The Feelings Book Todd Parr emotions",
        "When Sophie Gets Angry Molly Bang emotions",
        "Grumpy Monkey Suzanne Lang emotions funny",
        "Listening to My Body Gabi Garcia emotions",
        "Scaredy Squirrel Melanie Watt anxiety funny",
        "Wilma Jean Worry Machine Julia Cook anxiety",
        "Wemberly Worried Kevin Henkes anxiety school",
        "Today I Feel Silly Jamie Lee Curtis emotions",
        "The Invisible String comfort anxiety separation",
    ],
    "science": [
        "Magic School Bus Joanna Cole science series",
        "National Geographic Kids science animals",
        "George's Secret Key Universe Stephen Hawking",
        "Hilo Judd Winick science fiction graphic",
        "The Wild Robot Peter Brown science nature",
        "Ada Twist Scientist Andrea Beaty STEM",
        "Rosie Revere Engineer Andrea Beaty STEM girls",
        "Iggy Peck Architect Andrea Beaty STEM",
        "Astrophysics for Young People in a Hurry",
        "Hidden Figures Young Readers STEM diverse",
    ],
    "history": [
        "Number the Stars Lois Lowry World War II",
        "Roll of Thunder Hear My Cry Mildred Taylor",
        "The Watsons Go to Birmingham Christopher Paul Curtis",
        "Inside Out and Back Again Thanhha Lai Vietnam",
        "When You Reach Me Rebecca Stead historical",
        "Bud Not Buddy Christopher Paul Curtis Depression",
        "Esperanza Rising Pam Munoz Ryan history",
        "The Giver Lois Lowry dystopia history",
        "Sarah Plain and Tall Patricia MacLachlan pioneer",
        "Little House Prairie Laura Ingalls Wilder history",
    ],
    "diversity": [
        "Front Desk Kelly Yang Chinese American",
        "The Name Jar Yangsook Choi Korean American",
        "Last Stop on Market Street diverse community",
        "Each Kindness diverse friendship",
        "Inside Out and Back Again Vietnamese refugee",
        "Merci Suarez Changes Gears Cuban American",
        "American Street Ibi Zoboi diverse immigrant",
        "Stamped Racism Antiracism You young readers",
        "Genesis Begins Again Alicia Williams diverse",
        "New Kid Jerry Craft graphic diverse school",
    ],
    "resilience": [
        "Hatchet Gary Paulsen survival resilience",
        "Holes Louis Sachar perseverance resilience",
        "The One and Only Ivan resilience freedom",
        "A Long Walk to Water Linda Sue Park survival",
        "Esperanza Rising resilience hope",
        "Bud Not Buddy resilience Depression era",
        "Inside Out and Back Again resilience refugee",
        "The Crossover Kwame Alexander resilience sports",
        "Ghost Jason Reynolds resilience running",
        "Restart Gordon Korman second chances resilience",
    ],
    "problem_solving": [
        "Encyclopedia Brown Donald Sobol mystery solving",
        "From the Mixed-Up Files Mrs Basil E Frankweiler",
        "The Westing Game Ellen Raskin mystery puzzle",
        "Chasing Vermeer Blue Balliet art mystery",
        "The Mysterious Benedict Society Trenton Lee Stewart",
        "Hilo robot science problem solving graphic",
        "Big Nate Lincoln Peirce problem solving funny",
        "Diary Wimpy Kid Jeff Kinney problem solving",
        "Flat Stanley Jeff Brown problem solving adventure",
        "Sideways Stories Wayside School Louis Sachar",
    ],
    "environment": [
        "The Wild Robot Peter Brown nature environment",
        "Island of the Blue Dolphins nature survival",
        "My Side of the Mountain nature environment",
        "Hoot Carl Hiaasen environment conservation",
        "Flush Carl Hiaasen water pollution environment",
        "The Lorax Dr Seuss environment classic",
        "Brundibár Tony Kushner nature community",
        "Seedfolks Paul Fleischman community garden",
        "The One and Only Ivan animals zoo",
        "Watership Down Richard Adams nature animals",
    ],
    "family": [
        "Little Women Louisa May Alcott family sisters",
        "Anne of Green Gables family belonging",
        "Because of Winn-Dixie family community",
        "Sarah Plain and Tall family pioneer",
        "The Penderwicks family sisters",
        "Little House Prairie family pioneer",
        "The Great Gilly Hopkins Katherine Paterson foster",
        "Babe the Gallant Pig Dick King-Smith family farm",
        "Stuart Little E.B. White family adventure",
        "Harriet the Spy family observation",
    ],
    "creativity": [
        "Harold and the Purple Crayon Crockett Johnson",
        "The Very Hungry Caterpillar Eric Carle creativity",
        "Where the Wild Things Are Maurice Sendak",
        "Cloudy Chance Meatballs Judi Barrett imagination",
        "James and the Giant Peach Roald Dahl imagination",
        "Charlie and the Chocolate Factory imagination",
        "The BFG Roald Dahl imagination",
        "Inkheart Cornelia Funke books creativity",
        "The Phantom Tollbooth Norton Juster wordplay",
        "The Neverending Story Michael Ende creativity",
    ],
    # Award winners — broad sweep
    "newbery": [
        "Newbery Medal winner children literature",
        "Newbery Honor book children award",
        "Caldecott Medal picture book award",
        "National Book Award Young People Literature",
        "Coretta Scott King Award children diversity",
    ],
    # Age-specific classics
    "picture_books": [
        "Goodnight Moon Margaret Wise Brown classic",
        "Guess How Much I Love You Sam McBratney",
        "The Very Hungry Caterpillar Eric Carle",
        "Where the Wild Things Are Maurice Sendak",
        "Chicka Chicka Boom Boom alphabet",
        "Dr Seuss Cat in the Hat classic",
        "Green Eggs and Ham Dr Seuss",
        "Corduroy Don Freeman classic bear",
        "Madeline Ludwig Bemelmans classic Paris",
        "Alexander and the Terrible Horrible No Good Very Bad Day",
    ],
    "early_readers": [
        "Frog and Toad early reader Arnold Lobel",
        "Biscuit Alyssa Satin Capucilli early reader",
        "Fly Guy Tedd Arnold early reader funny",
        "Elephant and Piggie Mo Willems early reader",
        "Junie B Jones Barbara Park early chapter",
        "Magic Tree House Mary Pope Osborne adventure",
        "Cam Jansen David Adler mystery early reader",
        "Nate the Great Marjorie Sharmat mystery",
        "Horrible Harry Suzy Kline school",
        "A to Z Mysteries Ron Roy mystery early",
    ],
    "middle_grade": [
        "Percy Jackson Rick Riordan mythology adventure",
        "Harry Potter J.K. Rowling fantasy magic",
        "The Chronicles of Narnia C.S. Lewis fantasy",
        "A Wrinkle in Time Madeleine L'Engle sci-fi",
        "The Giver Lois Lowry dystopia",
        "Treasure Island Robert Louis Stevenson adventure",
        "The Secret Garden Frances Hodgson Burnett",
        "The Phantom Tollbooth Norton Juster wordplay",
        "From the Mixed-Up Files Frankweiler mystery",
        "Tuck Everlasting Natalie Babbitt fantasy",
    ],
}

# Learning goal tags for search terms
GOAL_TAGS = {
    "kindness": ["kindness", "empathy", "friendship"],
    "courage": ["courage", "confidence", "bravery"],
    "friendship": ["friendship", "loyalty", "belonging"],
    "emotions": ["emotions", "feelings", "mental health"],
    "science": ["science", "STEM", "nature", "curiosity"],
    "history": ["history", "culture", "social justice"],
    "diversity": ["diversity", "inclusion", "representation"],
    "resilience": ["resilience", "perseverance", "grit"],
    "problem_solving": ["problem solving", "critical thinking"],
    "environment": ["environment", "nature", "conservation"],
    "family": ["family", "relationships", "belonging"],
    "creativity": ["creativity", "imagination", "art"],
    "newbery": ["award winner", "literary excellence"],
    "picture_books": ["picture books", "early childhood"],
    "early_readers": ["early readers", "beginning chapter books"],
    "middle_grade": ["middle grade", "ages 8-12"],
}

# Age ranges by category
AGE_RANGES = {
    "picture_books": (2, 6),
    "early_readers": (5, 9),
    "middle_grade": (8, 13),
    "kindness": (4, 12),
    "courage": (4, 14),
    "friendship": (4, 14),
    "emotions": (3, 10),
    "science": (5, 14),
    "history": (8, 14),
    "diversity": (4, 14),
    "resilience": (7, 14),
    "problem_solving": (6, 14),
    "environment": (4, 14),
    "family": (4, 14),
    "creativity": (3, 12),
    "newbery": (6, 14),
}


def get_pg_url():
    url = os.getenv("DATABASE_URL", "")
    url = url.replace("postgresql+asyncpg://", "postgresql://")
    url = url.replace("postgres://", "postgresql://")
    return url


async def get_embeddings_batch(texts):
    if VOYAGE_API_KEY:
        for attempt in range(3):
            try:
                async with httpx.AsyncClient() as client:
                    r = await client.post(
                        "https://api.voyageai.com/v1/embeddings",
                        headers={"Authorization": f"Bearer {VOYAGE_API_KEY}",
                                "Content-Type": "application/json"},
                        json={"model": VOYAGE_MODEL, "input": texts},
                        timeout=60.0,
                    )
                    r.raise_for_status()
                    return [item["embedding"][:DIMS] for item in r.json()["data"]]
            except Exception as e:
                if attempt == 2:
                    raise
                await asyncio.sleep((attempt + 1) * 3)

    # Fallback
    results = []
    for text in texts:
        vector = []
        for i in range(DIMS):
            seed = hashlib.md5(f"{text}{i}".encode()).hexdigest()
            val = int(seed[:8], 16) / (16**8)
            vector.append(val * 2 - 1)
        magnitude = math.sqrt(sum(x**2 for x in vector))
        results.append([x / magnitude for x in vector])
    return results


async def search_open_library(query: str, limit: int = 20):
    async with httpx.AsyncClient() as client:
        r = await client.get(
            "https://openlibrary.org/search.json",
            params={
                "q": query,
                "limit": limit,
                "fields": "key,title,author_name,isbn,cover_i,first_publish_year,subject,number_of_pages_median"
            },
            timeout=20.0
        )
        r.raise_for_status()
        return r.json().get("docs", [])


async def ensure_children_columns(conn):
    """Add learning_goals column if it doesn't exist"""
    try:
        await conn.execute("""
            ALTER TABLE books
            ADD COLUMN IF NOT EXISTS learning_goals JSONB DEFAULT '[]'::jsonb
        """)
        await conn.execute("""
            ALTER TABLE books
            ADD COLUMN IF NOT EXISTS parent_note TEXT
        """)
        await conn.execute("""
            ALTER TABLE books
            ADD COLUMN IF NOT EXISTS is_children_book BOOLEAN DEFAULT FALSE
        """)
        print("✅ Children's columns ready")
    except Exception as e:
        print(f"⚠️ Column check: {e}")


async def ingest_children_query(conn, query: str, goal: str, limit: int = 20) -> int:
    """Ingest children's books for a specific learning goal"""
    try:
        raw_books = await search_open_library(query, limit)
    except Exception as e:
        print(f"    ⚠️ Search failed: {e}")
        return 0

    to_process = []
    for raw in raw_books:
        isbn_list = raw.get("isbn") or []
        isbn_13 = next((x for x in isbn_list if len(x) == 13), None)
        isbn_10 = next((x for x in isbn_list if len(x) == 10), None)
        if not isbn_13 and not isbn_10:
            continue
        to_process.append((raw, isbn_13, isbn_10))

    if not to_process:
        return 0

    ingested = 0
    batch_size = 10
    age_range = AGE_RANGES.get(goal, (4, 14))
    goal_tags = GOAL_TAGS.get(goal, [goal])

    for batch_start in range(0, len(to_process), batch_size):
        batch = to_process[batch_start:batch_start + batch_size]
        texts = []
        for raw, _, _ in batch:
            text = (
                f"Title: {raw.get('title', '')}\n"
                f"Author: {', '.join(raw.get('author_name') or ['Unknown'])}\n"
                f"Subjects: {', '.join((raw.get('subject') or [])[:8])}\n"
                f"Learning: {', '.join(goal_tags)}\n"
                f"Age: {age_range[0]}-{age_range[1]}"
            )
            texts.append(text)

        try:
            embeddings = await get_embeddings_batch(texts)
        except Exception as e:
            print(f"    ❌ Embedding failed: {e}")
            continue

        for (raw, isbn_13, isbn_10), embedding in zip(batch, embeddings):
            try:
                cover_id = raw.get("cover_i")
                    # Check if book exists in main books table
                existing = await conn.fetchrow("""
                    SELECT id, learning_goals FROM books 
                    WHERE isbn_13=$1 OR isbn_10=$2
                """, isbn_13, isbn_10)

                if existing:
                    # Update learning goals for existing book
                    current_goals = json.loads(existing['learning_goals'] or '[]')
                    if goal not in current_goals:
                        current_goals.append(goal)
                        await conn.execute("""
                            UPDATE books SET
                                learning_goals = $1::jsonb,
                                is_children_book = TRUE,
                                age_min = COALESCE(age_min, $2),
                                age_max = COALESCE(age_max, $3)
                            WHERE id = $4
                        """, json.dumps(current_goals), age_range[0], age_range[1], existing['id'])
                        ingested += 1
                else:
                    # Insert new book directly into books table
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
                        age_range[0],
                        age_range[1],
                        json.dumps([goal])
                    )
                    if result:
                        ingested += 1

            except Exception as e:
                continue

    return ingested


async def run_children_ingest():
    """Run full children's book ingestion"""
    pg_url = get_pg_url()
    conn = await asyncpg.connect(pg_url)

    print("\n🧒 BookMind Children's Book Ingestion")
    print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("─" * 50)

    await ensure_children_columns(conn)

    total_new = 0
    total_updated = 0

    before = await conn.fetchval(
        "SELECT COUNT(*) FROM books WHERE is_children_book = TRUE"
    ) or 0

    for goal, queries in CHILDREN_QUERIES.items():
        print(f"\n🎯 Learning Goal: {goal.upper()}")
        goal_total = 0

        for query in queries:
            print(f"  🔍 '{query[:50]}...' " if len(query) > 50 else f"  🔍 '{query}'")
            new = await ingest_children_query(conn, query, goal, limit=15)
            goal_total += new
            await asyncio.sleep(0.5)  # Be nice to Open Library

        print(f"  ✅ {goal_total} books added/updated for {goal}")
        total_new += goal_total

    after = await conn.fetchval(
        "SELECT COUNT(*) FROM books WHERE is_children_book = TRUE"
    ) or 0

    total = await conn.fetchval("SELECT COUNT(*) FROM books") or 0

    await conn.close()

    print(f"\n{'─' * 50}")
    print(f"✅ Children's ingestion complete!")
    print(f"📚 Children's books: {before} → {after} (+{after - before})")
    print(f"📖 Total books in database: {total}")
    print(f"🎯 Learning goals tagged: {len(CHILDREN_QUERIES)}")


if __name__ == "__main__":
    asyncio.run(run_children_ingest())
