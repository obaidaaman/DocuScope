from langgraph.graph import StateGraph, START, END

from .schemas import ReconciliationState
from .nodes import (
    ingest_documents_node,
    extract_claims_node,
    build_topic_clusters_node,
    llm_judge_node,
    persist_results_node,
)

workflow = StateGraph(ReconciliationState)
workflow.add_node("ingest_documents", ingest_documents_node)
workflow.add_node("extract_claims", extract_claims_node)
workflow.add_node("build_clusters", build_topic_clusters_node)
workflow.add_node("llm_judge", llm_judge_node)
workflow.add_node("persist_results", persist_results_node)

workflow.add_edge(START, "ingest_documents")
workflow.add_edge("ingest_documents", "extract_claims")
workflow.add_edge("extract_claims", "build_clusters")
workflow.add_edge("build_clusters", "llm_judge")
workflow.add_edge("llm_judge", "persist_results")
workflow.add_edge("persist_results", END)

reconciliation_graph = workflow.compile()
