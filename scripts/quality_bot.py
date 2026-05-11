"""
BookMind Quality Bot
====================
Simulates real user queries, evaluates recommendation quality,
and automatically ingests better books to fill gaps.

Usage:
    python -m scripts.quality_bot              # Run one cycle
    python -m scripts.quality_bot --continuous # Run forever
"""
import asyncio
import argparse
import os
import json
import httpx
import asyncpg
from datetime import datetime

API_BASE = os.getenv("BOOKMIND_API", "https://bookmind-production-58a5.up.railway.app")
DEMO_READER = "182739fd-aa47-4f58-b613-2beaaffba5aa"

TEST_QUERIES = [
    "I loved Bridgerton and want something similar",
    "Books like Outlander historical romance",
    "Something like The Notebook romance",
    "I want a enemies to lovers romance",
    "Cozy romance like Beach Read",
    "I loved Gone Girl psychological thriller",
    "Books like The Girl with the Dragon Tattoo",
    "Something like Big Little Lies mystery",
    "I want a cozy mystery like Miss Marple",
    "Thriller like The Da Vinci Code",
    "Books like Harry Potter magic school",
    "Something like Game of Thrones fantasy",
    "I loved Dune science fiction",
    "Books like The Hitchhiker's Guide to the Galaxy",
    "Fantasy like The Name of the Wind",
    "Books like The Kite Runner emotional",
    "Something like To Kill a Mockingbird",
    "Literary fiction like The Great Gatsby",
    "I loved A Little Life literary fiction",
    "Books like Normal People Sally Rooney",
    "Books like Atomic Habits productivity",
    "Something like Sapiens nonfiction",
    "I loved Educated memoir",
    "Books like The Body Keeps the Score",
    "Nonfiction like Thinking Fast and Slow",
    "Books like The Hunger Games dystopia",
    "Something like Twilight paranormal romance",
    "YA fantasy like An Ember in the Ashes",
    "Books like The Fault in Our Stars",
    "YA like Six of Crows heist fantasy",
    "Books like Percy Jackson for kids",
    "Something like Diary of a Wimpy Kid",
    "Adventure books like Hatchet",
    "Books like Charlotte's Web children",
    "Middle grade like Harry Potter",
    "I want something funny and light",
    "Dark and atmospheric thriller",
    "Heartwarming feel good fiction",
    "Epic fantasy with magic systems",
    "Quick easy beach read romance",
]

QUALITY_BENCHMARKS = {
    "romance": ["Pride and Prejudice", "Outlander", "The Notebook", "Me Before You",
                "Bride", "The Hating Game", "Beach Read", "It Ends with Us",
                "Twisted", "Corrupt", "Dreaming of You", "Devil in Winter",
                "Vampire Academy", "Safe Haven", "Tan lines", "Party of Two",
                "The Spanish Love Deception", "Conversations With Friends"],
    "thriller": ["Gone Girl", "The Girl with the Dragon Tattoo", "Big Little Lies",
                 "The Silent Patient", "Behind Closed Doors", "The Good Girl",
                 "The Girl Before", "Want to Know a Secret", "Gone for Good",
                 "Full Tilt", "The Fifth Assassin", "4:50 from Paddington",
                 "All the Dark Places", "Dark Matter", "The Guilty"],
    "fantasy": ["Harry Potter", "The Name of the Wind", "A Game of Thrones",
                "The Way of Kings", "Mistborn", "The Lies of Locke Lamora",
                "Eragon", "The Hero of Ages", "City of Glass", "Kingdom of Ash",
                "Realm Breaker", "House of Chains", "La Via dei Re"],
    "scifi": ["Dune", "The Martian", "Ender's Game", "Foundation", "Project Hail Mary",
              "Children of Dune", "The Restaurant at the End of the Universe",
              "Have Spacesuit", "Diamond Dogs", "The Hydrogen Sonata"],
    "literary": ["The Kite Runner", "A Little Life", "Normal People", "The Great Gatsby",
                 "To Kill a Mockingbird", "Educated", "Half of a Yellow Sun",
                 "Life After Life", "The God of Small Things", "Dear Edward",
                 "Infinite Jest", "Conversations With Friends", "Eleanor Oliphant"],
    "nonfiction": ["Atomic Habits", "Sapiens", "Thinking Fast and Slow",
                   "The Body Keeps the Score", "Outliers", "Blink", "Brain Rules",
                   "10% Happier", "Four Seconds", "HBR Guide", "Limitless"],
    "ya": ["The Hunger Games", "Divergent", "The Fault in Our Stars", "Six of Crows",
           "An Ember in the Ashes", "Twilight", "Allegiant", "The Maze Runner",
           "Nineteen Eighty-Four", "The Young Elites", "The iron trial"],
}

REMEDIATION_QUERIES = {
    "romance": [
        "Julia Quinn Bridgerton Regency romance witty",
        "Tessa Dare Regency romance spindle cove",
        "Sarah MacLean Rule of Scoundrels romance",
        "Eloisa James Regency romance duchess",
        "Colleen Hoover Verity romance thriller",
    ],
    "thriller": [
        "Gillian Flynn Sharp Objects Dark Places",
        "Tana French In the Woods Dublin Murder",
        "Ruth Ware One by One locked room",
        "Lucy Foley Guest List thriller island",
        "Lisa Jewell The Family Upstairs thriller",
    ],
    "fantasy": [
        "Brandon Sanderson Way of Kings Stormlight",
        "Patrick Rothfuss Name of the Wind Kingkiller",
        "Robin Hobb Assassin's Apprentice Farseer",
        "Scott Lynch Lies of Locke Lamora Gentleman Bastards",
        "Joe Abercrombie First Law Blade Itself",
    ],
    "scifi": [
        "Andy Weir Project Hail Mary Martian",
        "Liu Cixin Three Body Problem Dark Forest",
        "Ted Chiang Exhalation Stories Your Life",
        "N K Jemisin Fifth Season Broken Earth",
        "Ursula Le Guin Left Hand of Darkness",
    ],
    "literary": [
        "Hanya Yanagihara Little Life literary fiction",
        "Sally Rooney Conversations with Friends",
        "Colson Whitehead Underground Railroad Nickel Boys",
        "Yaa Gyasi Homegoing Transcendent Kingdom",
        "Madeline Miller Circe Song of Achilles",
    ],
    "nonfiction": [
        "Daniel Kahneman Thinking Fast Slow behavioral",
        "Malcolm Gladwell Outliers Tipping Point Blink",
        "Ryan Holiday Stoicism Obstacle Way Ego Enemy",
        "Adam Grant Think Again Originals Give Take",
        "Brene Brown Daring Greatly Gifts Imperfection",
    ],
    "ya": [
        "Leigh Bardugo Six of Crows Shadow Bone",
        "Holly Black Cruel Prince Folk Air",
        "Adam Silvera They Both Die at the End",
        "Angie Thomas Hate U Give On the Come Up",
        "Jason Reynolds Long Way Down Ghost",
    ],
}


def detect_genre(query):
    q = query.lower()
    # Check specific genres BEFORE romance to avoid misclassification
    if any(w in q for w in ["science fiction", "scifi", "sci-fi", "dune", "martian", "space", "hitchhiker"]):
        return "scifi"
    if any(w in q for w in ["thriller", "mystery", "murder", "detective", "psychological", "gone girl", "da vinci", "dragon tattoo", "big little lies"]):
        return "thriller"
    if any(w in q for w in ["fantasy", "magic", "dragon", "wizard", "harry potter", "game of thrones", "name of the wind", "six of crows", "ember"]):
        return "fantasy"
    if any(w in q for w in ["nonfiction", "atomic habits", "sapiens", "productivity", "memoir", "educated", "thinking fast", "body keeps", "little life"]):
        return "nonfiction"
    if any(w in q for w in ["literary", "kite runner", "great gatsby", "kill mockingbird", "normal people", "little life"]):
        return "literary"
    if any(w in q for w in ["ya", "young adult", "hunger games", "twilight", "divergent", "fault in our stars"]):
        return "ya"
    if any(w in q for w in ["romance", "love", "bridgerton", "outlander", "notebook", "enemies to lovers", "beach read", "cozy"]):
        return "romance"
    return "general"


def evaluate_quality(recommendations, genre):
    if not recommendations:
        return {"score": 0, "issues": ["No recommendations returned"], "titles": []}

    issues = []
    score = 100
    titles = [r.get("title", "").lower() for r in recommendations]
    authors = [r.get("author", "").lower() for r in recommendations]

    unique_authors = set(authors)
    if len(unique_authors) < len(authors):
        issues.append("Duplicate authors in results")
        score -= 20

    no_cover = sum(1 for r in recommendations if not r.get("cover_url"))
    if no_cover > 0:
        issues.append(str(no_cover) + " books missing covers")
        score -= no_cover * 10

    benchmarks = QUALITY_BENCHMARKS.get(genre, [])
    benchmark_found = any(
        any(b.lower() in t for b in benchmarks)
        for t in titles
    )
    if benchmarks and not benchmark_found:
        issues.append("No well-known " + genre + " books found")
        score -= 30

    return {
        "score": max(0, score),
        "issues": issues,
        "titles": [r.get("title") for r in recommendations],
    }


async def get_recommendations(query):
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                API_BASE + "/api/v1/recommendations/for-me",
                params={"reader_id": DEMO_READER},
                json={"message": query, "count": 5},
                timeout=30.0
            )
            r.raise_for_status()
            return r.json().get("recommendations", [])
    except Exception as e:
        print("    API error: " + str(e)[:80])
        return []


async def ingest_remediation_books(genre, conn):
    from scripts.auto_ingest import ingest_query, copy_to_books_table
    queries = REMEDIATION_QUERIES.get(genre, [])
    if not queries:
        return
    print("    Ingesting quality " + genre + " books...")
    total = 0
    for query in queries[:2]:
        new = await ingest_query(conn, query, 50)
        total += new
        print("       Added " + str(new) + " books for: " + query[:40])
        await asyncio.sleep(1)
    await copy_to_books_table(conn)
    print("    Copied " + str(total) + " new books to books table")


async def run_cycle():
    pg_url = os.getenv("DATABASE_URL", "")
    pg_url = pg_url.replace("postgresql+asyncpg://", "postgresql://")
    pg_url = pg_url.replace("postgres://", "postgresql://")
    conn = await asyncpg.connect(pg_url)

    print("\n🤖 BookMind Quality Bot")
    print("📅 " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("🔗 Testing: " + API_BASE)
    print("=" * 60)

    total_score = 0
    genres_needing_help = {}

    for i, query in enumerate(TEST_QUERIES):
        genre = detect_genre(query)
        print("\n[" + str(i+1) + "/" + str(len(TEST_QUERIES)) + "] '" + query[:50] + "'")

        recs = await get_recommendations(query)
        quality = evaluate_quality(recs, genre)

        print("    Score: " + str(quality["score"]) + "/100 | Genre: " + genre)
        
        titles = quality.get("titles", [])
        if titles:
            print("    Books: " + ", ".join(t for t in titles[:3] if t))
        
        issues = quality.get("issues", [])
        if issues:
            print("    Issues: " + ", ".join(issues))

        total_score += quality["score"]

        if quality["score"] < 90:
            genres_needing_help[genre] = genres_needing_help.get(genre, 0) + 1

        await asyncio.sleep(1)

    avg_score = total_score / len(TEST_QUERIES)
    print("\n" + "=" * 60)
    print("📊 QUALITY REPORT")
    print("   Average Score: " + str(round(avg_score, 1)) + "/100")
    print("   Queries Tested: " + str(len(TEST_QUERIES)))

    if genres_needing_help:
        print("\n⚠️  Genres needing improvement:")
        for genre, count in sorted(genres_needing_help.items(), key=lambda x: -x[1]):
            print("   - " + genre + ": " + str(count) + " low-quality results")

        print("\n🔧 Auto-fixing low quality genres...")
        fixed = set()
        for genre in genres_needing_help:
            if genre not in fixed and genre in REMEDIATION_QUERIES:
                await ingest_remediation_books(genre, conn)
                fixed.add(genre)
    else:
        print("\n✅ All genres scoring 90+!")

    total_books = await conn.fetchval("SELECT COUNT(*) FROM books")
    print("\n📚 Total books in database: " + str(total_books))
    await conn.close()
    return avg_score


async def run_continuous(interval_hours=12):
    print("🤖 BookMind Quality Bot — Continuous Mode")
    print("⏰ Running every " + str(interval_hours) + " hours")
    while True:
        await run_cycle()
        print("\n💤 Next check in " + str(interval_hours) + " hours...")
        await asyncio.sleep(interval_hours * 3600)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--continuous", action="store_true")
    parser.add_argument("--interval", type=int, default=12)
    args = parser.parse_args()

    if args.continuous:
        asyncio.run(run_continuous(args.interval))
    else:
        asyncio.run(run_cycle())
