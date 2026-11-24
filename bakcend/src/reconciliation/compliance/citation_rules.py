import hashlib
from typing import Any, Dict, List, Mapping, Sequence, Tuple

from ...models.db_models import ReviewItem
from .schemas import (
    DEMO_COMPLIANCE_SOURCE,
    SOURCE_OF_TRUTH,
    _CITATION_RULE_ID,
    _EVIDENCE_RULE_ID,
)


# check if cited quotes actually exist on the cited page text
def _citation_source_findings(
    section: Mapping[str, Any],
    source_pages: Mapping[Tuple[int, int], Sequence[str]],
) -> List[Dict[str, Any]]:
    title = section.get("title") or section.get("category") or "Untitled section"
    citations = section.get("citations")
    citations = citations if isinstance(citations, list) else []
    findings = []

    for citation in citations:
        if not isinstance(citation, dict):
            findings.append({
                "section": title,
                "message": "Citation must include a document ID, page number, and exact quote.",
            })
            continue

        doc_id = citation.get("doc_id")
        page_number = citation.get("page_number")
        exact_quote = citation.get("exact_quote")
        if (
            not isinstance(doc_id, int)
            or not isinstance(page_number, int)
            or not isinstance(exact_quote, str)
            or not exact_quote.strip()
        ):
            findings.append({
                "section": title,
                "message": "Citation must include a document ID, page number, and exact quote.",
            })
            continue

        page_texts = source_pages.get((doc_id, page_number), ())
        if not any(exact_quote in text for text in page_texts):
            findings.append({
                "section": title,
                "doc_id": doc_id,
                "page_number": page_number,
                "message": "The cited quote was not found verbatim on the cited source page.",
            })

    return findings


# run deterministic citation presence + quote match rules
def evaluate_demo_compliance(
    thread_id: str,
    sections: Sequence[Mapping[str, Any]],
    pending_conflicts: int,
    source_pages: Mapping[Tuple[int, int], Sequence[str]],
) -> Dict[str, Any]:
    citation_findings: List[Dict[str, Any]] = []
    evidence_findings: List[Dict[str, Any]] = []
    human_authored_sections = 0

    for section in sections:
        title = section.get("title") or section.get("category") or "Untitled section"
        body = section.get("committed_markdown") or ""
        citations = section.get("citations")
        citations = citations if isinstance(citations, list) else []
        is_explicit_human_note = (
            "**Analyst Negotiated Resolution:**" in body
            or "**Analyst Approved Compliance Resolution:**" in body
            or "**Clause Rejected / Omitted:**" in body
        )

        if "**Analyst Negotiated Resolution:**" in body and not citations:
            human_authored_sections += 1

        if not citations and not is_explicit_human_note:
            citation_findings.append({
                "section": title,
                "message": "Source-derived deliverable sections must include at least one citation.",
            })

        evidence_findings.extend(_citation_source_findings(section, source_pages))

    checks = [
        {
            "rule_id": _CITATION_RULE_ID,
            "requirement": (
                "Every source-derived deliverable section must cite a source. "
                "Analyst-negotiated and explicitly rejected notes are exempt."
            ),
            "status": "FAIL" if citation_findings else "PASS",
            "findings": citation_findings,
        },
        {
            "rule_id": _EVIDENCE_RULE_ID,
            "requirement": (
                "Every citation must match an exact quote in the cited document and page."
            ),
            "status": "FAIL" if evidence_findings else "PASS",
            "findings": evidence_findings,
        },
    ]

    if pending_conflicts:
        status = "PENDING_REVIEW"
    elif not sections:
        status = "NOT_READY"
    elif any(check["status"] == "FAIL" for check in checks):
        status = "NON_COMPLIANT"
    elif human_authored_sections:
        status = "NEEDS_REVIEW"
    else:
        status = "COMPLIANT"

    return {
        "thread_id": thread_id,
        "source": DEMO_COMPLIANCE_SOURCE,
        "source_of_truth": SOURCE_OF_TRUTH,
        "status": status,
        "pending_conflicts": pending_conflicts,
        "checked_sections": len(sections),
        "human_authored_sections": human_authored_sections,
        "checks": checks,
    }


def _has_current_as_is_approval(
    section: Mapping[str, Any],
    compliance_items: Sequence[ReviewItem],
    source_changed: bool,
) -> bool:
    if source_changed:
        return False
    title = section.get("title") or section.get("category") or "Untitled section"
    category = section.get("category") or title
    section_hash = hashlib.sha256(
        (section.get("committed_markdown") or "").encode("utf-8")
    ).hexdigest()
    return any(
        item.category == category
        and item.status == "RESOLVED"
        and item.resolution_notes
        and item.resolution_notes.startswith("Action: APPROVE_AS_IS")
        and f"SHA256:{section_hash}" in item.resolution_notes
        for item in compliance_items
    )

