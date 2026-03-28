"""
Tests: Nextcloud upload via WebDAV.
Verifies file upload, admin accessibility, and group share visibility.
"""
import uuid

import pytest
import requests
from requests.auth import HTTPBasicAuth

from helpers import NEXTCLOUD_URL, ADMIN_USER, ADMIN_PASSWORD, USER1, USER1_PASSWORD, NEXTCLOUD_TARGET_DIR


def _webdav_url(username: str, path: str) -> str:
    path = path if path.startswith("/") else f"/{path}"
    return f"{NEXTCLOUD_URL}/remote.php/dav/files/{username}{path}"


def _propfind(session: requests.Session, url: str) -> int:
    r = session.request("PROPFIND", url, headers={"Depth": "1"}, timeout=10)
    return r.status_code


class TestNextcloudUpload:

    def test_upload_succeeds(self, nextcloud_admin_uploader, sample_pdf):
        """Uploading a PDF via WebDAV returns success."""
        filename = f"test_{uuid.uuid4().hex[:8]}.pdf"
        ok, err = nextcloud_admin_uploader.upload(str(sample_pdf), filename, subfolder="2026-03")
        assert ok, f"Nextcloud upload failed: {err}"

    def test_file_accessible_to_admin(self, nextcloud_admin_uploader, sample_pdf):
        """Uploaded file is accessible to admin via PROPFIND."""
        filename = f"admin_{uuid.uuid4().hex[:8]}.pdf"
        ok, err = nextcloud_admin_uploader.upload(str(sample_pdf), filename, subfolder="2026-03")
        assert ok, f"Upload failed: {err}"

        session = requests.Session()
        session.auth = HTTPBasicAuth(ADMIN_USER, ADMIN_PASSWORD)

        url = _webdav_url(ADMIN_USER, f"{NEXTCLOUD_TARGET_DIR}/2026-03/{filename}")
        status = _propfind(session, url)
        assert status == 207, f"PROPFIND returned {status}; file not found for admin"

    def test_subdirectory_created_automatically(self, nextcloud_admin_uploader, sample_pdf):
        """Uploading to a new subfolder creates the directory automatically."""
        subfolder = f"auto-{uuid.uuid4().hex[:8]}"
        filename = "auto_test.pdf"
        ok, err = nextcloud_admin_uploader.upload(str(sample_pdf), filename, subfolder=subfolder)
        assert ok, f"Upload to new subfolder failed: {err}"

        session = requests.Session()
        session.auth = HTTPBasicAuth(ADMIN_USER, ADMIN_PASSWORD)

        dir_url = _webdav_url(ADMIN_USER, f"{NEXTCLOUD_TARGET_DIR}/{subfolder}/")
        status = _propfind(session, dir_url)
        assert status == 207, f"Subfolder was not created (PROPFIND returned {status})"

    def test_file_accessible_via_group_share(self, nextcloud_admin_uploader, nextcloud_user1_session, sample_pdf):
        """
        A file uploaded by admin to /Documents/Scans is accessible to user1
        via the group share.  In Nextcloud, the shared folder appears in user1's
        root as 'Scans' (the folder name).
        """
        filename = f"shared_{uuid.uuid4().hex[:8]}.pdf"
        ok, err = nextcloud_admin_uploader.upload(str(sample_pdf), filename)
        assert ok, f"Upload failed: {err}"

        # Nextcloud auto-mounts the shared /Documents/Scans folder at /Scans for group members
        shared_url = _webdav_url(USER1, f"/Scans/{filename}")
        status = _propfind(nextcloud_user1_session, shared_url)
        assert status == 207, (
            f"user1 cannot see '{filename}' via group share (PROPFIND returned {status}). "
            f"Checked: {shared_url}"
        )
