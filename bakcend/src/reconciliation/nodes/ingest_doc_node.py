import asyncio
from typing import Dict, Any
from sqlalchemy import select

from ...database import AsyncSessionLocal
from ...models.db_models import Document, DocumentChunk
from ...websocket.manager import ws_manager
from ...ingestion.pipeline import run_document_ingestion
from ..schemas import ReconciliationState


# node 1 - ingest and chunk docs if not already parsed
async def ingest_documents_node(state: ReconciliationState) -> Dict[str, Any]:
    thread_id = state.get("thread_id")
    doc_paths = state.get("doc_paths") or []
    doc_ids = list(state.get("doc_ids") or [])

    if not doc_paths and doc_ids:
        return {"doc_ids": doc_ids}

    if not doc_paths:
        return {"doc_ids": doc_ids}

    if thread_id:
        await ws_manager.broadcast(thread_id, "STAGE_CHANGED", {
            "stage": "INGESTION",
            "message": f"Ingesting and chunking {len(doc_paths)} documents..."
        })

    async def ingest_with_broadcast(item: Dict[str, Any]):
        d_id = item["doc_id"]
        f_path = item["file_path"]
        f_name = item.get("filename", f"Doc #{d_id}")

        async with AsyncSessionLocal() as session:
            doc = await session.get(Document, d_id)
            if doc and doc.status == "PARSED":
                chunks_res = await session.execute(
                    select(DocumentChunk).where(DocumentChunk.document_id == d_id)
                )
                chunk_count = len(chunks_res.scalars().all())
                if thread_id:
                    await ws_manager.broadcast(thread_id, "DOC_INGESTION_PROGRESS", {
                        "doc_id": d_id,
                        "filename": f_name,
                        "status": "PARSED",
                        "chunks_count": chunk_count
                    })
                return

        if thread_id:
            await ws_manager.broadcast(thread_id, "DOC_INGESTION_START", {
                "doc_id": d_id,
                "filename": f_name,
                "status": "PROCESSING"
            })

        await run_document_ingestion(doc_id=d_id, file_path=f_path)

        async with AsyncSessionLocal() as session:
            chunks_res = await session.execute(
                select(DocumentChunk).where(DocumentChunk.document_id == d_id)
            )
            chunk_count = len(chunks_res.scalars().all())

        if thread_id:
            await ws_manager.broadcast(thread_id, "DOC_INGESTION_PROGRESS", {
                "doc_id": d_id,
                "filename": f_name,
                "status": "PARSED",
                "chunks_count": chunk_count
            })

    await asyncio.gather(*[ingest_with_broadcast(item) for item in doc_paths], return_exceptions=True)

    final_doc_ids = [d["doc_id"] for d in doc_paths]

    if thread_id:
        await ws_manager.broadcast(thread_id, "INGESTION_COMPLETE", {
            "message": "All documents successfully ingested and embedded.",
            "doc_ids": final_doc_ids
        })

    return {"doc_ids": final_doc_ids}

