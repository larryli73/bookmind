"""
Safety filter — removes unsafe content and filters out seed authors/titles
"""
from __future__ import annotations
from agent.state import AgentState


def normalize(text: str) -> str:
    """Normalize text for comparison"""
    return text.lower().strip().replace("-", " ").replace("_", " ")


def shares_author_or_series(book, seed_titles: list[str]) -> bool:
    """Check if book is by same author or part of same series as seeds"""
    if not seed_titles:
        return False
    
    if isinstance(book, dict):
        title = normalize(book.get("title", ""))
        author = normalize(book.get("author", ""))
        series = normalize(book.get("series_name", "") or "")
    else:
        title = normalize(book.title or "")
        author = normalize(getattr(book, "author", "") or "")
        series = normalize(getattr(book, "series_name", "") or "")

    for seed in seed_titles:
        seed_norm = normalize(seed)
        # Check if seed words appear in title, author, or series
        seed_words = [w for w in seed_norm.split() if len(w) > 3]
        if not seed_words:
            continue
        # If most seed words match title or author, skip this book
        title_matches = sum(1 for w in seed_words if w in title)
        author_matches = sum(1 for w in seed_words if w in author)
        series_matches = sum(1 for w in seed_words if w in series) if series else 0
        
        if title_matches >= len(seed_words) * 0.6:
            return True
        if author_matches >= len(seed_words) * 0.6:
            return True
        if series_matches >= len(seed_words) * 0.6:
            return True

    return False


async def safety_filter(state: AgentState) -> AgentState:
    """Filter unsafe content and seed author/series books"""
    candidates = state.candidates or []
    filtered = []
    removed_seed = 0

    for book in candidates:
        # Skip books from same author/series as seeds
        if shares_author_or_series(book, state.seed_titles or []):
            removed_seed += 1
            continue

        # Kids safety filter
        if state.mode == "child":
            if isinstance(book, dict):
                scary = book.get("_has_scary") or book.get("has_scary_content")
                violence = book.get("_has_violence") or book.get("has_violence")
                adult = book.get("has_adult_themes")
            else:
                scary = getattr(book, "_has_scary", False) or getattr(book, "has_scary_content", False)
                violence = getattr(book, "_has_violence", False) or getattr(book, "has_violence", False)
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
        f"safety_filter: {len(candidates)} → {len(filtered)} candidates "
        f"(removed {removed_seed} seed-related books)"
    )
    return state
