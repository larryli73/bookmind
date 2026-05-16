"""
Embedder node — converts user message into a query vector using Voyage AI
"""
from __future__ import annotations
import os
import hashlib
import math
import httpx
import numpy as np
from agent.state import AgentState

VOYAGE_API_KEY = os.getenv("VOYAGE_API_KEY", "")
VOYAGE_MODEL   = "voyage-3"
DIMS           = 1024


async def get_embedding(text: str) -> list[float]:
    if VOYAGE_API_KEY:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.voyageai.com/v1/embeddings",
                    headers={"Authorization": f"Bearer {VOYAGE_API_KEY}", "Content-Type": "application/json"},
                    json={"model": VOYAGE_MODEL, "input": text[:4000]},
                    timeout=30.0,
                )
                response.raise_for_status()
                data = response.json()
                return data["data"][0]["embedding"]
        except Exception:
            pass  # fall through to hash fallback
    else:
        # Fallback hash embedding
        vector = []
        for i in range(DIMS):
            seed = hashlib.md5(f"{text}{i}".encode()).hexdigest()
            val = int(seed[:8], 16) / (16**8)
            vector.append(val * 2 - 1)
        magnitude = math.sqrt(sum(x**2 for x in vector))
        return [x / magnitude for x in vector]


async def embed_query(state: AgentState) -> AgentState:
    message_vector = None
    taste_vector = state.taste_vector

    if state.user_message:
        message_vector = await get_embedding(state.user_message)

    if message_vector and taste_vector:
        mv = np.array(message_vector)
        tv = np.array(taste_vector)
        # Pad or trim taste vector if dims differ
        if len(tv) != len(mv):
            tv = np.resize(tv, len(mv))
        blended = 0.7 * mv + 0.3 * tv
        norm = np.linalg.norm(blended)
        state.query_vector = (blended / norm).tolist() if norm > 0 else message_vector
    elif message_vector:
        state.query_vector = message_vector
    elif taste_vector:
        state.query_vector = taste_vector
    else:
        state.errors.append("embedder: no message or taste vector available")

    state.pipeline_steps.append("embed_query: complete")
    return state
