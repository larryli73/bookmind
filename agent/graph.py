"""
BookMind — LangGraph Agent Pipeline
"""
from __future__ import annotations
from langgraph.graph import StateGraph, END
from agent.state import AgentState
from agent.nodes.embedder import embed_query
from agent.nodes.orchestrator import extract_intent
from agent.nodes.ranker import llm_rank_books
from agent.nodes.safety import apply_content_filters
from agent.tools.similarity_search import vector_search
from agent.tools.collab_filter import collaborative_rerank
from agent.tools.affiliate_linker import attach_affiliate_links
from agent.tools.series_tracker import inject_series_next
from agent.nodes.claude_fallback import maybe_claude_fallback


def should_show_series_first(state: AgentState) -> str:
    if state.mode == "child" and state.series_next_books:
        return "series_inject"
    return "vector_search"


def build_recommendation_graph() -> StateGraph:
    graph = StateGraph(AgentState)

    graph.add_node("extract_intent",  extract_intent)
    graph.add_node("embed_query",     embed_query)
    graph.add_node("series_inject",   inject_series_next)
    graph.add_node("vector_search",   vector_search)
    graph.add_node("safety_filter",   apply_content_filters)
    graph.add_node("collab_rerank",   collaborative_rerank)
    graph.add_node("llm_rank",        llm_rank_books)
    graph.add_node("claude_fallback", maybe_claude_fallback)
    graph.add_node("affiliate_links", attach_affiliate_links)

    graph.set_entry_point("extract_intent")
    graph.add_edge("extract_intent", "embed_query")

    graph.add_conditional_edges(
        "embed_query",
        should_show_series_first,
        {"series_inject": "series_inject", "vector_search": "vector_search"}
    )

    graph.add_edge("series_inject",   "vector_search")
    graph.add_edge("vector_search",   "safety_filter")
    graph.add_edge("safety_filter",   "collab_rerank")
    graph.add_edge("collab_rerank",   "llm_rank")
    graph.add_edge("llm_rank",        "claude_fallback")
    graph.add_edge("claude_fallback", "affiliate_links")
    graph.add_edge("affiliate_links", END)

    return graph.compile()


recommendation_graph = build_recommendation_graph()


async def get_recommendations(state: AgentState) -> AgentState:
    result = await recommendation_graph.ainvoke(state)
    return result
