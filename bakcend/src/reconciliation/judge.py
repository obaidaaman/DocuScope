import os
import asyncio
from typing import List, Optional
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv

from .schemas import TopicCluster, JudgeVerdict, ClusterVerdictList

load_dotenv()

JUDGE_MODEL = os.getenv("OPENAI_JUDGE_MODEL", "gpt-6-sol")
llm = ChatOpenAI(
    model=JUDGE_MODEL,
    reasoning_effort="medium",
    use_responses_api=True,
)
# structured_judge = llm.with_structured_output(JudgeVerdict)
structured_judge = llm.with_structured_output(ClusterVerdictList, include_raw=True)


def _est_tokens(text_str: str) -> int:
    try:
        return llm.get_num_tokens(text_str)
    except Exception:
        return max(1, len(text_str) // 4)

# previous single-verdict judge prompt:
# JUDGE_SYSTEM_PROMPT = """You are a meticulous, impartial Legal & Contractual Reconciliation Judge.
# Your mission is to compare passages from multiple documents that discuss the same underlying topic.
# TASK OBJECTIVES:
# 1. TOPIC NAME: Assign a short, professional topic name (e.g. 'Vendor Payment Terms', 'Service Level Agreement', 'Governing Law').
# 2. STATUS: Determine whether the documents are in 'CONFLICT' or 'AGREEMENT'.
# ...
# """

JUDGE_SYSTEM_PROMPT = """You are a meticulous, impartial Cross-Document Reconciliation Judge.
Your mission is to exhaustively compare passages and tables from multiple documents within a topic cluster and return EVERY genuine, distinct conflict or agreement found.

CRITICAL AUDIT RULES:
1. EXHAUSTIVE MULTI-VERDICT EXTRACTION:
   - A single cluster may contain passages covering multiple sub-clauses, multiple items/entries, or multiple table rows.
   - Do NOT stop after finding one conflict. Emit a SEPARATE JudgeVerdict in `verdicts` for each distinct genuine factual, numerical, operational, policy, or legal discrepancy in the cluster.
2. STRICT NON-CONFLICT GUARDRAILS (NEVER HALLUCINATE FALSE POSITIVES):
   - Normal chronological progression is NOT a conflict: a subordinate, follow-up, amendment, or billing document having a later Effective Date / Invoice Date than a primary governing document is completely normal.
   - Valid amendments / change orders modifying scope, timeline, or budget of their parent document are NOT conflicts with the original parent document — UNLESS they violate an explicit precedence/signatory rule or are themselves breached by downstream execution/billing.
   - Never compare unrelated metrics (e.g. do NOT compare a Liability Cap against a Budget / Not-To-Exceed Cap).
   - If a cluster contains no genuine contradiction (only normal chronology or valid amendment), mark status as 'AGREEMENT' with severity 'NONE'.
3. GOVERNANCE & PRECEDENCE CHECK:
   - Check the GLOBAL DOCUMENT GOVERNANCE CONTEXT. If a primary/governing document specifies conditions required to amend or override its terms (such as explicit section references or specific approver/signatory roles), verify whether subordinate documents satisfy those conditions. Any deviation without required override authority is an invalid override and a HIGH severity CONFLICT.
4. NUMERICAL, TABLE & RULE VERIFICATION:
   - Cross-check every table row, rate/quantity, authorization limit, prohibition/freeze, unallocated item, added fee/surcharge, and cumulative total against the governing caps, timelines, and rules.
5. STRICT EVIDENCE ATTRIBUTION (ZERO MISATTRIBUTION):
   - Every item in `evidence` MUST be a verbatim quote copied from that exact `doc_id` and `page_number` header in the prompt. NEVER attach Document A's text to Document B's `doc_id`, and never fabricate quotes.
6. VERDICT FIELDS:
   - topic_name: Specific, descriptive title for the discrepancy or agreement.
   - status: 'CONFLICT' if documents genuinely disagree, violate a cap/prohibition/rule, or attempt an unauthorized override; 'AGREEMENT' if consistent.
   - severity: 'HIGH' for material numerical/financial discrepancies, unauthorized items, cap breaches, invalid overrides, or direct rule contradictions; 'MEDIUM' for minor variance; 'LOW' for cosmetic differences; 'NONE' for agreements.
   - explanation: Detailed explanation citing exact figures, clauses, and why a deviation or override is valid or invalid.
"""

async def evaluate_single_dabba(
    cluster: TopicCluster,
    semaphore: asyncio.Semaphore
) -> List[JudgeVerdict]:
    async with semaphore:
        passages_text = []
        for p in cluster.passages:
            # include doc name, type and status so judge knows what's signed vs draft
            meta = f"DOCUMENT ID: {p.doc_id}"
            if p.filename:
                meta += f" | FILE: {p.filename}"
            if p.doc_type:
                meta += f" | TYPE: {p.doc_type}"
            if p.execution_status:
                meta += f" | STATUS: {p.execution_status}"
            meta += f" | PAGE: {p.page_number} | CHUNK: {p.chunk_index}"

            claim_line = f"Extracted Claims: {p.extracted_claim}\n" if p.extracted_claim else ""
            passages_text.append(
                f"=== [{meta}] ===\n{claim_line}Verbatim Text:\n{p.text.strip()}"
            )
        formatted_context = "\n\n".join(passages_text)

        topic_header = f"RECONCILIATION TOPIC: {cluster.topic_hint}" if cluster.topic_hint else f"TOPIC CLUSTER #{cluster.dabba_id}"
        gov_block = (
            f"GLOBAL DOCUMENT GOVERNANCE & HIERARCHY CONTEXT:\n{cluster.governance_context}\n\n"
            if cluster.governance_context
            else ""
        )

        prompt = f"""{JUDGE_SYSTEM_PROMPT}

{gov_block}{topic_header}:
{formatted_context}

Provide all structured verdicts for this cluster:"""

        chunk_refs = [f"Doc{p.doc_id}:C{p.chunk_index}" for p in cluster.passages]
        est_in = _est_tokens(prompt)
        print(f"[JUDGE -> START]     Model: {JUDGE_MODEL} | Dabba #{cluster.dabba_id} ({cluster.topic_hint}) | Chunks: {chunk_refs} | Est Input Tokens: {est_in}")

        try:
            raw_res = await structured_judge.ainvoke(prompt)
            res: ClusterVerdictList = raw_res["parsed"]
            usage = getattr(raw_res.get("raw"), "usage_metadata", None) or {}
            in_tok = usage.get("input_tokens", "N/A")
            out_tok = usage.get("output_tokens", "N/A")
            print(f"[JUDGE -> DONE]      Dabba #{cluster.dabba_id} ({cluster.topic_hint}) | Chunks: {chunk_refs} | Input Tokens: {in_tok} | Output Tokens: {out_tok}")
            return res.verdicts if res and res.verdicts else []
        except Exception as e:
            print(f"[JUDGE ERROR] Failed to evaluate Dabba #{cluster.dabba_id}: {e}")
            return []

async def run_llm_judge_pipeline(
    clusters: List[TopicCluster],
    max_concurrency: int = 5
) -> List[JudgeVerdict]:
    if not clusters:
        return []

    semaphore = asyncio.Semaphore(max_concurrency)
    tasks = [evaluate_single_dabba(c, semaphore) for c in clusters]
    raw_results = await asyncio.gather(*tasks, return_exceptions=True)

    verdicts: List[JudgeVerdict] = []
    for res in raw_results:
        if isinstance(res, list):
            verdicts.extend(res)
        elif isinstance(res, JudgeVerdict):
            verdicts.append(res)

    return verdicts
