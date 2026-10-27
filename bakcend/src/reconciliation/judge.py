import os
import asyncio
from typing import List, Optional
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv

from .schemas import TopicCluster, JudgeVerdict

load_dotenv()

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
llm = ChatOpenAI(model=OPENAI_MODEL, temperature=0)
structured_judge = llm.with_structured_output(JudgeVerdict)

JUDGE_SYSTEM_PROMPT = """You are a meticulous, impartial Legal & Contractual Reconciliation Judge.
Your mission is to compare passages from multiple documents that discuss the same underlying topic.

TASK OBJECTIVES:
1. TOPIC NAME: Assign a short, professional topic name (e.g. 'Vendor Payment Terms', 'Service Level Agreement', 'Governing Law').
2. STATUS: Determine whether the documents are in 'CONFLICT' or 'AGREEMENT'.
   - 'CONFLICT': If there are contradictory numbers, dates, payment periods, obligations, liabilities, delivery addresses, or differing terms between any documents.
   - 'AGREEMENT': If all documents are consistent, compatible, or mutually reaffirming on this topic.
3. SEVERITY:
   - 'HIGH': Material financial, legal, delivery, or liability contradiction.
   - 'MEDIUM': Minor administrative, procedural, or wording variance.
   - 'LOW': Cosmetic differences.
   - 'NONE': For consistent agreements.
4. EXPLANATION: Provide a clear, objective summary explaining exactly what agrees or where the contradiction lies.
5. EVIDENCE: Provide verbatim quotes directly cited from each document with the corresponding doc_id and page_number. Do not fabricate quotes.
"""

async def evaluate_single_dabba(
    cluster: TopicCluster,
    semaphore: asyncio.Semaphore
) -> Optional[JudgeVerdict]:
    async with semaphore:
        passages_text = []
        for p in cluster.passages:
            passages_text.append(
                f"=== [DOCUMENT ID: {p.doc_id} | PAGE: {p.page_number} | CHUNK: {p.chunk_index}] ===\n{p.text.strip()}"
            )
        formatted_context = "\n\n".join(passages_text)

        topic_header = f"RECONCILIATION TOPIC: {cluster.topic_hint}" if cluster.topic_hint else f"TOPIC CLUSTER #{cluster.dabba_id}"

        prompt = f"""{JUDGE_SYSTEM_PROMPT}

{topic_header}:
{formatted_context}

Provide your structured verdict:"""

        try:
            verdict: JudgeVerdict = await structured_judge.ainvoke(prompt)
            return verdict
        except Exception as e:
            print(f"[JUDGE ERROR] Failed to evaluate Dabba #{cluster.dabba_id}: {e}")
            return None

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
        if isinstance(res, JudgeVerdict):
            verdicts.append(res)

    return verdicts
