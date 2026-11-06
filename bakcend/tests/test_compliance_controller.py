import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException

from src.controller.reconciliation_controller import (
    resolve_review_items_controller,
    start_compliance_check_controller,
)
from src.reconciliation.schemas import (
    ComplianceCheckRequest,
    ResolveReviewItemsRequest,
)


class ComplianceControllerTests(unittest.IsolatedAsyncioTestCase):
    @patch(
        "src.controller.reconciliation_controller.check_and_broadcast_compliance",
        new_callable=AsyncMock,
    )
    async def test_starts_comparison_for_parsed_document_in_active_project(
        self, check_compliance
    ):
        db = AsyncMock()
        db.get.return_value = SimpleNamespace(
            id=7,
            project_id=3,
            status="PARSED",
        )
        db.scalar.side_effect = [1, 0]
        check_compliance.return_value = {"status": "COMPLIANT"}

        result = await start_compliance_check_controller(
            "thread-1",
            ComplianceCheckRequest(source_truth_doc_id=7, project_id=3),
            db,
        )

        self.assertEqual(result["status"], "COMPLIANT")
        check_compliance.assert_awaited_once_with("thread-1", 7)

    async def test_rejects_source_document_from_another_project(self):
        db = AsyncMock()
        db.get.return_value = SimpleNamespace(
            id=7,
            project_id=4,
            status="PARSED",
        )

        with self.assertRaises(HTTPException) as raised:
            await start_compliance_check_controller(
                "thread-1",
                ComplianceCheckRequest(source_truth_doc_id=7, project_id=3),
                db,
            )

        self.assertEqual(raised.exception.status_code, 400)
        db.scalar.assert_not_awaited()

    async def test_blocks_comparison_until_conflicts_are_resolved(self):
        db = AsyncMock()
        db.get.return_value = SimpleNamespace(
            id=7,
            project_id=3,
            status="PARSED",
        )
        db.scalar.side_effect = [1, 2]

        with self.assertRaises(HTTPException) as raised:
            await start_compliance_check_controller(
                "thread-1",
                ComplianceCheckRequest(source_truth_doc_id=7, project_id=3),
                db,
            )

        self.assertEqual(raised.exception.status_code, 409)

    @patch(
        "src.controller.reconciliation_controller.check_and_broadcast_compliance",
        new_callable=AsyncMock,
    )
    async def test_resolving_initial_conflict_does_not_start_compliance(
        self, check_compliance
    ):
        conflict = SimpleNamespace(
            id=5,
            run_thread_id="thread-1",
            item_type="CONFLICT",
            category="Payment Terms",
            summary="Payment terms differ.",
            citations_json=[],
            resolution_notes=None,
        )
        audit = SimpleNamespace(source_truth_doc_id=7)
        db = AsyncMock()
        db.get.return_value = conflict
        execution = MagicMock()
        execution.scalar_one_or_none.return_value = None
        db.execute.return_value = execution
        db.scalar.return_value = audit
        db.add = MagicMock()

        result = await resolve_review_items_controller(
            ResolveReviewItemsRequest(
                thread_id="thread-1",
                resolutions=[{
                    "review_item_id": 5,
                    "action": "REJECT",
                }],
            ),
            db,
        )

        self.assertIsNone(result["compliance_audit"])
        check_compliance.assert_not_awaited()

    @patch(
        "src.controller.reconciliation_controller.check_and_broadcast_compliance",
        new_callable=AsyncMock,
    )
    async def test_compliance_resolution_updates_audit_without_rerunning_comparison(
        self, check_compliance
    ):
        item = SimpleNamespace(
            id=5,
            run_thread_id="thread-1",
            item_type="COMPLIANCE",
            category="Payment Terms",
            summary="Payment term differs from baseline.",
            citations_json=[],
            status="PENDING",
            resolution_notes=None,
        )
        section = SimpleNamespace(committed_markdown="Net 30.")
        audit = SimpleNamespace(
            source_truth_doc_id=7,
            status="PENDING_COMPLIANCE_REVIEW",
            finalized=False,
            result_json={"checks": []},
        )
        section_result = MagicMock()
        section_result.scalar_one_or_none.return_value = section
        review_result = MagicMock()
        review_result.scalars.return_value.all.return_value = [item]
        db = AsyncMock()
        db.get.return_value = item
        db.execute.side_effect = [section_result, review_result]
        db.scalar.return_value = audit

        result = await resolve_review_items_controller(
            ResolveReviewItemsRequest(
                thread_id="thread-1",
                resolutions=[{
                    "review_item_id": 5,
                    "action": "APPROVE_AS_IS",
                }],
            ),
            db,
        )

        self.assertEqual(result["compliance_audit"]["status"], "HUMAN_APPROVED")
        self.assertEqual(item.status, "RESOLVED")
        self.assertIn("SHA256:", item.resolution_notes)
        check_compliance.assert_not_awaited()
