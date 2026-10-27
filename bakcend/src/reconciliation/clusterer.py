import os
from typing import List, Dict, Any, Optional
import networkx as nx
from openai import AsyncOpenAI
from langchain_openai import ChatOpenAI
from sqlalchemy import text, select
from sqlalchemy.ext.asyncio import AsyncSession
from dotenv import load_dotenv

from ..models.db_models import Document, DocumentChunk
from .schemas import TopicCluster, Passage, TopicAnchor, DiscoveredTopics

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")

openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)
structured_topic_llm = ChatOpenAI(model=OPENAI_MODEL, temperature=0).with_structured_output(DiscoveredTopics)


# ============================================================================
# DYNAMIC TOPIC ANCHOR & CONTEXT EXPANSION CLUSTERING (ACTIVE ENGINE)
# ============================================================================

async def extract_document_outlines(db: AsyncSession, doc_ids: List[int]) -> str:
    """
    Extracts high-level document outlines by taking the title/first non-empty lines
    of every chunk for the selected documents. This gives a 360-degree TOC of the documents
    without token bloating.
    """
    stmt = (
        select(Document.id, Document.filename, DocumentChunk.chunk_index, DocumentChunk.page_number, DocumentChunk.raw_text)
        .join(DocumentChunk, Document.id == DocumentChunk.document_id)
        .where(Document.id.in_(doc_ids))
        .order_by(Document.id, DocumentChunk.chunk_index)
    )
    res = await db.execute(stmt)
    rows = res.fetchall()

    doc_outlines: Dict[int, Dict[str, Any]] = {}
    for doc_id, filename, chunk_idx, page_num, raw_text in rows:
        if doc_id not in doc_outlines:
            doc_outlines[doc_id] = {
                "filename": filename,
                "headings": []
            }
        
        # Take the first 2-3 non-empty lines as section title/header
        lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
        heading_snippet = " | ".join(lines[:2]) if lines else "Untitled Section"
        if len(heading_snippet) > 160:
            heading_snippet = heading_snippet[:157] + "..."
            
        doc_outlines[doc_id]["headings"].append(
            f"  - Chunk {chunk_idx} (Page {page_num}): {heading_snippet}"
        )

    formatted_docs = []
    for doc_id, data in doc_outlines.items():
        headings_text = "\n".join(data["headings"])
        formatted_docs.append(f"=== DOCUMENT ID: {doc_id} ({data['filename']}) ===\n{headings_text}")

    return "\n\n".join(formatted_docs)


async def discover_dynamic_topic_anchors(outlines_text: str) -> List[TopicAnchor]:
    """
    Calls gpt-4o-mini to discover 3-6 comparative topics where terms or figures
    should be cross-reconciled across the documents.
    """
    system_prompt = """You are a Legal & Commercial Reconciliation Architect.
Given the document structures and headings across interrelated documents (MSA, SOW, Amendments, Invoices), identify 3 to 6 key comparative topics where commercial, financial, operational, or legal terms must be cross-reconciled.

For each topic:
1. topic_name: Professional topic title (e.g., 'Hourly Billing Rates & Rate Caps', 'Payment Window & Late Penalties', 'Travel & Expense Reimbursements', 'Service Level Agreement', 'Intellectual Property Ownership').
2. description: Brief rationale of what is being compared.
3. search_query: A rich, keyword-dense semantic search query combining contract terms, role titles, and invoice line-item keywords so vector search can pull the relevant chunks from every document.
"""

    prompt = f"""{system_prompt}

DOCUMENTS SECTION HEADINGS:
{outlines_text}

Provide 3 to 6 key comparative topics:"""

    try:
        discovered: DiscoveredTopics = await structured_topic_llm.ainvoke(prompt)
        if discovered and discovered.topics:
            return discovered.topics
    except Exception as e:
        print(f"[TOPIC DISCOVERY WARNING] Error discovering topics: {e}. Falling back to default anchors.")

    # Resilient fallback default anchors in case of API failure
    return [
        TopicAnchor(
            topic_name="Hourly Billing Rates & Role Pricing",
            description="Hourly rates and role billing ceilings across agreements and invoices",
            search_query="hourly billing rates unit rate per hour Principal Cloud Architect Senior Data Engineer DevOps Project Manager rate card ceiling"
        ),
        TopicAnchor(
            topic_name="Payment Terms & Invoicing Window",
            description="Payment window, due dates, and late payment interest fees",
            search_query="payment terms payment window Net 45 Net 30 Net 15 invoice receipt due date late fee interest penalty"
        ),
        TopicAnchor(
            topic_name="Travel & Expense Reimbursement Policy",
            description="Travel, lodging, and out-of-pocket expenses authorization and reimbursement",
            search_query="travel lodging meal expenses out-of-pocket reimbursement prior written approval authorization expense freeze"
        ),
        TopicAnchor(
            topic_name="Service Level Agreement & Uptime",
            description="System availability, SLA uptime percentage, and service credits",
            search_query="service level agreement SLA production server uptime percentage 99.9% 99.95% service credit penalty breach"
        )
    ]


async def build_topic_clusters(
    db: AsyncSession,
    doc_ids: List[int],
    similarity_threshold: float = 0.45,
    max_pairs: int = 500
) -> List[TopicCluster]:
    """
    Production Topic Anchor Clustering:
    1. Extracts full document outlines across all selected documents.
    2. Dynamically discovers 3-6 core comparative topics via gpt-4o-mini.
    3. Batch embeds topic queries with text-embedding-3-small.
    4. Finds the best matching chunk k for each document via pgvector.
    5. Expands context window to include [k-1, k, k+1] chunks for complete legal context.
    6. Returns clean, named TopicClusters.
    """
    if len(doc_ids) < 2:
        return []

    # 1. Extract structural outlines
    outlines = await extract_document_outlines(db, doc_ids)
    if not outlines:
        return []

    # 2. Discover dynamic topics
    anchors = await discover_dynamic_topic_anchors(outlines)
    if not anchors:
        return []

    # 3. Batch embed all search queries in a single OpenAI call
    queries = [a.search_query for a in anchors]
    emb_res = await openai_client.embeddings.create(model=EMBEDDING_MODEL, input=queries)
    query_embeddings = [item.embedding for item in emb_res.data]

    clusters: List[TopicCluster] = []
    dabba_counter = 1

    # 4. For each topic, match best chunk across each document
    for anchor, q_emb in zip(anchors, query_embeddings):
        vector_str = f"[{','.join(str(x) for x in q_emb)}]"

        sql = text("""
            SELECT DISTINCT ON (document_id)
                document_id,
                chunk_index,
                page_number,
                (1 - (embedding <=> CAST(:topic_vec AS vector))) AS similarity
            FROM document_chunks
            WHERE document_id = ANY(:doc_ids)
              AND embedding IS NOT NULL
              AND (1 - (embedding <=> CAST(:topic_vec AS vector))) >= :threshold
            ORDER BY 
                document_id, 
                (embedding <=> CAST(:topic_vec AS vector)) ASC;
        """)

        res = await db.execute(sql, {
            "doc_ids": doc_ids,
            "topic_vec": vector_str,
            "threshold": similarity_threshold
        })
        matched_rows = res.fetchall()

        # Topic must appear in at least 2 documents to form a reconciliation cluster
        if len(matched_rows) < 2:
            continue

        all_dabba_passages: List[Passage] = []
        total_chunks = 0
        matched_doc_ids: List[int] = []

        # 5. For each document, expand to [k-1, k, k+1] chunks
        for row in matched_rows:
            d_id = row[0]
            target_idx = row[1]
            page_num = row[2]
            matched_doc_ids.append(d_id)

            candidate_indices = [idx for idx in [target_idx - 1, target_idx, target_idx + 1] if idx >= 0]

            stmt = (
                select(DocumentChunk)
                .where(
                    DocumentChunk.document_id == d_id,
                    DocumentChunk.chunk_index.in_(candidate_indices)
                )
                .order_by(DocumentChunk.chunk_index)
            )
            c_res = await db.execute(stmt)
            fetched_chunks = c_res.scalars().all()

            if fetched_chunks:
                total_chunks += len(fetched_chunks)
                combined_text = "\n\n".join([c.raw_text for c in fetched_chunks])
                first_page = fetched_chunks[0].page_number

                all_dabba_passages.append(Passage(
                    doc_id=d_id,
                    chunk_index=target_idx,
                    page_number=first_page,
                    text=combined_text
                ))

        if len(all_dabba_passages) >= 2:
            clusters.append(TopicCluster(
                dabba_id=dabba_counter,
                topic_hint=anchor.topic_name,
                document_ids=matched_doc_ids,
                passages=all_dabba_passages,
                total_chunks=total_chunks
            ))
            dabba_counter += 1

    return clusters



# Graph-Based Connected Components Clustering 

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


async def build_topic_clusters_graph_legacy(
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
