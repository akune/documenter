"""
Integration test fixtures.
Assumes docker-compose.test.yml services are running and test-init has completed.
Run via: make test-integration
"""
import sys
import time
import uuid
from pathlib import Path
from typing import Generator

import pytest
import requests
from requests.auth import HTTPBasicAuth

# Make src/ and the integration test directory importable
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from config import Config
from paperless_uploader import PaperlessUploader
from nextcloud_uploader import NextcloudUploader

from helpers import (
    PAPERLESS_URL, NEXTCLOUD_URL,
    ADMIN_USER, ADMIN_PASSWORD,
    USER1, USER1_PASSWORD,
    USER2, USER2_PASSWORD,
    GROUP_NAME, NEXTCLOUD_TARGET_DIR,
    minimal_pdf, paperless_token, paperless_session, wait_for_document, wait_for_task,
)


# ── Service readiness ─────────────────────────────────────────────────────────

@pytest.fixture(scope="session", autouse=True)
def wait_for_services() -> None:
    """Block until both services are reachable and test users exist (init done)."""
    _wait_paperless()
    _wait_nextcloud()
    _wait_for_init()


def _wait_paperless(timeout: int = 120) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = requests.get(
                f"{PAPERLESS_URL}/api/tags/",
                headers={"Accept": "application/json; version=6",
                         "Authorization": "Token placeholder"},
                timeout=5,
            )
            if r.status_code in (200, 401, 403):
                return
        except requests.RequestException:
            pass
        time.sleep(2)
    pytest.fail(f"Paperless-ngx at {PAPERLESS_URL} did not become reachable within {timeout}s")


def _wait_nextcloud(timeout: int = 300) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = requests.get(f"{NEXTCLOUD_URL}/status.php", timeout=5)
            if r.status_code == 200 and r.json().get("installed") is True:
                return
        except (requests.RequestException, ValueError):
            pass
        time.sleep(2)
    pytest.fail(f"Nextcloud at {NEXTCLOUD_URL} did not finish installing within {timeout}s")


def _wait_for_init(timeout: int = 120) -> None:
    """Wait until test users can authenticate in both services — confirms init completed."""
    # Verify Paperless user1 can obtain a token
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = requests.post(
                f"{PAPERLESS_URL}/api/token/",
                json={"username": USER1, "password": USER1_PASSWORD},
                timeout=10,
            )
            if r.status_code == 200:
                break
        except requests.RequestException:
            pass
        time.sleep(3)
    else:
        pytest.fail("Paperless test users were not created within timeout — did test-init complete?")

    # Verify Nextcloud user1 can authenticate via WebDAV (also triggers home dir creation)
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = requests.request(
                "PROPFIND",
                f"{NEXTCLOUD_URL}/remote.php/dav/files/{USER1}/",
                auth=(USER1, USER1_PASSWORD),
                headers={"Depth": "0"},
                timeout=10,
            )
            if r.status_code in (200, 207):
                return
        except requests.RequestException:
            pass
        time.sleep(3)
    pytest.fail("Nextcloud test users were not ready within timeout — did test-init complete?")


# ── Paperless fixtures ────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def admin_token() -> str:
    return paperless_token(ADMIN_USER, ADMIN_PASSWORD)


@pytest.fixture(scope="session")
def admin_session(admin_token) -> requests.Session:
    return paperless_session(admin_token)


@pytest.fixture(scope="session")
def user1_session() -> requests.Session:
    return paperless_session(paperless_token(USER1, USER1_PASSWORD))


@pytest.fixture(scope="session")
def user2_session() -> requests.Session:
    return paperless_session(paperless_token(USER2, USER2_PASSWORD))


def _make_paperless_config(token: str, group: str = "") -> Config:
    return Config(
        paperless_url=PAPERLESS_URL,
        paperless_api_token=token,
        paperless_group=group,
        paperless_default_tags=["TestInbox"],
        paperless_enabled=True,
        nextcloud_enabled=False,
    )


@pytest.fixture(scope="session")
def paperless_admin_client(admin_token) -> PaperlessUploader:
    """PaperlessUploader authenticated as admin, with TestFamily group."""
    return PaperlessUploader(_make_paperless_config(admin_token, group=GROUP_NAME))


@pytest.fixture(scope="session")
def paperless_admin_client_no_group(admin_token) -> PaperlessUploader:
    """PaperlessUploader authenticated as admin, with no group (for negative tests)."""
    return PaperlessUploader(_make_paperless_config(admin_token, group=""))


@pytest.fixture
def unique_pdf(tmp_path) -> Path:
    """Write a uniquely-content PDF to avoid Paperless duplicate detection."""
    uid = uuid.uuid4().hex
    pdf_bytes = minimal_pdf() + f"\n% unique-{uid}\n".encode()
    pdf_path = tmp_path / f"unique_{uid[:8]}.pdf"
    pdf_path.write_bytes(pdf_bytes)
    return pdf_path


@pytest.fixture(scope="session")
def sample_pdf(tmp_path_factory) -> Path:
    """Write a minimal valid PDF to a temp file and return its path."""
    pdf_path = tmp_path_factory.mktemp("pdfs") / f"test_{uuid.uuid4().hex[:8]}.pdf"
    pdf_path.write_bytes(minimal_pdf())
    return pdf_path


@pytest.fixture(scope="session")
def uploaded_document(paperless_admin_client, admin_session, sample_pdf) -> Generator:
    """Upload a document once per session, yield its metadata dict, delete on teardown."""
    title = f"IntegTest-{uuid.uuid4().hex[:8]}"
    tag_context = {"year_month": "2026-03", "directory_path": "2026-03"}

    ok, task_id = paperless_admin_client.upload(
        str(sample_pdf), title, created_date=None, tag_context=tag_context
    )
    assert ok, f"Upload failed: {task_id}"

    doc_id = wait_for_task(admin_session, task_id)
    r = admin_session.get(f"{PAPERLESS_URL}/api/documents/{doc_id}/", timeout=10)
    r.raise_for_status()
    doc = r.json()
    yield doc

    admin_session.delete(f"{PAPERLESS_URL}/api/documents/{doc['id']}/", timeout=10)


# ── Nextcloud fixtures ────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def nextcloud_admin_uploader() -> NextcloudUploader:
    config = Config(
        nextcloud_url=NEXTCLOUD_URL,
        nextcloud_user=ADMIN_USER,
        nextcloud_password=ADMIN_PASSWORD,
        nextcloud_target_dir=NEXTCLOUD_TARGET_DIR,
        nextcloud_enabled=True,
        paperless_enabled=False,
    )
    return NextcloudUploader(config)


@pytest.fixture(scope="session")
def nextcloud_user1_session() -> requests.Session:
    s = requests.Session()
    s.auth = HTTPBasicAuth(USER1, USER1_PASSWORD)
    return s
