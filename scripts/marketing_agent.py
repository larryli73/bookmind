"""
BookMind Marketing Agent
========================
Generates authentic marketing content for different platforms and audiences.
Uses Claude to write posts that don't sound like ads.

Usage:
    python -m scripts.marketing_agent --platform reddit --subreddit suggestmeabook
    python -m scripts.marketing_agent --platform twitter
    python -m scripts.marketing_agent --platform producthunt
    python -m scripts.marketing_agent --platform all
"""
import asyncio
import argparse
import os
from anthropic import AsyncAnthropic

client = AsyncAnthropic()

SITE_URL = "https://www.getbookmind.ai"
SITE_DESC = """
BookMind is a free AI book recommendation engine that:
- Takes natural language input like "I loved Gone Girl, what's next?"
- Returns 8 personalized book recommendations with explanations
- Shows Amazon and Bookshop buy links
- No signup required
- Has 17,000+ quality books indexed
- Uses Claude AI for intelligent recommendations
- Shows award badges (NYT Bestseller, Pulitzer, etc.)
- Works for adults, literary fiction, sci-fi, romance, thrillers, kids books
"""

SUBREDDITS = [
    {
        "name": "r/suggestmeabook",
        "members": "5.5M",
        "rules": "Must be genuine, no pure self-promotion, share what problem it solves",
        "audience": "Active book lovers who ask for recommendations daily",
        "tone": "Casual, genuine, book lover to book lover"
    },
    {
        "name": "r/books",
        "members": "23M", 
        "rules": "No spam, must add value to discussion, share why it's useful",
        "audience": "General book enthusiasts",
        "tone": "Thoughtful, discuss the problem with recommendations first"
    },
    {
        "name": "r/booksuggestions",
        "members": "800K",
        "rules": "Must be helpful content",
        "audience": "People actively looking for book suggestions",
        "tone": "Direct and helpful"
    },
    {
        "name": "r/Fantasy",
        "members": "1.5M",
        "rules": "Must be fantasy-relevant",
        "audience": "Fantasy book fans",
        "tone": "Focus on fantasy recommendations specifically"
    },
    {
        "name": "r/printSF",
        "members": "200K",
        "rules": "Science fiction focused",
        "audience": "Sci-fi readers",
        "tone": "Technical, mention sci-fi catalog depth"
    },
    {
        "name": "r/RomanceBooks",
        "members": "500K",
        "rules": "Romance focused",
        "audience": "Romance readers",
        "tone": "Warm, mention romance subgenre support"
    },
]


async def generate_reddit_post(subreddit: dict) -> str:
    """Generate an authentic Reddit post for a specific subreddit"""
    response = await client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=800,
        messages=[{
            "role": "user",
            "content": f"""Write an authentic Reddit post for {subreddit['name']} ({subreddit['members']} members) promoting BookMind.

About BookMind:
{SITE_DESC}

URL: {SITE_URL}

Subreddit audience: {subreddit['audience']}
Tone: {subreddit['tone']}
Rules to follow: {subreddit['rules']}

Write a genuine post that:
1. Doesn't sound like an ad
2. Leads with a relatable problem book lovers face
3. Mentions the tool naturally as a solution
4. Invites feedback and discussion
5. Feels like a real person sharing something useful

Format as:
TITLE: [post title]

BODY:
[post body]

Keep title under 300 chars. Body should be 150-300 words. Be genuine and conversational."""
        }]
    )
    return response.content[0].text


async def generate_twitter_thread() -> str:
    """Generate a Twitter/X thread"""
    response = await client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=600,
        messages=[{
            "role": "user",
            "content": f"""Write a Twitter/X thread (5-7 tweets) promoting BookMind.

About BookMind:
{SITE_DESC}

URL: {SITE_URL}

Rules:
- Each tweet max 280 chars
- Start with a hook about the problem with book recommendations
- Thread should feel like sharing a useful discovery
- End with the URL and call to action
- Use relevant hashtags sparingly (#books #reading #AI)
- Number each tweet (1/6, 2/6, etc.)

Write the full thread now."""
        }]
    )
    return response.content[0].text


async def generate_producthunt_post() -> str:
    """Generate a Product Hunt launch post"""
    response = await client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=600,
        messages=[{
            "role": "user",
            "content": f"""Write a Product Hunt launch post for BookMind.

About BookMind:
{SITE_DESC}

URL: {SITE_URL}

Format:
TAGLINE: [one line, max 60 chars]

DESCRIPTION: [2-3 paragraphs explaining what it does, why it's different, and what makes it special. 150-200 words]

FIRST COMMENT: [founder's comment - personal story of why you built it, 100-150 words]

Make it compelling, honest, and highlight the AI personalization aspect."""
        }]
    )
    return response.content[0].text


async def generate_seo_blog_post(topic: str) -> str:
    """Generate an SEO blog post"""
    response = await client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=1500,
        messages=[{
            "role": "user",
            "content": f"""Write an SEO blog post for BookMind's website about: "{topic}"

About BookMind:
{SITE_DESC}

URL: {SITE_URL}

Requirements:
- 600-800 words
- Include the topic as H1
- Use H2 subheadings
- Naturally mention BookMind 2-3 times as a resource
- Include a call to action at the end
- Write for book lovers, not SEO bots
- Conversational but informative tone

Write the full blog post in Markdown format."""
        }]
    )
    return response.content[0].text


async def generate_email_template() -> str:
    """Generate a welcome email for new signups"""
    response = await client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=400,
        messages=[{
            "role": "user",
            "content": f"""Write a welcome email for new BookMind users.

About BookMind:
{SITE_DESC}

URL: {SITE_URL}

Requirements:
- Subject line that gets opened
- Warm, personal tone
- Explain how to get the best recommendations
- Mention the ❤️ and 👎 buttons improve their recs
- Invite them to reply with feedback
- Keep it short (150 words max)

Format:
SUBJECT: [subject line]

BODY:
[email body]"""
        }]
    )
    return response.content[0].text


async def main(platform: str, subreddit_name: str = None):
    print(f"\n🤖 BookMind Marketing Agent")
    print(f"🌐 Site: {SITE_URL}")
    print("=" * 60)

    if platform in ("reddit", "all"):
        targets = [s for s in SUBREDDITS if not subreddit_name or s["name"] == f"r/{subreddit_name}"]
        for sub in targets:
            print(f"\n📝 Generating post for {sub['name']}...")
            post = await generate_reddit_post(sub)
            print(f"\n{'='*60}")
            print(f"📌 {sub['name']} ({sub['members']} members)")
            print(f"{'='*60}")
            print(post)
            print()

    if platform in ("twitter", "all"):
        print(f"\n🐦 Generating Twitter/X thread...")
        thread = await generate_twitter_thread()
        print(f"\n{'='*60}")
        print("📌 TWITTER/X THREAD")
        print(f"{'='*60}")
        print(thread)

    if platform in ("producthunt", "all"):
        print(f"\n🚀 Generating Product Hunt post...")
        ph = await generate_producthunt_post()
        print(f"\n{'='*60}")
        print("📌 PRODUCT HUNT LAUNCH")
        print(f"{'='*60}")
        print(ph)

    if platform in ("email", "all"):
        print(f"\n📧 Generating welcome email...")
        email = await generate_email_template()
        print(f"\n{'='*60}")
        print("📌 WELCOME EMAIL")
        print(f"{'='*60}")
        print(email)

    if platform in ("blog", "all"):
        topics = [
            "How to Find Your Next Favourite Book Using AI",
            "Why Goodreads Recommendations Fail (And What to Do Instead)",
            "The Best Books Like Gone Girl According to AI",
        ]
        for topic in topics[:1]:  # Generate 1 blog post
            print(f"\n✍️ Generating blog post: {topic}")
            blog = await generate_seo_blog_post(topic)
            print(f"\n{'='*60}")
            print(f"📌 BLOG POST")
            print(f"{'='*60}")
            print(blog)

    print(f"\n✅ Marketing content generated!")
    print(f"💡 Tip: Copy the Reddit posts and post them one at a time, 2-3 days apart")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BookMind Marketing Agent")
    parser.add_argument("--platform", default="reddit",
                        choices=["reddit", "twitter", "producthunt", "email", "blog", "all"],
                        help="Platform to generate content for")
    parser.add_argument("--subreddit", default=None,
                        help="Specific subreddit (e.g. suggestmeabook)")
    args = parser.parse_args()
    asyncio.run(main(args.platform, args.subreddit))
