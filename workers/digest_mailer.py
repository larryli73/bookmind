"""
Weekly digest mailer — sends personalized book picks every Monday
"""
import os
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from db.session import AsyncSessionLocal
from db.models import Reader, Child
from agent.state import AgentState
from agent.graph import get_recommendations
from sqlalchemy import select
import uuid


SENDGRID_KEY       = os.getenv("SENDGRID_API_KEY", "")
FROM_EMAIL         = os.getenv("SENDGRID_FROM_EMAIL", "hello@bookmind.app")
FROM_NAME          = os.getenv("SENDGRID_FROM_NAME", "BookMind")


def build_adult_digest_html(reader_name: str, recs: list) -> str:
    items = ""
    for i, r in enumerate(recs, 1):
        affiliate_links = ""
        if r.get("buy_links", {}).get("amazon"):
            affiliate_links += f'<a href="{r["buy_links"]["amazon"]}" style="background:#FF9900;color:#000;padding:6px 14px;border-radius:4px;text-decoration:none;font-size:12px;margin-right:6px;">📦 Amazon</a>'
        if r.get("buy_links", {}).get("bookshop"):
            affiliate_links += f'<a href="{r["buy_links"]["bookshop"]}" style="background:#2D5016;color:#fff;padding:6px 14px;border-radius:4px;text-decoration:none;font-size:12px;">📚 Bookshop</a>'

        items += f"""
        <div style="border:1px solid #e5e7eb;border-radius:8px;padding:16px;margin-bottom:16px;">
            <div style="font-size:14px;color:#6b7280;margin-bottom:4px;">Pick #{i}</div>
            <div style="font-size:18px;font-weight:700;color:#111827;">{r['title']}</div>
            <div style="font-size:14px;color:#6b7280;margin-bottom:8px;">by {r['author']}</div>
            <div style="font-size:14px;color:#374151;margin-bottom:12px;font-style:italic;">{r.get('reason', '')}</div>
            <div>{affiliate_links}</div>
        </div>"""

    return f"""
    <div style="font-family:Georgia,serif;max-width:600px;margin:0 auto;padding:20px;">
        <h1 style="font-size:28px;color:#111827;">📚 Your picks this week, {reader_name}!</h1>
        <p style="color:#6b7280;">Curated just for you by BookMind</p>
        {items}
        <p style="font-size:12px;color:#9ca3af;margin-top:24px;">
            BookMind uses affiliate links. When you buy through our links, 
            we earn a small commission at no extra cost to you. Thank you for supporting us!
        </p>
    </div>"""


async def send_weekly_digests(ctx=None):
    """ARQ job: send Monday digest to all readers with digest enabled"""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Reader).where(Reader.digest_enabled == True, Reader.onboarding_complete == True)
        )
        readers = result.scalars().all()

        sg = SendGridAPIClient(SENDGRID_KEY)
        sent = 0

        for reader in readers:
            try:
                state = AgentState(
                    mode="adult",
                    reader_id=reader.id,
                    reader_name=reader.name or "Reader",
                    session_id=str(uuid.uuid4()),
                    trigger="digest",
                    requested_count=5,
                    taste_vector=reader.taste_vector,
                )
                result_state = await get_recommendations(state)
                recs = [
                    {
                        "title": b.title, "author": b.author,
                        "reason": b.reason,
                        "buy_links": {"amazon": b.amazon_url, "bookshop": b.bookshop_url}
                    }
                    for b in result_state.final_recommendations
                ]

                html = build_adult_digest_html(reader.name or "Reader", recs)
                message = Mail(
                    from_email=(FROM_EMAIL, FROM_NAME),
                    to_emails=reader.email,
                    subject=f"📚 Your 5 books for this week, {reader.name or 'Reader'}",
                    html_content=html,
                )
                sg.send(message)
                sent += 1
            except Exception as e:
                print(f"Failed to send digest to {reader.email}: {e}")

    print(f"Weekly digest sent to {sent} readers")
    return sent


class WorkerSettings:
    functions  = [send_weekly_digests]
    queue_name = "bookmind:digest"
