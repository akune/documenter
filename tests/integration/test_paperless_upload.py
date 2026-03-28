"""
Tests: Paperless-ngx upload correctness.
Verifies that documents are uploaded with the right title, date, and tags.
"""
import uuid
from pathlib import Path
from datetime import datetime

import pytest

from helpers import PAPERLESS_URL, wait_for_document, wait_for_task


class TestPaperlessUpload:

    def test_upload_succeeds(self, uploaded_document):
        """Uploading a sample PDF returns success and the document appears."""
        assert uploaded_document is not None
        assert "id" in uploaded_document

    def test_upload_sets_title(self, uploaded_document):
        """Document title in Paperless-ngx matches the title passed at upload."""
        assert "IntegTest-" in uploaded_document["title"]

    def test_upload_creates_tags(self, uploaded_document, admin_session):
        """Tags passed at upload are present on the document."""
        tag_ids = uploaded_document.get("tags", [])
        assert len(tag_ids) > 0, "Document has no tags"

        # Resolve tag IDs to names
        r = admin_session.get(f"{PAPERLESS_URL}/api/tags/", timeout=10)
        assert r.status_code == 200
        all_tags = {t["id"]: t["name"] for t in r.json().get("results", [])}
        tag_names = [all_tags.get(tid, "") for tid in tag_ids]
        assert any("TestInbox" in name for name in tag_names), (
            f"Expected 'TestInbox' tag; found: {tag_names}"
        )

    def test_upload_with_created_date(self, paperless_admin_client, admin_session, unique_pdf):
        """Document created date is set from the value passed at upload."""
        title = f"DateTest-{uuid.uuid4().hex[:8]}"
        created = datetime(2025, 6, 15, 10, 30, 0)

        ok, task_id = paperless_admin_client.upload(
            str(unique_pdf),
            title,
            created_date=created,
            tag_context={"year_month": "2025-06", "directory_path": "2025-06"},
        )
        assert ok, f"Upload failed: {task_id}"

        doc_id = wait_for_task(admin_session, task_id)
        r = admin_session.get(f"{PAPERLESS_URL}/api/documents/{doc_id}/", timeout=10)
        r.raise_for_status()
        doc = r.json()
        try:
            assert "2025-06-15" in (doc.get("created") or doc.get("created_date") or "")
        finally:
            admin_session.delete(f"{PAPERLESS_URL}/api/documents/{doc['id']}/", timeout=10)
