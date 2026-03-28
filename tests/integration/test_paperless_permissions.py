"""
Tests: Paperless-ngx group permissions.

Key test: verifies that tags created by the uploader are visible to all group
members — this directly tests the fix for tags missing set_permissions on creation.
"""
import uuid

import pytest
import requests

from helpers import PAPERLESS_URL, GROUP_NAME, wait_for_document, wait_for_task


class TestPaperlessPermissions:

    def test_tag_visible_to_user1(self, uploaded_document, user1_session):
        """user1 can see a tag created by admin when the group is set."""
        tag_ids = uploaded_document.get("tags", [])
        assert tag_ids, "No tags on document to check"

        # Look up each tag ID as user1
        visible = []
        for tid in tag_ids:
            r = user1_session.get(f"{PAPERLESS_URL}/api/tags/{tid}/", timeout=10)
            if r.status_code == 200:
                visible.append(r.json()["name"])

        assert visible, (
            f"user1 cannot see any of the document tags (ids={tag_ids}). "
            "This indicates the tag set_permissions fix is not working."
        )

    def test_tag_visible_to_user2(self, uploaded_document, user2_session):
        """user2 can see a tag created by admin when the group is set."""
        tag_ids = uploaded_document.get("tags", [])
        assert tag_ids, "No tags on document to check"

        visible = []
        for tid in tag_ids:
            r = user2_session.get(f"{PAPERLESS_URL}/api/tags/{tid}/", timeout=10)
            if r.status_code == 200:
                visible.append(r.json()["name"])

        assert visible, (
            f"user2 cannot see any of the document tags (ids={tag_ids}). "
            "This indicates the tag set_permissions fix is not working."
        )

    def test_document_visible_to_user1(self, uploaded_document, user1_session):
        """user1 can see a document uploaded by admin when group permissions are set."""
        doc_id = uploaded_document["id"]
        r = user1_session.get(f"{PAPERLESS_URL}/api/documents/{doc_id}/", timeout=10)
        assert r.status_code == 200, (
            f"user1 cannot see document {doc_id} (status={r.status_code}). "
            "Group document permissions may not be working."
        )

    def test_document_visible_to_user2(self, uploaded_document, user2_session):
        """user2 can see a document uploaded by admin when group permissions are set."""
        doc_id = uploaded_document["id"]
        r = user2_session.get(f"{PAPERLESS_URL}/api/documents/{doc_id}/", timeout=10)
        assert r.status_code == 200, (
            f"user2 cannot see document {doc_id} (status={r.status_code})."
        )

    def test_document_not_visible_without_group(
        self, paperless_admin_client_no_group, admin_session, user1_session, unique_pdf
    ):
        """
        Negative test: a document uploaded WITHOUT group permissions is not visible
        to user1, confirming that permissions are not granted by default.
        """
        title = f"NoGroup-{uuid.uuid4().hex[:8]}"
        ok, task_id = paperless_admin_client_no_group.upload(
            str(unique_pdf),
            title,
            tag_context={"year_month": "2026-03", "directory_path": "2026-03"},
        )
        assert ok, f"Upload failed: {task_id}"

        doc_id = wait_for_task(admin_session, task_id)
        r = admin_session.get(f"{PAPERLESS_URL}/api/documents/{doc_id}/", timeout=10)
        r.raise_for_status()
        doc = r.json()
        doc_id = doc["id"]
        try:
            r = user1_session.get(f"{PAPERLESS_URL}/api/documents/{doc_id}/", timeout=10)
            assert r.status_code in (403, 404), (
                f"Expected user1 to be denied access to ungrouped document, "
                f"but got status {r.status_code}."
            )
        finally:
            admin_session.delete(f"{PAPERLESS_URL}/api/documents/{doc_id}/", timeout=10)
