import hashlib
import sys
from typing import Any, Dict, List, Tuple
from sqlalchemy import func, select

from ...models.db_models import (
    ComplianceAudit,
    DeliverableSection,
    Document,
    DocumentChunk,
    ReviewItem,
)
from ...websocket.manager import ws_manager
from .schemas import _CLAIM_RULE_ID
from .citation_rules import evaluate_demo_compliance, _has_current_as_is_approval
from .source_comparator import _compare_sections_with_source


# run full compliance audit against source_truth_doc_id and update db
async def run_compliance_audit(
    thread_id: str,
    source_truth_doc_id: int,
) -> Dict[str, Any]:
    pkg = sys.modules[__package__]
    async with pkg.AsyncSessionLocal() as session:
        audit = await session.scalar(
            select(ComplianceAudit).where(
                ComplianceAudit.run_thread_id == thread_id
            )
        )
        source_document = await session.get(Document, source_truth_doc_id)
        if not source_document or source_document.status != "PARSED":
            raise ValueError(
                f"Source-of-truth document {source_truth_doc_id} is not a parsed document."
            )

        section_count = await session.scalar(
            select(func.count(DeliverableSection.id)).where(
                DeliverableSection.run_thread_id == thread_id
            )
        )
        if not section_count:
            raise ValueError("A deliverable must exist before compliance comparison.")

        section_result = await session.execute(
            select(DeliverableSection).where(
                DeliverableSection.run_thread_id == thread_id
            )
        )
        sections = section_result.scalars().all()
        compliance_items_result = await session.execute(
            select(ReviewItem).where(
                ReviewItem.run_thread_id == thread_id,
                ReviewItem.item_type == "COMPLIANCE",
            )
        )
        compliance_items = compliance_items_result.scalars().all()
        source_changed = bool(
            audit
            and audit.source_truth_doc_id != source_truth_doc_id
        )

        pending_conflict_count = await session.scalar(
            select(func.count(ReviewItem.id))
            .where(
                ReviewItem.run_thread_id == thread_id,
                ReviewItem.item_type == "CONFLICT",
                ReviewItem.status == "PENDING",
            )
        )

        cited_doc_ids = {
            citation.get("doc_id")
            for section in sections
            for citation in (section.citations_json or [])
            if isinstance(citation, dict) and isinstance(citation.get("doc_id"), int)
        }

        source_pages: Dict[Tuple[int, int], List[str]] = {}
        if cited_doc_ids:
            chunk_result = await session.execute(
                select(
                    DocumentChunk.document_id,
                    DocumentChunk.page_number,
                    DocumentChunk.raw_text,
                ).where(DocumentChunk.document_id.in_(cited_doc_ids))
            )
            for doc_id, page_number, raw_text in chunk_result.all():
                source_pages.setdefault((doc_id, page_number), []).append(raw_text)

        audit_result = evaluate_demo_compliance(
            thread_id=thread_id,
            sections=[
                {
                    "title": section.title,
                    "category": section.category,
                    "committed_markdown": section.committed_markdown,
                    "citations": section.citations_json,
                }
                for section in sections
            ],
            pending_conflicts=pending_conflict_count or 0,
            source_pages=source_pages,
        )
        audit_result["source_of_truth"] = source_document.filename
        audit_result["source_truth_doc_id"] = source_document.id

        semantic_results = []
        needs_human_review = False
        section_data = [
            {
                "title": section.title,
                "category": section.category,
                "committed_markdown": section.committed_markdown,
                "citations": section.citations_json,
            }
            for section in sections
        ]
        sections_to_compare = []
        for section in section_data:
            title = section.get("title") or section.get("category") or "Untitled section"
            body = section.get("committed_markdown") or ""

            if "**Clause Rejected / Omitted:**" in body:
                semantic_results.append({
                    "section": title,
                    "status": "NOT_APPLICABLE",
                    "explanation": "Rejected clauses are audit notes, not adopted deliverable claims.",
                    "unsupported_claims": [],
                })
                continue

            if "**Analyst Approved Compliance Resolution:**" in body:
                semantic_results.append({
                    "section": title,
                    "status": "HUMAN_APPROVED",
                    "explanation": "An analyst supplied and approved this compliance resolution.",
                    "unsupported_claims": [],
                })
                continue

            if _has_current_as_is_approval(
                section,
                compliance_items,
                source_changed,
            ):
                semantic_results.append({
                    "section": title,
                    "status": "HUMAN_APPROVED",
                    "explanation": "An analyst approved this unchanged section as-is.",
                    "unsupported_claims": [],
                    "evidence": [],
                })
                continue

            sections_to_compare.append(section)

        semantic_results.extend(await _compare_sections_with_source(
            sections_to_compare,
            source_truth_doc_id,
        ))

        semantic_findings = [
            result for result in semantic_results
            if result["status"] == "NON_COMPLIANT"
        ]
        needs_human_review = needs_human_review or any(
            result["status"] == "INSUFFICIENT_EVIDENCE"
            for result in semantic_results
        )
        semantic_check_status = (
            "FAIL" if semantic_findings
            else "NEEDS_REVIEW" if needs_human_review
            else "PASS"
        )
        audit_result["checks"].append({
            "rule_id": _CLAIM_RULE_ID,
            "requirement": (
                "Material claims in the final deliverable must be supported by, "
                "and not contradict, their cited source text."
            ),
            "status": semantic_check_status,
            "findings": semantic_findings,
            "section_results": semantic_results,
        })

        deterministic_failure = any(
            check["status"] == "FAIL" for check in audit_result["checks"]
        )
        section_by_title = {
            section.title or section.category: section for section in sections
        }
        semantic_by_title = {
            result["section"]: result for result in semantic_results
        }
        findings_by_title: Dict[str, List[str]] = {}
        for check in audit_result["checks"]:
            for finding in check["findings"]:
                title = finding.get("section")
                if title:
                    findings_by_title.setdefault(title, []).append(
                        finding.get("message") or finding.get("explanation") or check["requirement"]
                    )
        for result in semantic_results:
            if result["status"] in ("NON_COMPLIANT", "INSUFFICIENT_EVIDENCE"):
                findings_by_title.setdefault(result["section"], []).append(
                    result["explanation"]
                )
                findings_by_title[result["section"]].extend(
                    result["unsupported_claims"]
                )
                if result["evidence"]:
                    findings_by_title[result["section"]].append(
                        "Source-of-truth evidence: "
                        + ", ".join(
                            evidence["exact_quote"]
                            for evidence in result["evidence"]
                        )
                    )

        if source_changed:
            for item in compliance_items:
                if item.status == "PENDING" or (
                    item.resolution_notes
                    and "SHA256:" in item.resolution_notes
                ):
                    item.status = "RESOLVED"
                    item.resolution_notes = "Superseded by a new source-of-truth selection."

        existing_items = {
            (item.category, item.summary): item for item in compliance_items
        }
        current_findings = []
        for title, messages in findings_by_title.items():
            section = section_by_title.get(title)
            if section is None:
                continue
            semantic_result = semantic_by_title.get(title)

            summary = "\n".join(dict.fromkeys(messages))
            category = section.category or section.title
            section_hash = hashlib.sha256(
                section.committed_markdown.encode("utf-8")
            ).hexdigest()
            item = existing_items.get((category, summary))
            if item and item.status == "RESOLVED":
                item = None
            if item is None:
                item = next((
                    existing for existing in compliance_items
                    if existing.category == category
                    and existing.status == "RESOLVED"
                    and existing.resolution_notes
                    and f"SHA256:{section_hash}" in existing.resolution_notes
                ), None)
            if item is not None and item.status == "RESOLVED":
                continue
            if item is None:
                item = ReviewItem(
                    run_thread_id=thread_id,
                    item_type="COMPLIANCE",
                    category=category,
                    severity="HIGH" if semantic_result and semantic_result["status"] == "NON_COMPLIANT" else "MEDIUM",
                    summary=summary,
                    citations_json=[
                        *(semantic_result.get("evidence", []) if semantic_result else []),
                        *(section.citations_json or []),
                    ],
                    status="PENDING",
                )
                session.add(item)
                compliance_items.append(item)
            elif item.status == "PENDING":
                item.citations_json = [
                    *(semantic_result.get("evidence", []) if semantic_result else []),
                    *(section.citations_json or []),
                ]
            current_findings.append(item)

        current_finding_keys = {
            (item.category, item.summary) for item in current_findings
        }
        for item in compliance_items:
            key = (item.category, item.summary)
            if item.status == "PENDING" and key not in current_finding_keys:
                item.status = "RESOLVED"
                item.resolution_notes = "Finding no longer applies after deliverable update."

        await session.flush()
        pending_compliance_count = sum(
            item.status == "PENDING" for item in compliance_items
        )
        has_human_approved_findings = any(
            item.status == "RESOLVED"
            and item.resolution_notes
            and any(
                section.category == item.category
                and f"SHA256:{hashlib.sha256(section.committed_markdown.encode('utf-8')).hexdigest()}"
                in item.resolution_notes
                for section in sections
            )
            for item in compliance_items
        )
        if audit_result["status"] != "NOT_READY":
            if pending_conflict_count:
                audit_result["status"] = "PENDING_REVIEW"
            elif pending_compliance_count:
                audit_result["status"] = "PENDING_COMPLIANCE_REVIEW"
            elif has_human_approved_findings:
                audit_result["status"] = "HUMAN_APPROVED"
            elif deterministic_failure or semantic_findings:
                audit_result["status"] = "NON_COMPLIANT"
            elif needs_human_review:
                audit_result["status"] = "NEEDS_REVIEW"

        audit_result["pending_compliance_reviews"] = pending_compliance_count
        audit_result["finalized"] = False
        audit_result["compliance_review_items"] = [
            {
                "id": item.id,
                "category": item.category,
                "summary": item.summary,
                "status": item.status,
                "resolution_notes": item.resolution_notes,
            }
            for item in compliance_items
        ]
        if audit:
            audit.status = audit_result["status"]
            audit.result_json = audit_result
            audit.source_truth_doc_id = source_truth_doc_id
            audit.finalized = False
        else:
            session.add(ComplianceAudit(
                run_thread_id=thread_id,
                status=audit_result["status"],
                result_json=audit_result,
                source_truth_doc_id=source_truth_doc_id,
                finalized=False,
            ))

        await session.commit()
        return audit_result


async def check_and_broadcast_compliance(
    thread_id: str,
    source_truth_doc_id: int,
) -> Dict[str, Any]:
    audit_result = await run_compliance_audit(thread_id, source_truth_doc_id)
    await ws_manager.broadcast(
        thread_id,
        "COMPLIANCE_CHECK_COMPLETE",
        audit_result,
    )
    return audit_result

