from typing import List, Dict, Any
import networkx as nx
from sqlalchemy import text, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.db_models import DocumentChunk
from .schemas import TopicCluster, Passage

async def fetch_matching_pairs(
    db: AsyncSession,
    doc_ids: List[int],
    similarity_threshold: float = 0.78,
    limit: int = 500
) -> List[Dict[str, Any]]:
    sql = text("""
        SELECT 
            c1.document_id AS doc_a, c1.chunk_index AS idx_a,
            c2.document_id AS doc_b, c2.chunk_index AS idx_b,
            (1 - (c1.embedding <=> c2.embedding)) AS similarity
        FROM document_chunks c1
        JOIN document_chunks c2 ON c1.document_id < c2.document_id
        WHERE c1.document_id = ANY(:doc_ids) 
          AND c2.document_id = ANY(:doc_ids)
          AND c1.embedding IS NOT NULL
          AND c2.embedding IS NOT NULL
          AND (1 - (c1.embedding <=> c2.embedding)) >= :threshold
        ORDER BY similarity DESC
        LIMIT :limit;
    """)
    res = await db.execute(sql, {
        "doc_ids": doc_ids,
        "threshold": similarity_threshold,
        "limit": limit
    })
    return [dict(row._mapping) for row in res]

async def build_topic_clusters(
    db: AsyncSession,
    doc_ids: List[int],
    similarity_threshold: float = 0.78,
    max_pairs: int = 500
) -> List[TopicCluster]:
    pairs = await fetch_matching_pairs(
        db=db,
        doc_ids=doc_ids,
        similarity_threshold=similarity_threshold,
        limit=max_pairs
    )

    if not pairs:
        return []

    graph = nx.Graph()
    for p in pairs:
        node_a = (p["doc_a"], p["idx_a"])
        node_b = (p["doc_b"], p["idx_b"])
        graph.add_edge(node_a, node_b, weight=float(p["similarity"]))

    components = list(nx.connected_components(graph))
    clusters: List[TopicCluster] = []
    dabba_counter = 1

    for comp in components:
        doc_to_indices: Dict[int, List[int]] = {}
        for (d_id, c_idx) in comp:
            doc_to_indices.setdefault(d_id, []).append(c_idx)

        if len(doc_to_indices) < 2:
            continue

        all_dabba_passages: List[Passage] = []
        total_chunks = 0

        for d_id, indices in doc_to_indices.items():
            sorted_indices = sorted(indices)
            total_chunks += len(sorted_indices)

            stmt = (
                select(DocumentChunk)
                .where(
                    DocumentChunk.document_id == d_id,
                    DocumentChunk.chunk_index.in_(sorted_indices)
                )
                .order_by(DocumentChunk.chunk_index)
            )
            c_res = await db.execute(stmt)
            fetched_chunks = c_res.scalars().all()

            if fetched_chunks:
                combined_text = "\n\n".join([c.raw_text for c in fetched_chunks])
                first_page = fetched_chunks[0].page_number
                
                all_dabba_passages.append(Passage(
                    doc_id=d_id,
                    chunk_index=sorted_indices[0],
                    page_number=first_page,
                    text=combined_text
                ))

        if len(all_dabba_passages) >= 2:
            clusters.append(TopicCluster(
                dabba_id=dabba_counter,
                topic_hint=None,
                document_ids=list(doc_to_indices.keys()),
                passages=all_dabba_passages,
                total_chunks=total_chunks
            ))
            dabba_counter += 1

    return clusters
