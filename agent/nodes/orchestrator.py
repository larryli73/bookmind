"""
Orchestrator node — extracts intent and context from user message using Claude
"""
from __future__ import annotations
import json
import anthropic
from agent.state import AgentState
from agent.prompts import TASTE_EXTRACTION_PROMPT, KIDS_TASTE_EXTRACTION_PROMPT

client = anthropic.AsyncAnthropic()


async def extract_intent(state: AgentState) -> AgentState:
    """
    Parse the user's message to extract:
    - Seed books they mentioned
    - What they loved / want
    - Any constraints
    """
    if not state.user_message:
        state.pipeline_steps.append("extract_intent: no message, using taste vector only")
        return state

    prompt = KIDS_TASTE_EXTRACTION_PROMPT if state.mode == "child" else TASTE_EXTRACTION_PROMPT

    response = await client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=500,
        system=prompt,
        messages=[{"role": "user", "content": state.user_message}]
    )

    state.total_tokens_used += response.usage.input_tokens + response.usage.output_tokens

    try:
        extracted = json.loads(response.content[0].text)
        # Store extracted intent in messages for later nodes
        state.messages.append({
            "role": "extracted_intent",
            "content": extracted
        })
    except (json.JSONDecodeError, IndexError):
        state.errors.append("extract_intent: failed to parse Claude response")

    state.pipeline_steps.append("extract_intent: complete")
    return state
