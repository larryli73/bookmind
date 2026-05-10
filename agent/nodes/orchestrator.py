"""
Orchestrator node — extracts intent and sets up filtering
"""
from __future__ import annotations
import json, re
from anthropic import AsyncAnthropic
from agent.state import AgentState
from agent.prompts import TASTE_EXTRACTION_PROMPT

client = AsyncAnthropic()

# Common words to ignore when extracting author/title seeds
STOP_WORDS = {"i", "want", "like", "a", "an", "the", "something", "books", "book", 
               "similar", "to", "and", "or", "adventure", "story", "novel"}

def extract_seed_titles(message: str) -> list[str]:
    """Extract mentioned book/author names from message"""
    # Simple extraction — look for capitalized phrases
    words = message.split()
    seeds = []
    current = []
    for word in words:
        clean = word.strip(".,!?\"'")
        if clean and clean[0].isupper() and clean.lower() not in STOP_WORDS:
            current.append(clean)
        else:
            if current:
                seeds.append(" ".join(current))
                current = []
    if current:
        seeds.append(" ".join(current))
    return seeds


async def extract_intent(state: AgentState) -> AgentState:
    """Extract reader intent from their message"""
    try:
        response = await client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=300,
            system=TASTE_EXTRACTION_PROMPT,
            messages=[{"role": "user", "content": state.user_message}]
        )
        
        text = response.content[0].text.strip()
        # Clean up markdown code blocks if present
        text = re.sub(r'```json\s*', '', text)
        text = re.sub(r'```\s*', '', text)
        
        intent = json.loads(text)
        state.seed_titles = intent.get("seed_titles", [])
        state.loved_because = intent.get("loved_because", [])
        state.mood = intent.get("mood_now", "")
        state.constraints = intent.get("constraints", [])
        state.pipeline_steps.append("extract_intent: complete")
        
    except Exception as e:
        # Fallback: extract seeds from message directly
        state.seed_titles = extract_seed_titles(state.user_message)
        state.pipeline_steps.append(f"extract_intent: used fallback")

    return state
