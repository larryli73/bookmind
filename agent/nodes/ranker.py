"""
LLM Ranker node — Claude picks final top-N books with personalized explanations
"""
from __future__ import annotations
import json
import re
import anthropic
from agent.state import AgentState

client = anthropic.AsyncAnthropic()


def candidates_to_text(candidates: list) -> str:
    lines = []
    for b in candidates[:20]:
        if isinstance(b, dict):
            bid = str(b.get("book_id", ""))
            title = b.get("title", "")
            author = b.get("author", "")
            genres = b.get("genres", [])
        else:
            bid = str(b.book_id)
            title = b.title
            author = b.author
            genres = b.genres or []
        line = f"- ID:{bid} | {title} by {author}"
        if genres:
            line += f" | Genres: {', '.join(str(g) for g in genres[:3])}"
        lines.append(line)
    return "\n".join(lines)


def extract_json(text: str) -> list:
    text = text.strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    match = re.search(r'```(?:json)?\s*(\[.*?\])\s*```', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except Exception:
            pass
    match = re.search(r'\[.*\]', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except Exception:
            pass
    return []


async def llm_rank_books(state: AgentState) -> AgentState:
    candidates = state.filtered_candidates or state.candidates
    if not candidates:
        state.errors.append("llm_rank: no candidates")
        return state

    count = min(state.requested_count, len(candidates))
    cand_text = candidates_to_text(candidates)
    user_msg = state.user_message or "general reading"

    prompt = f"""The reader said: "{user_msg}"

Here are candidate books:
{cand_text}

Pick the best {count} books for this reader. Return ONLY a JSON array like this:
[{{"book_id": "uuid-here", "reason": "2 sentence explanation why this fits the reader"}}]

No markdown, no explanation, just the JSON array."""

    try:
        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}]
        )
        state.total_tokens_used += response.usage.input_tokens + response.usage.output_tokens
        raw = response.content[0].text.strip()
        ranked = extract_json(raw)

        if ranked:
            if candidates and isinstance(candidates[0], dict):
                book_map = {str(b.get("book_id", "")): b for b in candidates}
            else:
                book_map = {str(b.book_id): b for b in candidates}

            final = []
            for item in ranked:
                bid = str(item.get("book_id", ""))
                if bid in book_map:
                    book = book_map[bid]
                    if isinstance(book, dict):
                        book["reason"] = item.get("reason", "")
                        final.append(book)
                    else:
                        book.reason = item.get("reason", "")
                        final.append(book)

            state.final_recommendations = final if final else candidates[:count]
        else:
            state.errors.append(f"llm_rank: no JSON found in: {raw[:100]}")
            state.final_recommendations = candidates[:count]

    except Exception as e:
        state.errors.append(f"llm_rank error: {e}")
        state.final_recommendations = candidates[:count]

    state.pipeline_steps.append(f"llm_rank: selected {len(state.final_recommendations)} books")
    return state
