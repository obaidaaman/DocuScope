from typing import Dict, Any

from ...database import AsyncSessionLocal
from ...websocket.manager import ws_manager
from ..clusterer import extract_all_document_claims
from ..schemas import ReconciliationState


# node 2 - extract doc profile and claims per chunk in parallel
async def extract_claims_node(state: ReconciliationState) -> Dict[str, Any]:
    thread_id = state.get("thread_id")
    doc_ids = state.get("doc_ids", [])

    if not doc_ids or len(doc_ids) < 2:
        error_msg = f"At least 2 documents are required for reconciliation. Found {len(doc_ids)}."
        if thread_id:
            await ws_manager.broadcast(thread_id, "PIPELINE_ERROR", {"message": error_msg})
        return {"doc_extractions": [], "error": error_msg}

    if thread_id:
        await ws_manager.broadcast(thread_id, "STAGE_CHANGED", {
            "stage": "CLAIM_EXTRACTION",
            "message": f"Identifying document types and extracting claims across {len(doc_ids)} documents..."
        })

    async with AsyncSessionLocal() as session:
        try:
            extractions = await extract_all_document_claims(db=session, doc_ids=doc_ids)
            if thread_id:
                await ws_manager.broadcast(thread_id, "CLAIMS_EXTRACTED", {
                    "documents": [
                        {
                            "doc_id": e.doc_id,
                            "filename": e.filename,
                            "doc_type": e.doc_type,
                            "execution_status": e.execution_status,
                            "claims_count": len(e.claims)
                        }
                        for e in extractions
                    ]
                })
            return {"doc_extractions": [e.model_dump() for e in extractions], "error": None}
        except Exception as e:
            error_msg = f"Claim extraction error: {str(e)}"
            if thread_id:
                await ws_manager.broadcast(thread_id, "PIPELINE_ERROR", {"message": error_msg})
            return {"doc_extractions": [], "error": error_msg}

