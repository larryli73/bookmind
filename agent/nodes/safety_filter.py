"""
Safety filter — removes unsafe content and filters out seed authors/titles
"""
from __future__ import annotations
from agent.state import AgentState


def normalize(text: str) -> str:
    return text.lower().strip().replace("-", " ").replace("_", " ")


def shares_author_or_series(book, seed_titles: list[str], user_message: str) -> bool:
    """Check if book relates to anything mentioned in user message"""
    if isinstance(book, dict):
        title = normalize(book.get("title", ""))
        author = normalize(book.get("author", ""))
        series = normalize(book.get("series_name", "") or "")
    else:
        title = normalize(getattr(book, "title", "") or "")
        author = normalize(getattr(book, "author", "") or "")
        series = normalize(getattr(book, "series_name", "") or "")

    msg = normalize(user_message or "")

    # Direct check: if any word from book title appears prominently in user message
    title_words = [w for w in title.split() if len(w) > 4]
    for word in title_words:
        if word in msg:
            return True

    # Check seed titles
    for seed in (seed_titles or []):
        seed_norm = normalize(seed)
        seed_words = [w for w in seed_norm.split() if len(w) > 3]
        if not seed_words:
            continue

        title_matches = sum(1 for w in seed_words if w in title)
        author_matches = sum(1 for w in seed_words if w in author)
        series_matches = sum(1 for w in seed_words if w in series) if series else 0

        if title_matches >= max(1, len(seed_words) * 0.5):
            return True
        if author_matches >= max(1, len(seed_words) * 0.5):
            return True
        if series and series_matches >= max(1, len(seed_words) * 0.5):
            return True

    return False


async def safety_filter(state: AgentState) -> AgentState:
    candidates = state.candidates or []
    filtered = []
    removed_seed = 0

    for book in candidates:
        if shares_author_or_series(book, state.seed_titles or [], state.user_message or ""):
            removed_seed += 1
            continue

        if state.mode == "child":
            if isinstance(book, dict):
                scary = book.get("_has_scary") or book.get("has_scary_content")
                violence = book.get("_has_violence") or book.get("has_violence")
                adult = book.get("has_adult_themes")
            else:
                scary = getattr(book, "_has_scary", False)
                violence = getattr(book, "_has_violence", False)
                adult = getattr(book, "has_adult_themes", False)

            if state.avoid_scary and scary:
                continue
            if state.avoid_violence and violence:
                continue
            if adult:
                continue

        filtered.append(book)

    state.filtered_candidates = filtered
    state.pipeline_steps.append(
        f"safety_filter: {len(candidates)} → {len(filtered)} "
        f"(removed {removed_seed} seed-related)"
    )
    return state
