import hashlib
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from src.reconciliation.compliance import (
    BatchComplianceVerdict,
    _compare_sections_with_source,
    _has_current_as_is_approval,
    evaluate_demo_compliance,
)
from src.reconciliation.schemas import ResolutionAction


class DemoComplianceTests(unittest.TestCase):
    def test_verifiable_citation_passes(self):
        result = evaluate_demo_compliance(
            thread_id="run-1",
            sections=[{
                "title": "Payment Terms",
                "committed_markdown": "Payment is due in 30 days.",
                "citations": [{
                    "doc_id": 7,
                    "page_number": 2,
                    "exact_quote": "Payment is due in 30 days.",
                }],
            }],
            pending_conflicts=0,
            source_pages={(7, 2): ["Payment is due in 30 days."]},
        )

        self.assertEqual(result["status"], "COMPLIANT")

    def test_source_derived_section_without_citation_fails(self):
        result = evaluate_demo_compliance(
            thread_id="run-1",
            sections=[{
                "title": "Payment Terms",
                "committed_markdown": "Payment is due in 30 days.",
                "citations": [],
            }],
            pending_conflicts=0,
            source_pages={},
        )

        self.assertEqual(result["status"], "NON_COMPLIANT")

    def test_quote_must_exist_on_cited_page(self):
        result = evaluate_demo_compliance(
            thread_id="run-1",
            sections=[{
                "title": "Payment Terms",
                "committed_markdown": "Payment is due in 30 days.",
                "citations": [{
                    "doc_id": 7,
                    "page_number": 2,
                    "exact_quote": "Payment is due in 30 days.",
                }],
            }],
            pending_conflicts=0,
            source_pages={(7, 3): ["Payment is due in 30 days."]},
        )

        self.assertEqual(result["status"], "NON_COMPLIANT")
        evidence_check = result["checks"][1]
        self.assertEqual(evidence_check["status"], "FAIL")

    def test_pending_conflicts_block_final_compliance_status(self):
        result = evaluate_demo_compliance(
            thread_id="run-1",
            sections=[],
            pending_conflicts=2,
            source_pages={},
        )

        self.assertEqual(result["status"], "PENDING_REVIEW")
        self.assertEqual(result["pending_conflicts"], 2)

    def test_empty_deliverable_is_not_ready(self):
        result = evaluate_demo_compliance(
            thread_id="run-1",
            sections=[],
            pending_conflicts=0,
            source_pages={},
        )

        self.assertEqual(result["status"], "NOT_READY")

    def test_analyst_authored_section_requires_human_review(self):
        result = evaluate_demo_compliance(
            thread_id="run-1",
            sections=[{
                "title": "Payment Terms",
                "committed_markdown": "**Analyst Negotiated Resolution:**\n\nNet 30.",
                "citations": [],
            }],
            pending_conflicts=0,
            source_pages={},
        )

        self.assertEqual(result["status"], "NEEDS_REVIEW")

    def test_compliance_human_approval_is_an_available_review_action(self):
        action = ResolutionAction(
            review_item_id=4,
            action="APPROVE_AS_IS",
        )

        self.assertEqual(action.action, "APPROVE_AS_IS")

    def test_as_is_approval_is_reused_only_for_same_content_and_source(self):
        section = {
            "category": "Payment Terms",
            "committed_markdown": "Net 30.",
        }
        content_hash = hashlib.sha256(b"Net 30.").hexdigest()
        item = SimpleNamespace(
            category="Payment Terms",
            status="RESOLVED",
            resolution_notes=f"Action: APPROVE_AS_IS | SHA256:{content_hash}",
        )

        self.assertTrue(_has_current_as_is_approval(section, [item], False))
        self.assertFalse(_has_current_as_is_approval(section, [item], True))
        self.assertFalse(_has_current_as_is_approval(
            {**section, "committed_markdown": "Net 45."},
            [item],
            False,
        ))


class SourceComparisonTests(unittest.IsolatedAsyncioTestCase):
    @patch("src.reconciliation.compliance.AsyncSessionLocal")
    @patch("src.reconciliation.compliance.openai_client.embeddings.create")
    @patch("src.reconciliation.compliance.compliance_judge")
    async def test_batches_embeddings_and_section_judgments(
        self, judge, create_embedding, session_factory
    ):
        source_text = "Payment is due in 30 days. Other source context."
        create_embedding.return_value = SimpleNamespace(
            data=[
                SimpleNamespace(embedding=[0.1, 0.2]),
                SimpleNamespace(embedding=[0.3, 0.4]),
            ]
        )
        judge.ainvoke = AsyncMock(return_value=BatchComplianceVerdict(
            results=[
                {
                    "section_index": 0,
                    "status": "COMPLIANT",
                    "explanation": "The selected source supports the payment term.",
                    "unsupported_claims": [],
                    "evidence": [{
                        "doc_id": 7,
                        "page_number": 2,
                        "exact_quote": "Payment is due in 30 days.",
                    }],
                },
                {
                    "section_index": 1,
                    "status": "NON_COMPLIANT",
                    "explanation": "The deliverable amount differs from the baseline.",
                    "unsupported_claims": ["The amount is misstated."],
                    "evidence": [{
                        "doc_id": 7,
                        "page_number": 3,
                        "exact_quote": "The total fee is $148,000.",
                    }],
                },
            ]
        ))
        chunks_result = MagicMock()
        chunks_result.mappings.return_value.all.return_value = [
            {
                "section_index": 0,
                "chunk_index": 4,
                "page_number": 2,
                "raw_text": source_text,
            },
            {
                "section_index": 1,
                "chunk_index": 5,
                "page_number": 3,
                "raw_text": "The total fee is $148,000.",
            },
        ]
        session = AsyncMock()
        session.execute.return_value = chunks_result
        session_factory.return_value.__aenter__ = AsyncMock(return_value=session)
        session_factory.return_value.__aexit__ = AsyncMock(return_value=None)

        result = await _compare_sections_with_source(
            [
                {
                    "title": "Payment Terms",
                    "committed_markdown": "Payment is due in 30 days.",
                },
                {
                    "title": "Fee",
                    "committed_markdown": "The fee is $162,000.",
                },
            ],
            7,
        )

        self.assertEqual([item["status"] for item in result], [
            "COMPLIANT",
            "NON_COMPLIANT",
        ])
        self.assertEqual(result[0]["evidence"][0]["doc_id"], 7)
        create_embedding.assert_awaited_once()
        judge.ainvoke.assert_awaited_once()
        self.assertIn(source_text, judge.ainvoke.await_args.args[0])
        self.assertIn("The fee is $162,000.", judge.ainvoke.await_args.args[0])
        self.assertIn("websearch_to_tsquery", str(session.execute.await_args.args[0]))
        self.assertIn("query_text_0", session.execute.await_args.args[1])
        self.assertIn("embedding_1", session.execute.await_args.args[1])

    @patch("src.reconciliation.compliance.AsyncSessionLocal")
    @patch("src.reconciliation.compliance.openai_client.embeddings.create")
    @patch("src.reconciliation.compliance.compliance_judge")
    async def test_no_candidates_returns_insufficient_evidence_without_judging(
        self, judge, create_embedding, session_factory
    ):
        create_embedding.return_value = SimpleNamespace(
            data=[SimpleNamespace(embedding=[0.1, 0.2])]
        )
        chunks_result = MagicMock()
        chunks_result.mappings.return_value.all.return_value = []
        session = AsyncMock()
        session.execute.return_value = chunks_result
        session_factory.return_value.__aenter__ = AsyncMock(return_value=session)
        session_factory.return_value.__aexit__ = AsyncMock(return_value=None)

        result = await _compare_sections_with_source(
            [{
                "title": "Payment Terms",
                "committed_markdown": "Net 30.",
            }],
            7,
        )

        self.assertEqual(result[0]["status"], "INSUFFICIENT_EVIDENCE")
        judge.ainvoke.assert_not_called()


if __name__ == "__main__":
    unittest.main()
