import os
import asyncio
from typing import List, Dict, Any, Optional
import networkx as nx
from openai import AsyncOpenAI
from pydantic import BaseModel
from langchain_openai import ChatOpenAI
from sqlalchemy import text, select
from sqlalchemy.ext.asyncio import AsyncSession
from dotenv import load_dotenv

from ..models.db_models import Document, DocumentChunk
from .schemas import (
    TopicCluster,
    Passage,
    SectionClaim,
    DocumentExtraction,
    AlignedTopicList
)

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
EXTRACTOR_MODEL = os.getenv("OPENAI_EXTRACTOR_MODEL", "gpt-4o-mini")
ALIGNER_MODEL = os.getenv("OPENAI_ALIGNER_MODEL", "gpt-4o")
EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")

openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)


class _DocProfileOutput(BaseModel):
    doc_type: str
    execution_status: str
    governance_summary: str
    claims: List[SectionClaim]


_extractor_base = ChatOpenAI(model=EXTRACTOR_MODEL, temperature=0)
_aligner_base = ChatOpenAI(model=ALIGNER_MODEL, temperature=0)
extractor_llm = _extractor_base.with_structured_output(_DocProfileOutput, include_raw=True)
aligner_llm = _aligner_base.with_structured_output(AlignedTopicList, include_raw=True)


def _est_tokens(llm_obj: ChatOpenAI, text_str: str) -> int:
    try:
        return llm_obj.get_num_tokens(text_str)
    except Exception:
        return max(1, len(text_str) // 4)


def _usage_counts(raw_msg: Any) -> tuple:
    usage = getattr(raw_msg, "usage_metadata", None) or {}
    return usage.get("input_tokens", "N/A"), usage.get("output_tokens", "N/A")



async def _extract_single_doc(doc_id: int, filename: str, chunks: List[DocumentChunk]) -> DocumentExtraction:
    chunk_blocks = []   
    for c in chunks:
        block = f"[CHUNK {c.chunk_index} | PAGE {c.page_number}]\n{c.raw_text.strip()}"
        if c.tables_html:
            tables_str = "\n".join(c.tables_html) if isinstance(c.tables_html, list) else str(c.tables_html)
            block += f"\n[STRUCTURED TABLES IN CHUNK {c.chunk_index}]:\n{tables_str}"
        chunk_blocks.append(block)

    chunks_text = "\n\n".join(chunk_blocks)

    # previous 1-claim-per-chunk prompt:
    # prompt = f"""Analyze this document and extract its identity and section-level factual claims.
    # 1. Determine doc_type (e.g. Master Services Agreement, Statement of Work, Proposed Change Order, Security Exhibit).
    # 2. Determine execution_status: check for draft warnings, unsigned blocks, or active terms ('SIGNED/ACTIVE' vs 'DRAFT/UNSIGNED').
    # 3. For EVERY chunk, extract a concise factual claim capturing numbers, fees, days, percentages, notice periods, and governance rules.
    # DOCUMENT FILENAME: {filename}
    # {chunks_text}"""

    prompt = f"""Analyze this document and decompose it into atomic, self-contained factual claims.
1. doc_type: Identify the document's role or type (e.g. primary policy/agreement, addendum, schedule, change request, report, bill/statement, specification).
2. execution_status: State whether it is signed/approved/active or draft/unsigned/proposed, including who signed or approved it (names & titles) and any notes about missing approvals.
3. governance_summary: Summarize any precedence/hierarchy rules, conditions required to amend or override another document (e.g. required cross-references, specific approver roles, or effective dates), and parent document references.
4. claims (ATOMIC DECOMPOSITION - multiple claims per chunk_index allowed and required):
   - Do NOT squash multiple sub-clauses, bullet points, or table rows from one chunk into a single claim.
   - Emit a SEPARATE SectionClaim (using the chunk's chunk_index) for EVERY numbered sub-section, bullet item, table row, numerical figure, rate, limit/cap, prohibition, summary total, date, or approval block.
   - Preserve exact numbers, quantities, units, dates, percentages, and conditions in each claim.

DOCUMENT FILENAME: {filename}
{chunks_text}"""

    chunk_nums = [c.chunk_index for c in chunks]
    est_in = _est_tokens(_extractor_base, prompt)
    print(f"[EXTRACTOR -> START] Model: {EXTRACTOR_MODEL} | Doc #{doc_id} ({filename}) | Chunks: {chunk_nums} | Est Input Tokens: {est_in}")

    raw_res = await extractor_llm.ainvoke(prompt)
    res: _DocProfileOutput = raw_res["parsed"]
    in_tok, out_tok = _usage_counts(raw_res.get("raw"))
    print(f"[EXTRACTOR -> DONE]  Doc #{doc_id} ({filename}) | Chunks: {chunk_nums} | Input Tokens: {in_tok} | Output Tokens: {out_tok}")

    return DocumentExtraction(
        doc_id=doc_id,
        filename=filename,
        doc_type=res.doc_type,
        execution_status=res.execution_status,
        governance_summary=res.governance_summary,
        claims=res.claims
    )


# group chunks by doc and run extraction in parallel
async def extract_all_document_claims(db: AsyncSession, doc_ids: List[int]) -> List[DocumentExtraction]:
    stmt = (
        select(Document.id, Document.filename, DocumentChunk)
        .join(DocumentChunk, Document.id == DocumentChunk.document_id)
        .where(Document.id.in_(doc_ids))
        .order_by(Document.id, DocumentChunk.chunk_index)
    )
    rows = (await db.execute(stmt)).fetchall()

    doc_map: Dict[int, Dict[str, Any]] = {}
    for d_id, fname, chunk in rows:
        if d_id not in doc_map:
            doc_map[d_id] = {"filename": fname, "chunks": []}
        doc_map[d_id]["chunks"].append(chunk)

    tasks = [
        _extract_single_doc(d_id, data["filename"], data["chunks"])
        for d_id, data in doc_map.items()
    ]
    return list(await asyncio.gather(*tasks))


async def build_topic_clusters(
    db: AsyncSession,
    doc_ids: List[int],
    similarity_threshold: float = 0.45,
    max_pairs: int = 500,
    doc_extractions: Optional[List[Dict[str, Any]]] = None
) -> List[TopicCluster]:
    if len(doc_ids) < 2:
        return []

    # reuse extractions from graph node if already ran, else run here
    extractions = (
        [DocumentExtraction(**e) for e in doc_extractions]
        if doc_extractions
        else await extract_all_document_claims(db, doc_ids)
    )
    if not extractions:
        return []

    stmt = select(DocumentChunk).where(DocumentChunk.document_id.in_(doc_ids))
    all_chunks = (await db.execute(stmt)).scalars().all()
    chunk_lookup = {(c.document_id, c.chunk_index): c for c in all_chunks}
    doc_lookup = {e.doc_id: e for e in extractions}

    # keep all atomic claims per chunk instead of overwriting with a single dict entry
    # claim_lookup = {(e.doc_id, cl.chunk_index): cl for e in extractions for cl in e.claims}
    claims_by_chunk: Dict[Any, List[SectionClaim]] = {}
    for e in extractions:
        for cl in e.claims:
            claims_by_chunk.setdefault((e.doc_id, cl.chunk_index), []).append(cl)

    summary_blocks = []
    governance_lines = []
    for e in extractions:
        gov_info = f" | GOVERNANCE: {e.governance_summary}" if e.governance_summary else ""
        governance_lines.append(
            f"- Doc #{e.doc_id} ({e.filename}) [{e.doc_type} | {e.execution_status}]{gov_info}"
        )
        lines = [f"  - chunk_index={cl.chunk_index} ({cl.section_title}): {cl.claim}" for cl in e.claims]
        summary_blocks.append(
            f"=== DOC ID: {e.doc_id} | {e.filename} | TYPE: {e.doc_type} | STATUS: {e.execution_status}{gov_info} ===\n"
            + "\n".join(lines)
        )

    global_governance_context = "\n".join(governance_lines)

    # previous coarse alignment prompt:
    # align_prompt = f"""You are a Legal & Commercial Reconciliation Architect.
    # Group the extracted section claims across these documents into comparative reconciliation topics (e.g., Project Fees & Pricing, Invoice Payment Window, Service Availability & SLA, Security Incident Notice, Contract Governance & Amendment Validity).
    # Rules:
    # - Every commercial, operational, financial, or governance topic shared across 2 or more documents must become a topic cluster.
    # - Include all relevant (doc_id, chunk_index) pairs for each topic (a doc can have multiple chunks in the same topic, like preamble + signature status).
    # EXTRACTED DOCUMENT CLAIMS:
    # {chr(10).join(summary_blocks)}"""

    align_prompt = f"""You are a meticulous Cross-Document Reconciliation Architect.
Align the extracted atomic claims across these documents into clean, exhaustive comparative topic clusters.

CRITICAL CLUSTERING REQUIREMENTS:

1. EXHAUSTIVE SUBSTANTIVE COVERAGE (NO RELEVANT CLAIM OR CHUNK LEFT BEHIND):
   Every substantive commercial, financial, operational, and legal subject shared across 2 or more documents MUST be aligned into its own dedicated topic cluster.
   Specifically check and align:
   a) PAYMENT TERMS & INVOICE PAYMENT SCHEDULE:
      - Pair all payment terms and windows (e.g. Net 45 in primary agreement, Net 30 in SOW, Net 15 on Invoices).
      - If payment terms appear in an invoice header/preamble chunk (such as chunk 0), you MUST include that chunk in this topic.
   b) LATE PAYMENT FEES & SERVICE PENALTIES:
      - Pair all late payment interest rates, fees, and operational consequences (e.g. 1.0%/mo in primary agreement, 2.0%/mo in SOW, 3.0%/mo penalty and sandbox/service suspension in invoice remittance chunks).
   c) NOT-TO-EXCEED (NTE) BUDGET CAPS & CUMULATIVE SPEND:
      - Pair contract NTE budget caps (original SOW cap, Change Order revised cap) with cumulative spend totals and billing trackers (e.g. invoice financial summary & cumulative total billed chunk).
   d) PERFORMANCE WARRANTIES & DEFECT REMEDIES:
      - Pair warranty durations, scope of deliverables covered, and post-warranty defect remedy terms (e.g. 90-day warranty on all deliverables at no charge vs 30-day warranty on ETL only with T&M billing).
   e) TRAVEL & EXPENSE REIMBURSEMENT POLICIES:
      - Pair travel pre-approval requirements and allowances (e.g. primary agreement Travel Authorization Form requirement vs SOW unapproved monthly travel allowance vs Change Order travel freeze vs Invoice travel line items).
   f) LABOR RATES & RESOURCE ALLOCATION:
      - Pair hourly rate cards and caps across primary agreements, SOWs, and Change Orders with billed hourly rates in invoice line items.
   g) INTELLECTUAL PROPERTY & DELIVERABLE OWNERSHIP:
      - Pair work made for hire / ownership clauses with vendor retention or restrictive license clauses.
   h) TERMINATION FOR CONVENIENCE & PENALTIES:
      - Pair termination notice periods, convenience rights (Client vs Vendor), and early termination fees.
   i) LIMITATION OF LIABILITY:
      - Pair aggregate liability caps across agreements and SOWs.
   j) GOVERNING LAW, VENUE & DISPUTE FORUM:
      - Pair governing law (e.g. NY vs CA) and dispute resolution forums (court vs arbitration).
   k) GOVERNANCE & PRECEDENCE:
      - Pair order of precedence rules and signature requirements with signature blocks and override attempts across documents.

2. MULTI-TOPIC CHUNKS:
   - A single chunk frequently covers multiple distinct subjects (e.g. a chunk may contain Payment Terms, Late Fees, and Travel; another chunk may contain Warranty and Liability; an invoice chunk may contain Line Items, Cumulative Financial Summary, and Remittance Penalties).
   - You MUST include a chunk in EVERY topic cluster it is relevant to. Never omit a chunk from a topic cluster just because it was assigned to another.

3. HEADER AND FOOTER CHUNKS:
   - Do NOT create a cluster purely for routine chronological dates (e.g. SOW dated after MSA).
   - However, any header or footer chunk that specifies commercial terms (payment terms, billing periods, cumulative budget trackers, late penalties, or remittance terms) MUST be included in the corresponding substantive clusters.

4. ONE CLUSTER PER UNIQUE SUBJECT (ZERO DUPLICATE TOPICS):
   - For each distinct subject, include ALL documents that discuss it in ONE single cluster. Do not create pairwise duplicate clusters (e.g. combine all documents discussing payment terms into one "Payment Terms & Invoicing Schedule" cluster).

5. Include all relevant (doc_id, chunk_index) pairs for each topic cluster.

EXTRACTED DOCUMENT CLAIMS:
{chr(10).join(summary_blocks)}"""

    all_chunk_refs = [f"Doc{c.document_id}:C{c.chunk_index}" for c in all_chunks]
    est_in = _est_tokens(_aligner_base, align_prompt)
    print(f"[ALIGNER -> START]   Model: {ALIGNER_MODEL} | Docs: {doc_ids} | Chunks ({len(all_chunk_refs)}): {all_chunk_refs} | Est Input Tokens: {est_in}")

    raw_aligned = await aligner_llm.ainvoke(align_prompt)
    aligned: AlignedTopicList = raw_aligned["parsed"]
    in_tok, out_tok = _usage_counts(raw_aligned.get("raw"))
    print(f"[ALIGNER -> DONE]    Docs: {doc_ids} | Clusters Created: {len(aligned.topics)} | Input Tokens: {in_tok} | Output Tokens: {out_tok}")

    clusters: List[TopicCluster] = []
    seen_chunk_sets: Dict[Any, TopicCluster] = {}
    dabba_counter = 1

    # map aligned pairs back to actual chunks from db
    for topic in aligned.topics:
        passages: List[Passage] = []
        matched_docs = set()
        seen_pairs = set()

        for m in topic.matched_chunks:
            key = (m.doc_id, m.chunk_index)
            if key in seen_pairs or key not in chunk_lookup:
                continue
            seen_pairs.add(key)

            chunk_obj = chunk_lookup[key]
            doc_ext = doc_lookup.get(m.doc_id)
            chunk_claims = claims_by_chunk.get(key, [])
            combined_claims = " | ".join(f"[{cl.section_title}] {cl.claim}" for cl in chunk_claims) if chunk_claims else None
            matched_docs.add(m.doc_id)

            passage_text = chunk_obj.raw_text
            if chunk_obj.tables_html:
                t_html = "\n".join(chunk_obj.tables_html) if isinstance(chunk_obj.tables_html, list) else str(chunk_obj.tables_html)
                passage_text = f"{passage_text}\n\n[Table HTML]:\n{t_html}"

            passages.append(Passage(
                doc_id=m.doc_id,
                filename=doc_ext.filename if doc_ext else None,
                doc_type=doc_ext.doc_type if doc_ext else None,
                execution_status=doc_ext.execution_status if doc_ext else None,
                chunk_index=m.chunk_index,
                page_number=chunk_obj.page_number,
                extracted_claim=combined_claims,
                text=passage_text
            ))

        if len(matched_docs) >= 2:
            # merge topics that point to the exact same set of chunks
            chunk_signature = frozenset(seen_pairs)
            if chunk_signature in seen_chunk_sets:
                existing = seen_chunk_sets[chunk_signature]
                existing.topic_hint = f"{existing.topic_hint}; {topic.topic_name}"
                continue

            new_cluster = TopicCluster(
                dabba_id=dabba_counter,
                topic_hint=topic.topic_name,
                governance_context=global_governance_context,
                document_ids=sorted(matched_docs),
                passages=passages,
                total_chunks=len(passages)
            )
            seen_chunk_sets[chunk_signature] = new_cluster
            clusters.append(new_cluster)
            dabba_counter += 1

    return clusters


# previous outline + pgvector anchor approach
# async def extract_document_outlines(db: AsyncSession, doc_ids: List[int]) -> str:
#     stmt = (
#         select(Document.id, Document.filename, DocumentChunk.chunk_index, DocumentChunk.page_number, DocumentChunk.raw_text)
#         .join(DocumentChunk, Document.id == DocumentChunk.document_id)
#         .where(Document.id.in_(doc_ids))
#         .order_by(Document.id, DocumentChunk.chunk_index)
#     )
#     res = await db.execute(stmt)
#     rows = res.fetchall()
#
#     doc_outlines: Dict[int, Dict[str, Any]] = {}
#     for doc_id, filename, chunk_idx, page_num, raw_text in rows:
#         if doc_id not in doc_outlines:
#             doc_outlines[doc_id] = {
#                 "filename": filename,
#                 "headings": []
#             }
#
#         lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
#         heading_snippet = " | ".join(lines[:2]) if lines else "Untitled Section"
#         if len(heading_snippet) > 160:
#             heading_snippet = heading_snippet[:157] + "..."
#
#         doc_outlines[doc_id]["headings"].append(
#             f"  - Chunk {chunk_idx} (Page {page_num}): {heading_snippet}"
#         )
#
#     formatted_docs = []
#     for doc_id, data in doc_outlines.items():
#         headings_text = "\n".join(data["headings"])
#         formatted_docs.append(f"=== DOCUMENT ID: {doc_id} ({data['filename']}) ===\n{headings_text}")
#
#     return "\n\n".join(formatted_docs)
#
#
# async def discover_dynamic_topic_anchors(outlines_text: str):
#     system_prompt = """You are a Legal & Commercial Reconciliation Architect.
# Given the document structures and headings across interrelated documents (MSA, SOW, Amendments, Invoices), identify 3 to 6 key comparative topics where commercial, financial, operational, or legal terms must be cross-reconciled.
#
# For each topic:
# 1. topic_name: Professional topic title (e.g., 'Hourly Billing Rates & Rate Caps', 'Payment Window & Late Penalties', 'Travel & Expense Reimbursements', 'Service Level Agreement', 'Intellectual Property Ownership').
# 2. description: Brief rationale of what is being compared.
# 3. search_query: A rich, keyword-dense semantic search query combining contract terms, role titles, and invoice line-item keywords so vector search can pull the relevant chunks from every document.
# """
#
#     prompt = f"""{system_prompt}
#
# DOCUMENTS SECTION HEADINGS:
# {outlines_text}
#
# Provide 3 to 6 key comparative topics:"""
#
#     try:
#         discovered = await structured_topic_llm.ainvoke(prompt)
#         if discovered and discovered.topics:
#             return discovered.topics
#     except Exception as e:
#         print(f"[TOPIC DISCOVERY WARNING] Error discovering topics: {e}. Falling back to default anchors.")
#
#     return []
#
#
# async def build_topic_clusters_anchor_legacy(
#     db: AsyncSession,
#     doc_ids: List[int],
#     similarity_threshold: float = 0.45,
#     max_pairs: int = 500
# ) -> List[TopicCluster]:
#     if len(doc_ids) < 2:
#         return []
#
#     outlines = await extract_document_outlines(db, doc_ids)
#     if not outlines:
#         return []
#
#     anchors = await discover_dynamic_topic_anchors(outlines)
#     if not anchors:
#         return []
#
#     queries = [a.search_query for a in anchors]
#     emb_res = await openai_client.embeddings.create(model=EMBEDDING_MODEL, input=queries)
#     query_embeddings = [item.embedding for item in emb_res.data]
#
#     clusters: List[TopicCluster] = []
#     dabba_counter = 1
#
#     for anchor, q_emb in zip(anchors, query_embeddings):
#         vector_str = f"[{','.join(str(x) for x in q_emb)}]"
#
#         sql = text("""
#             SELECT DISTINCT ON (document_id)
#                 document_id,
#                 chunk_index,
#                 page_number,
#                 (1 - (embedding <=> CAST(:topic_vec AS vector))) AS similarity
#             FROM document_chunks
#             WHERE document_id = ANY(:doc_ids)
#               AND embedding IS NOT NULL
#               AND (1 - (embedding <=> CAST(:topic_vec AS vector))) >= :threshold
#             ORDER BY
#                 document_id,
#                 (embedding <=> CAST(:topic_vec AS vector)) ASC;
#         """)
#
#         res = await db.execute(sql, {
#             "doc_ids": doc_ids,
#             "topic_vec": vector_str,
#             "threshold": similarity_threshold
#         })
#         matched_rows = res.fetchall()
#
#         if len(matched_rows) < 2:
#             continue
#
#         all_dabba_passages: List[Passage] = []
#         total_chunks = 0
#         matched_doc_ids: List[int] = []
#
#         for row in matched_rows:
#             d_id = row[0]
#             target_idx = row[1]
#             page_num = row[2]
#             matched_doc_ids.append(d_id)
#
#             candidate_indices = [idx for idx in [target_idx - 1, target_idx, target_idx + 1] if idx >= 0]
#
#             stmt = (
#                 select(DocumentChunk)
#                 .where(
#                     DocumentChunk.document_id == d_id,
#                     DocumentChunk.chunk_index.in_(candidate_indices)
#                 )
#                 .order_by(DocumentChunk.chunk_index)
#             )
#             c_res = await db.execute(stmt)
#             fetched_chunks = c_res.scalars().all()
#
#             if fetched_chunks:
#                 total_chunks += len(fetched_chunks)
#                 combined_text = "\n\n".join([c.raw_text for c in fetched_chunks])
#                 first_page = fetched_chunks[0].page_number
#
#                 all_dabba_passages.append(Passage(
#                     doc_id=d_id,
#                     chunk_index=target_idx,
#                     page_number=first_page,
#                     text=combined_text
#                 ))
#
#         if len(all_dabba_passages) >= 2:
#             clusters.append(TopicCluster(
#                 dabba_id=dabba_counter,
#                 topic_hint=anchor.topic_name,
#                 document_ids=matched_doc_ids,
#                 passages=all_dabba_passages,
#                 total_chunks=total_chunks
#             ))
#             dabba_counter += 1
#
#     return clusters



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
