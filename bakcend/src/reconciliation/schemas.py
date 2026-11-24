from typing import List, Optional, Literal, Dict, Any, TypedDict
from pydantic import BaseModel, Field

class ReconciliationState(TypedDict):
    thread_id: Optional[str]
    doc_ids: List[int]
    doc_paths: Optional[List[Dict[str, Any]]]
    similarity_threshold: float
    max_pairs: int
    doc_extractions: Optional[List[Dict[str, Any]]]
    clusters: List[Dict[str, Any]]
    verdicts: List[Dict[str, Any]]
    review_items: Optional[List[Dict[str, Any]]]
    error: Optional[str]

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


class ClusterVerdictList(BaseModel):
    verdicts: List[JudgeVerdict] = Field(
        description="All distinct conflict or agreement verdicts found within this topic cluster"
    )

class Passage(BaseModel):
    doc_id: int
    filename: Optional[str] = None
    doc_type: Optional[str] = None
    execution_status: Optional[str] = None
    chunk_index: int
    page_number: int
    extracted_claim: Optional[str] = None
    text: str

class TopicCluster(BaseModel):
    dabba_id: int
    topic_hint: Optional[str] = None
    governance_context: Optional[str] = None
    document_ids: List[int]
    passages: List[Passage]
    total_chunks: int

class SectionClaim(BaseModel):
    chunk_index: int
    section_title: str
    claim: str

class DocumentExtraction(BaseModel):
    doc_id: int
    filename: str
    doc_type: str
    execution_status: str
    governance_summary: Optional[str] = None
    claims: List[SectionClaim]

class ClusterMatch(BaseModel):
    doc_id: int
    chunk_index: int

class AlignedTopic(BaseModel):
    topic_name: str
    matched_chunks: List[ClusterMatch]

class AlignedTopicList(BaseModel):
    topics: List[AlignedTopic]

# class TopicAnchor(BaseModel):
#     topic_name: str = Field(description="Concise topic title, e.g. 'Hourly Billing Rates & Caps'")
#     description: str = Field(description="Brief explanation of what is being cross-reconciled")
#     search_query: str = Field(description="Dense semantic search phrase containing key terms and figures to retrieve chunks via vector search")
#
# class DiscoveredTopics(BaseModel):
#     topics: List[TopicAnchor] = Field(description="List of 3 to 6 key comparative topics across the documents")

class ReconciliationRequest(BaseModel):
    doc_ids: List[int] = Field(..., min_length=2, description="At least 2 document IDs to reconcile")
    similarity_threshold: float = Field(default=0.45, ge=0.2, le=1.0, description="Minimum cosine similarity for topic chunk retrieval")
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
    action: Literal["APPROVE_DOC", "APPROVE_AS_IS", "CUSTOM_RESOLUTION", "REJECT"]
    chosen_doc_id: Optional[int] = None
    custom_text: Optional[str] = None

class ResolveReviewItemsRequest(BaseModel):
    thread_id: str
    resolutions: List[ResolutionAction]

class ComplianceCheckRequest(BaseModel):
    source_truth_doc_id: int = Field(..., gt=0)
    project_id: int = Field(..., gt=0)
