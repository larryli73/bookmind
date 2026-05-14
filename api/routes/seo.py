"""
BookMind Programmable SEO
Auto-generates hundreds of landing pages targeting real Google searches
Add to api/routes/seo.py and register in main.py
"""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
import asyncpg
import os
import json

router = APIRouter()

DB_URL = os.getenv("DATABASE_URL", "").replace("postgresql+asyncpg://", "postgresql://").replace("postgres://", "postgresql://")

# ── Page Definitions ──────────────────────────────────────────

LEARNING_GOALS = {
    "kindness":         {"label": "Kindness & Empathy",    "emoji": "❤️",  "desc": "teach children to be kind, caring, and empathetic toward others"},
    "courage":          {"label": "Courage & Confidence",  "emoji": "💪",  "desc": "build bravery, self-confidence, and the courage to try new things"},
    "friendship":       {"label": "Friendship",             "emoji": "🤝",  "desc": "explore what it means to be a good friend and build lasting relationships"},
    "emotions":         {"label": "Managing Emotions",      "emoji": "🧠",  "desc": "help children understand and manage their feelings in healthy ways"},
    "science":          {"label": "Science & Nature",       "emoji": "🔬",  "desc": "spark curiosity about the natural world, science, and discovery"},
    "history":          {"label": "History & Culture",      "emoji": "🌍",  "desc": "bring history alive and explore different cultures around the world"},
    "diversity":        {"label": "Diversity & Inclusion",  "emoji": "🌈",  "desc": "celebrate differences and teach children about inclusion and representation"},
    "resilience":       {"label": "Resilience & Grit",     "emoji": "🌟",  "desc": "build perseverance, grit, and the ability to bounce back from challenges"},
    "problem-solving":  {"label": "Problem Solving",        "emoji": "🧩",  "desc": "develop critical thinking and creative problem-solving skills"},
    "environment":      {"label": "Environment & Nature",   "emoji": "🌿",  "desc": "build love for the natural world and environmental awareness"},
    "family":           {"label": "Family & Relationships", "emoji": "🏠",  "desc": "explore family bonds, belonging, and the importance of relationships"},
    "creativity":       {"label": "Creativity & Imagination","emoji": "🎨", "desc": "spark imagination and creative thinking in young minds"},
}

AGE_GROUPS = {
    "3": {"label": "3-Year-Olds", "min": 2, "max": 4, "type": "Picture Books", "reader": "read aloud together"},
    "4": {"label": "4-Year-Olds", "min": 3, "max": 5, "type": "Picture Books", "reader": "read aloud together"},
    "5": {"label": "5-Year-Olds", "min": 4, "max": 6, "type": "Picture Books & Early Readers", "reader": "read aloud or with help"},
    "6": {"label": "6-Year-Olds", "min": 5, "max": 7, "type": "Early Readers", "reader": "read with some help"},
    "7": {"label": "7-Year-Olds", "min": 6, "max": 8, "type": "Early Chapter Books", "reader": "read with some help"},
    "8": {"label": "8-Year-Olds", "min": 7, "max": 9, "type": "Chapter Books", "reader": "read independently"},
    "9": {"label": "9-Year-Olds", "min": 8, "max": 10, "type": "Middle Grade", "reader": "read independently"},
    "10": {"label": "10-Year-Olds", "min": 9, "max": 11, "type": "Middle Grade", "reader": "read independently"},
    "11": {"label": "11-Year-Olds", "min": 10, "max": 12, "type": "Middle Grade", "reader": "read independently"},
    "12": {"label": "12-Year-Olds", "min": 11, "max": 13, "type": "Middle Grade / Tween", "reader": "read independently"},
}

ADULT_GENRES = {
    "thriller": {"label": "Thriller", "emoji": "🔪", "desc": "gripping, suspenseful stories that keep you on the edge of your seat"},
    "mystery": {"label": "Mystery", "emoji": "🔍", "desc": "puzzling whodunits and detective stories full of twists"},
    "fantasy": {"label": "Fantasy", "emoji": "⚡", "desc": "magical worlds, epic quests, and extraordinary adventures"},
    "romance": {"label": "Romance", "emoji": "💕", "desc": "heartwarming love stories with satisfying happy endings"},
    "science-fiction": {"label": "Science Fiction", "emoji": "🚀", "desc": "mind-expanding stories about technology, space, and the future"},
    "literary-fiction": {"label": "Literary Fiction", "emoji": "📖", "desc": "beautifully written stories that explore the human condition"},
    "historical-fiction": {"label": "Historical Fiction", "emoji": "🏛️", "desc": "vivid stories set in fascinating periods of history"},
    "horror": {"label": "Horror", "emoji": "👻", "desc": "chilling stories that will keep you up at night"},
    "nonfiction": {"label": "Nonfiction", "emoji": "📚", "desc": "fascinating true stories about real people, events, and ideas"},
    "self-help": {"label": "Self-Help", "emoji": "🌱", "desc": "practical books to help you grow, improve, and live better"},
}

POPULAR_BOOKS = {
    "harry-potter": "Harry Potter",
    "gone-girl": "Gone Girl",
    "atomic-habits": "Atomic Habits",
    "the-hunger-games": "The Hunger Games",
    "percy-jackson": "Percy Jackson",
    "diary-of-a-wimpy-kid": "Diary of a Wimpy Kid",
    "the-giver": "The Giver",
    "wonder": "Wonder",
    "Charlotte's-web": "Charlotte's Web",
    "a-wrinkle-in-time": "A Wrinkle in Time",
    "the-alchemist": "The Alchemist",
    "educated": "Educated",
    "where-the-crawdads-sing": "Where the Crawdads Sing",
    "the-midnight-library": "The Midnight Library",
    "project-hail-mary": "Project Hail Mary",
}


async def get_db():
    return await asyncpg.connect(DB_URL)


async def fetch_books_by_goal(goal: str, age_min: int, age_max: int, limit: int = 6):
    # Normalize URL key back to DB key (problem-solving → problem_solving)
    db_goal = goal.replace("-", "_")
    conn = await get_db()
    try:
        rows = await conn.fetch("""
            SELECT title, author, cover_url, age_min, age_max,
                   learning_goals, page_count, genres
            FROM books
            WHERE is_children_book = TRUE
            AND learning_goals::text LIKE $1
            AND age_min <= $2
            AND age_max >= $3
            ORDER BY
                CASE WHEN cover_url IS NOT NULL THEN 0 ELSE 1 END,
                page_count DESC NULLS LAST
            LIMIT $4
        """, f"%{db_goal}%", age_max, age_min, limit)
        return rows
    finally:
        await conn.close()


async def fetch_books_by_age(age_min: int, age_max: int, limit: int = 8):
    conn = await get_db()
    try:
        rows = await conn.fetch("""
            SELECT title, author, cover_url, age_min, age_max,
                   learning_goals, page_count
            FROM books
            WHERE is_children_book = TRUE
            AND age_min <= $1
            AND age_max >= $2
            ORDER BY
                CASE WHEN cover_url IS NOT NULL THEN 0 ELSE 1 END,
                page_count DESC NULLS LAST
            LIMIT $3
        """, age_max, age_min, limit)
        return rows
    finally:
        await conn.close()


async def fetch_books_by_genre(genre: str, limit: int = 8):
    conn = await get_db()
    try:
        rows = await conn.fetch("""
            SELECT title, author, cover_url, page_count, genres
            FROM books
            WHERE (is_children_book = FALSE OR is_children_book IS NULL)
            AND (
                LOWER(genres::text) LIKE $1
                OR LOWER(title) LIKE $1
            )
            ORDER BY
                CASE WHEN cover_url IS NOT NULL THEN 0 ELSE 1 END,
                page_count DESC NULLS LAST
            LIMIT $2
        """, f"%{genre.replace('-', ' ')}%", limit)
        return rows
    finally:
        await conn.close()


def book_card_html(book, show_age=True):
    """Generate HTML for a single book card"""
    cover = book['cover_url'] or ''
    goals = json.loads(book.get('learning_goals') or '[]') if book.get('learning_goals') else []
    goal_tags = ''.join([
        f'<span class="goal-tag">{g.replace("_", " ").title()}</span>'
        for g in goals[:3]
    ])
    age_str = f"Ages {book['age_min']}-{book['age_max']}" if book.get('age_min') else ""
    cover_html = (
        f'<img src="{cover}" alt="{book["title"]}" loading="lazy" onerror="this.style.display=\'none\'">'
        if cover else
        f'<div class="no-cover">📚</div>'
    )
    amazon_url = f"https://www.amazon.com/s?k={book['title'].replace(' ', '+').replace(chr(39), '')}&tag=bookmind88-20"
    bookshop_url = f"https://bookshop.org/search?keywords={book['title'].replace(' ', '+')}&affiliate=124067"

    return f"""
    <div class="book-card" itemscope itemtype="https://schema.org/Book">
        <div class="book-cover">{cover_html}</div>
        <div class="book-info">
            <h3 class="book-title" itemprop="name">{book['title']}</h3>
            <p class="book-author" itemprop="author">{book['author']}</p>
            {f'<p class="book-age">{age_str}</p>' if show_age and age_str else ''}
            {f'<div class="goal-tags">{goal_tags}</div>' if goal_tags else ''}
            <div class="buy-buttons">
                <a href="{amazon_url}" target="_blank" rel="noopener" class="buy-btn amazon">Amazon</a>
                <a href="{bookshop_url}" target="_blank" rel="noopener" class="buy-btn bookshop">Bookshop</a>
            </div>
        </div>
    </div>"""


def seo_page_html(title, description, h1, intro, books_html, breadcrumbs, canonical, related_links=""):
    """Full SEO page template"""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<meta name="description" content="{description}">
<link rel="canonical" href="https://www.getbookmind.ai{canonical}">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{description}">
<meta property="og:url" content="https://www.getbookmind.ai{canonical}">
<meta property="og:type" content="website">
<meta property="og:image" content="https://www.getbookmind.ai/og-image.png">
<meta name="twitter:card" content="summary_large_image">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
<script type="application/ld+json">
{{
  "@context": "https://schema.org",
  "@type": "CollectionPage",
  "name": "{title}",
  "description": "{description}",
  "url": "https://www.getbookmind.ai{canonical}",
  "publisher": {{
    "@type": "Organization",
    "name": "BookMind",
    "url": "https://www.getbookmind.ai"
  }}
}}
</script>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
:root{{--accent:#7c3aed;--accent2:#a78bfa;--text:#1a1a2e;--muted:#6b7280;--bg:#fafaf9;--surface:#ffffff;--border:#e5e7eb}}
body{{font-family:'Inter',sans-serif;background:var(--bg);color:var(--text);line-height:1.6}}
.header{{background:var(--surface);border-bottom:1px solid var(--border);padding:16px 24px;display:flex;align-items:center;justify-content:space-between}}
.logo{{font-family:'Playfair Display',serif;font-size:22px;color:var(--accent);text-decoration:none;font-weight:700}}
.nav-link{{color:var(--muted);text-decoration:none;font-size:14px;margin-left:20px}}
.nav-link:hover{{color:var(--accent)}}
.breadcrumb{{max-width:900px;margin:16px auto;padding:0 24px;font-size:13px;color:var(--muted)}}
.breadcrumb a{{color:var(--accent);text-decoration:none}}
.breadcrumb a:hover{{text-decoration:underline}}
.hero{{max-width:900px;margin:32px auto;padding:0 24px}}
.hero h1{{font-family:'Playfair Display',serif;font-size:clamp(28px,4vw,42px);color:var(--text);margin-bottom:16px;line-height:1.2}}
.hero p{{font-size:17px;color:var(--muted);max-width:680px;line-height:1.7}}
.badge{{display:inline-flex;align-items:center;gap:6px;background:rgba(124,58,237,0.08);color:var(--accent);border:1px solid rgba(124,58,237,0.2);border-radius:100px;padding:4px 12px;font-size:12px;font-weight:600;margin-bottom:16px}}
.books-grid{{max-width:900px;margin:40px auto;padding:0 24px;display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:20px}}
.book-card{{background:var(--surface);border:1px solid var(--border);border-radius:14px;overflow:hidden;transition:box-shadow 0.2s;display:flex;flex-direction:column}}
.book-card:hover{{box-shadow:0 4px 20px rgba(0,0,0,0.08)}}
.book-cover{{height:180px;background:#f3f4f6;display:flex;align-items:center;justify-content:center;overflow:hidden}}
.book-cover img{{width:100%;height:100%;object-fit:cover}}
.no-cover{{font-size:48px}}
.book-info{{padding:16px;flex:1;display:flex;flex-direction:column;gap:6px}}
.book-title{{font-weight:600;font-size:14px;line-height:1.4;color:var(--text)}}
.book-author{{font-size:13px;color:var(--muted)}}
.book-age{{font-size:11px;color:var(--accent);font-weight:600}}
.goal-tags{{display:flex;flex-wrap:wrap;gap:4px;margin-top:4px}}
.goal-tag{{background:rgba(124,58,237,0.08);color:var(--accent);border-radius:4px;padding:2px 8px;font-size:10px;font-weight:500}}
.buy-buttons{{display:flex;gap:8px;margin-top:auto;padding-top:12px}}
.buy-btn{{flex:1;padding:8px;border-radius:8px;font-size:12px;font-weight:600;text-align:center;text-decoration:none;transition:opacity 0.2s}}
.buy-btn:hover{{opacity:0.85}}
.amazon{{background:#FF9900;color:#000}}
.bookshop{{background:#2d6a4f;color:#fff}}
.cta-section{{max-width:900px;margin:48px auto;padding:32px 24px;background:linear-gradient(135deg,rgba(124,58,237,0.08),rgba(167,139,250,0.08));border:1px solid rgba(124,58,237,0.15);border-radius:20px;text-align:center}}
.cta-section h2{{font-family:'Playfair Display',serif;font-size:24px;margin-bottom:10px}}
.cta-section p{{color:var(--muted);margin-bottom:20px;font-size:15px}}
.cta-btn{{display:inline-block;background:var(--accent);color:white;padding:12px 28px;border-radius:100px;font-weight:600;text-decoration:none;font-size:15px}}
.cta-btn:hover{{opacity:0.9}}
.related{{max-width:900px;margin:40px auto;padding:0 24px 48px}}
.related h2{{font-family:'Playfair Display',serif;font-size:22px;margin-bottom:16px}}
.related-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:10px}}
.related-link{{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:12px 16px;text-decoration:none;color:var(--text);font-size:13px;font-weight:500;transition:all 0.2s}}
.related-link:hover{{border-color:var(--accent);color:var(--accent)}}
.footer{{background:var(--surface);border-top:1px solid var(--border);padding:32px 24px;text-align:center;color:var(--muted);font-size:13px}}
.footer a{{color:var(--accent);text-decoration:none}}
@media(max-width:600px){{.books-grid{{grid-template-columns:1fr 1fr}}}}
</style>
</head>
<body>
<header class="header">
  <a href="/" class="logo">BookMind</a>
  <nav>
    <a href="/" class="nav-link">Home</a>
    <a href="/books-for-children" class="nav-link">Kids Books</a>
    <a href="/best-books-by-genre" class="nav-link">Adult Books</a>
  </nav>
</header>

<nav class="breadcrumb" aria-label="Breadcrumb">
  {breadcrumbs}
</nav>

<main>
  <div class="hero">
    <div class="badge">✨ AI-Curated Book List</div>
    <h1>{h1}</h1>
    <p>{intro}</p>
  </div>

  <div class="books-grid">
    {books_html}
  </div>

  <div class="cta-section">
    <h2>Get Personalized Recommendations</h2>
    <p>Tell us about your child's age, reading level, and what you want them to learn. BookMind finds the perfect books in seconds.</p>
    <a href="/" class="cta-btn">Find Books for My Child →</a>
  </div>

  {f'<div class="related"><h2>Related Book Lists</h2><div class="related-grid">{related_links}</div></div>' if related_links else ''}
</main>

<footer class="footer">
  <p>© 2026 <a href="/">BookMind</a> — AI-powered book recommendations.
  Some links are affiliate links. We may earn a small commission at no extra cost to you.</p>
</footer>
</body>
</html>"""


# ── Routes ────────────────────────────────────────────────────

@router.get("/books-that-teach-problem_solving-for-kids")
async def redirect_problem_solving_goal():
    from fastapi.responses import RedirectResponse
    return RedirectResponse("/books-that-teach-problem-solving-for-kids", status_code=301)


@router.get("/books-that-teach-problem_solving-for-{age}-year-olds")
async def redirect_problem_solving_age(age: str):
    from fastapi.responses import RedirectResponse
    return RedirectResponse(f"/books-that-teach-problem-solving-for-{age}-year-olds", status_code=301)


@router.get("/books-that-teach-{goal}-for-kids", response_class=HTMLResponse)
async def books_by_goal(goal: str):
    """Books that teach a specific learning goal"""
    if goal not in LEARNING_GOALS:
        return HTMLResponse("<h1>Not Found</h1>", status_code=404)

    g = LEARNING_GOALS[goal]
    books = await fetch_books_by_goal(goal, 3, 14, limit=6)

    if not books:
        return HTMLResponse("<h1>Coming Soon</h1>", status_code=404)

    books_html = "".join([book_card_html(b) for b in books])

    # Related links — other learning goals
    related = "".join([
        f'<a href="/books-that-teach-{g2}-for-kids" class="related-link">{LEARNING_GOALS[g2]["emoji"]} {LEARNING_GOALS[g2]["label"]}</a>'
        for g2 in LEARNING_GOALS if g2 != goal
    ])

    breadcrumbs = '<a href="/">Home</a> › <a href="/books-for-children">Kids Books</a> › Books that Teach ' + g["label"]

    return HTMLResponse(seo_page_html(
        title=f"Best Books That Teach {g['label']} for Kids (2026) — BookMind",
        description=f"Discover the best children's books to {g['desc']}. Expert-curated list with age recommendations and learning outcomes.",
        h1=f"{g['emoji']} Best Books That Teach {g['label']} for Kids",
        intro=f"Looking for books that {g['desc']}? We've curated the best children's books across all age groups, each carefully selected for its ability to teach {g['label'].lower()} through engaging stories.",
        books_html=books_html,
        breadcrumbs=breadcrumbs,
        canonical=f"/books-that-teach-{goal}-for-kids",
        related_links=related
    ))


@router.get("/best-books-for-{age}-year-olds", response_class=HTMLResponse)
async def books_by_age(age: str):
    """Best books for a specific age"""
    if age not in AGE_GROUPS:
        return HTMLResponse("<h1>Not Found</h1>", status_code=404)

    a = AGE_GROUPS[age]
    books = await fetch_books_by_age(a["min"], a["max"], limit=8)

    if not books:
        return HTMLResponse("<h1>Coming Soon</h1>", status_code=404)

    books_html = "".join([book_card_html(b) for b in books])

    # Related ages
    related = "".join([
        f'<a href="/best-books-for-{age2}-year-olds" class="related-link">📚 Books for {age2}-Year-Olds</a>'
        for age2 in AGE_GROUPS if age2 != age
    ])

    # Add learning goal links
    related += "".join([
        f'<a href="/books-that-teach-{g}-for-kids" class="related-link">{LEARNING_GOALS[g]["emoji"]} Books Teaching {LEARNING_GOALS[g]["label"]}</a>'
        for g in list(LEARNING_GOALS.keys())[:6]
    ])

    breadcrumbs = f'<a href="/">Home</a> › <a href="/books-for-children">Kids Books</a> › Best Books for {a["label"]}'

    return HTMLResponse(seo_page_html(
        title=f"Best Books for {a['label']} (2026) — Expert Picks — BookMind",
        description=f"The best books for {a['label'].lower()} in 2026. {a['type']} perfect for kids who {a['reader']}. Expert-curated with learning outcomes.",
        h1=f"📚 Best Books for {a['label']}",
        intro=f"Finding the right book for a {age}-year-old can transform them into a lifelong reader. These are the best {a['type'].lower()} for {a['label'].lower()} — books that children love to read and parents feel great about.",
        books_html=books_html,
        breadcrumbs=breadcrumbs,
        canonical=f"/best-books-for-{age}-year-olds",
        related_links=related
    ))


@router.get("/books-that-teach-{goal}-for-{age}-year-olds", response_class=HTMLResponse)
async def books_by_goal_and_age(goal: str, age: str):
    """Books teaching a specific goal for a specific age"""
    if goal not in LEARNING_GOALS or age not in AGE_GROUPS:
        return HTMLResponse("<h1>Not Found</h1>", status_code=404)

    g = LEARNING_GOALS[goal]
    a = AGE_GROUPS[age]
    books = await fetch_books_by_goal(goal, a["min"], a["max"], limit=6)

    if not books:
        # Fallback — all ages for this goal
        books = await fetch_books_by_goal(goal, 3, 14, limit=6)

    if not books:
        return HTMLResponse("<h1>Coming Soon</h1>", status_code=404)

    books_html = "".join([book_card_html(b) for b in books])

    related = "".join([
        f'<a href="/books-that-teach-{goal}-for-{age2}-year-olds" class="related-link">📚 {goal.replace("_"," ").title()} for {age2}-Year-Olds</a>'
        for age2 in AGE_GROUPS if age2 != age
    ])

    breadcrumbs = f'<a href="/">Home</a> › <a href="/books-for-children">Kids Books</a> › <a href="/best-books-for-{age}-year-olds">Books for {age}-Year-Olds</a> › {g["label"]}'

    return HTMLResponse(seo_page_html(
        title=f"Books That Teach {g['label']} for {a['label']} (2026) — BookMind",
        description=f"Best children's books to teach {g['label'].lower()} to {a['label'].lower()}. Perfect for {a['reader']}. Expert-curated with parent notes.",
        h1=f"{g['emoji']} Books That Teach {g['label']} for {a['label']}",
        intro=f"The best books to {g['desc']} — perfect for {a['label'].lower()} who {a['reader']}. Each book was carefully selected for its ability to teach {g['label'].lower()} in an age-appropriate, engaging way.",
        books_html=books_html,
        breadcrumbs=breadcrumbs,
        canonical=f"/books-that-teach-{goal}-for-{age}-year-olds",
        related_links=related
    ))


@router.get("/best-{genre}-books", response_class=HTMLResponse)
async def books_by_genre(genre: str):
    """Best adult books by genre"""
    if genre not in ADULT_GENRES:
        return HTMLResponse("<h1>Not Found</h1>", status_code=404)

    g = ADULT_GENRES[genre]
    books = await fetch_books_by_genre(genre, limit=8)

    if not books:
        return HTMLResponse("<h1>Coming Soon</h1>", status_code=404)

    books_html = "".join([book_card_html(b, show_age=False) for b in books])

    related = "".join([
        f'<a href="/best-{g2}-books" class="related-link">{ADULT_GENRES[g2]["emoji"]} Best {ADULT_GENRES[g2]["label"]} Books</a>'
        for g2 in ADULT_GENRES if g2 != genre
    ])

    breadcrumbs = f'<a href="/">Home</a> › <a href="/best-books-by-genre">Books by Genre</a> › Best {g["label"]} Books'

    return HTMLResponse(seo_page_html(
        title=f"Best {g['label']} Books (2026) — Must-Read Picks — BookMind",
        description=f"The best {g['label'].lower()} books of 2026. Discover {g['desc']}. AI-curated recommendations with reader reviews.",
        h1=f"{g['emoji']} Best {g['label']} Books",
        intro=f"Looking for the best {g['label'].lower()} books? These are {g['desc']}. Whether you're a longtime fan or new to the genre, these picks will keep you reading all night.",
        books_html=books_html,
        breadcrumbs=breadcrumbs,
        canonical=f"/best-{genre}-books",
        related_links=related
    ))


@router.get("/books-for-children", response_class=HTMLResponse)
async def children_hub():
    """Children's books hub page"""
    goal_links = "".join([
        f'<a href="/books-that-teach-{g}-for-kids" class="related-link">{LEARNING_GOALS[g]["emoji"]} Books Teaching {LEARNING_GOALS[g]["label"]}</a>'
        for g in LEARNING_GOALS
    ])
    age_links = "".join([
        f'<a href="/best-books-for-{a}-year-olds" class="related-link">📚 Best Books for {a}-Year-Olds</a>'
        for a in AGE_GROUPS
    ])

    html = seo_page_html(
        title="Best Children's Books (2026) — By Age, Goal & Interest — BookMind",
        description="Find the perfect children's book by age, learning goal, or interest. Expert-curated lists for every child from toddlers to teens.",
        h1="📚 Children's Books — Find the Perfect Match",
        intro="Every child is different. Browse our curated children's book lists by age group, learning goal, or let our AI find the perfect book for your child in seconds.",
        books_html="",
        breadcrumbs='<a href="/">Home</a> › Children\'s Books',
        canonical="/books-for-children",
        related_links=goal_links + age_links
    )
    return HTMLResponse(html)


@router.get("/best-books-by-genre", response_class=HTMLResponse)
async def genre_hub():
    """Adult books genre hub"""
    genre_links = "".join([
        f'<a href="/best-{g}-books" class="related-link">{ADULT_GENRES[g]["emoji"]} Best {ADULT_GENRES[g]["label"]} Books</a>'
        for g in ADULT_GENRES
    ])

    return HTMLResponse(seo_page_html(
        title="Best Books by Genre (2026) — Expert Picks — BookMind",
        description="Find your next favorite book by genre. Expert-curated lists of the best thriller, mystery, fantasy, romance, and more.",
        h1="📚 Best Books by Genre",
        intro="Find your perfect next read. Browse our expert-curated book lists by genre — from gripping thrillers to heartwarming romance, mind-bending sci-fi to beautiful literary fiction.",
        books_html="",
        breadcrumbs='<a href="/">Home</a> › Books by Genre',
        canonical="/best-books-by-genre",
        related_links=genre_links
    ))


@router.get("/sitemap.xml")
async def sitemap():
    """Auto-generated XML sitemap for all SEO pages"""
    urls = ["https://www.getbookmind.ai/"]
    urls.append("https://www.getbookmind.ai/books-for-children")
    urls.append("https://www.getbookmind.ai/best-books-by-genre")

    for goal in LEARNING_GOALS:
        urls.append(f"https://www.getbookmind.ai/books-that-teach-{goal}-for-kids")
        for age in AGE_GROUPS:
            urls.append(f"https://www.getbookmind.ai/books-that-teach-{goal}-for-{age}-year-olds")

    for age in AGE_GROUPS:
        urls.append(f"https://www.getbookmind.ai/best-books-for-{age}-year-olds")

    for genre in ADULT_GENRES:
        urls.append(f"https://www.getbookmind.ai/best-{genre}-books")

    from datetime import date
    today = date.today().isoformat()

    xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    for i, url in enumerate(urls):
        priority = "1.0" if i == 0 else "0.8"
        xml += f"  <url><loc>{url}</loc><lastmod>{today}</lastmod><changefreq>weekly</changefreq><priority>{priority}</priority></url>\n"
    xml += "</urlset>"

    from fastapi.responses import Response
    return Response(content=xml, media_type="application/xml")
