from typing import List, Literal
from pydantic import BaseModel, Field

from ..schemas import EvidenceItem

DEMO_COMPLIANCE_SOURCE = "Demo grounding-compliance checklist"
SOURCE_OF_TRUTH = "Ingested source documents and cited page text"

_CITATION_RULE_ID = "source_citation_required"
_EVIDENCE_RULE_ID = "citation_matches_source"
_CLAIM_RULE_ID = "deliverable_matches_source"


class SectionComplianceAssessment(BaseModel):
    section_index: int = Field(description="Index of the deliverable section being assessed")
    status: Literal["COMPLIANT", "NON_COMPLIANT", "INSUFFICIENT_EVIDENCE"] = Field(
        description="Whether the deliverable section matches the authoritative source"
    )
    explanation: str = Field(description="Concise comparison of the deliverable and source")
    unsupported_claims: List[str] = Field(
        description="Material claims unsupported by or contradicted by the selected source"
    )
    evidence: List[EvidenceItem] = Field(
        default_factory=list,
        description="Verbatim evidence from the source-of-truth document supporting this assessment"
    )


class BatchComplianceVerdict(BaseModel):
    results: List[SectionComplianceAssessment]

