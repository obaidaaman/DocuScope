from typing import List, Optional, Literal, Dict, Any
from pydantic import BaseModel, Field

class EvidenceItem(BaseModel):
    doc_id: int = Field(description="Document ID from which quote is cited")
    page_number: int = Field(description="Page number where the text appears")
    exact_quote: str = Field(description="Exact verbatim quote from the text as grounding proof")

class JudgeVerdict(BaseModel):
    topic_name: str = Field(description="Concise topic title, e.g., 'Vendor Payment Terms', 'Liability Cap'")
    status: Literal["CONFLICT", "AGREEMENT"] = Field(description="CONFLICT if documents disagree, AGREEMENT if consistent")
    severity: Literal["HIGH", "MEDIUM", "LOW", "NONE"] = Field(
        description="HIGH for direct legal/financial contradictions, MEDIUM for minor variance, NONE for agreements"
    )
    explanation: str = Field(description="Clear explanation detailing how documents disagree or agree")
    evidence: List[EvidenceItem] = Field(description="List of verbatim evidence quotes with document ID and page number")

class Passage(BaseModel):
    doc_id: int
    chunk_index: int
    page_number: int
    text: str

class TopicCluster(BaseModel):
    dabba_id: int
    topic_hint: Optional[str] = None
    document_ids: List[int]
    passages: List[Passage]
    total_chunks: int

class ReconciliationRequest(BaseModel):
    doc_ids: List[int] = Field(..., min_length=2, description="At least 2 document IDs to reconcile")
    similarity_threshold: float = Field(default=0.65, ge=0.5, le=1.0, description="Minimum cosine similarity")
    max_pairs: int = Field(default=300, ge=10, le=2000, description="Maximum matching pairs to retrieve")
    thread_id: Optional[str] = Field(default=None, description="Optional thread/run ID. Generated if omitted.")

class ReconciliationResponse(BaseModel):
    thread_id: str
    total_dabbe: int
    conflicts_count: int
    agreements_count: int
    verdicts: List[JudgeVerdict]
    dabbe_preview: Optional[List[Dict[str, Any]]] = None

class ResolutionAction(BaseModel):
    review_item_id: int
    action: Literal["APPROVE_DOC", "CUSTOM_RESOLUTION", "REJECT"]
    chosen_doc_id: Optional[int] = None
    custom_text: Optional[str] = None

class ResolveReviewItemsRequest(BaseModel):
    thread_id: str
    resolutions: List[ResolutionAction]
