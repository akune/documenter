"""
Integration test fixtures.
Assumes docker-compose.test.yml services are running and test-init has completed.
Run via: make test-integration
"""
import sys
import time
import uuid
import tempfile
from pathlib import Path
from typing import Generator

import pytest
import requests
from requests.auth import HTTPBasicAuth

# Make src/ importable without installation
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from config import Config
from paperless_uploader import PaperlessUploader
from nextcloud_uploader import NextcloudUploader

# ── Service coordinates ────────────────────────────────────────────────────────

PAPERLESS_URL = "http://localhost:8010"
NEXTCLOUD_URL = "http://localhost:8011"

ADMIN_USER = "admin"
ADMIN_PASSWORD = "admin"
USER1 = "user1"
USER1_PASSWORD = "user1password"
USER2 = "user2"
USER2_PASSWORD = "user2password"
GROUP_NAME = "TestFamily"
NEXTCLOUD_TARGET_DIR = "/Documents/Scans"

# ── Helpers ───────────────────────────────────────────────────────────────────


def _paperless_token(username: str, password: str) -> str:
    """Fetch a Paperless-ngx API token."""
    r = requests.post(
        f"{PAPERLESS_URL}/api/token/",
        json={"username": username, "password": password},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["token"]


def _paperless_session(token: str) -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "Authorization": f"Token {token}",
        "Accept": "application/json; version=6",
    })
    return s


def _minimal_pdf() -> bytes:
    """Generate a minimal valid single-page blank PDF from first principles."""
    header = b"%PDF-1.4\n"
    obj1   = b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
    obj2   = b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
    obj3   = b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>\nendobj\n"

    off = [len(header)]
    off.append(off[0] + len(obj1))
    off.append(off[1] + len(obj2))
    xref_pos = off[2] + len(obj3)

    xref = (
        b"xref\n0 4\n"
        b"0000000000 65535 f \n"
        + f"{off[0]:010d} 00000 n \n".encode()
        + f"{off[1]:010d} 00000 n \n".encode()
        + f"{off[2]:010d} 00000 n \n".encode()
    )
    trailer = (
        b"trailer\n<< /Size 4 /Root 1 0 R >>\nstartxref\n"
        + str(xref_pos).encode()
        + b"\n%%EOF\n"
    )
    return header + obj1 + obj2 + obj3 + xref + trailer


def _wait_for_document(session: requests.Session, title: str, timeout: int = 120) -> dict:
    """Poll until a document with the given title appears in Paperless-ngx."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = session.get(f"{PAPERLESS_URL}/api/documents/", params={"title__iexact": title}, timeout=10)
        if r.status_code == 200:
            results = r.json().get("results", [])
            if results:
                return results[0]
        time.sleep(3)
    raise TimeoutError(f"Document '{title}' did not appear in Paperless-ngx within {timeout}s")


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
            r = requests.get(f"{PAPERLESS_URL}/api/tags/", timeout=5,
                             headers={"Accept": "application/json; version=6",
                                      "Authorization": "Token placeholder"})
            if r.status_code in (200, 401, 403):
                return
        except requests.RequestException:
            pass
        time.sleep(2)
    pytest.fail(f"Paperless-ngx at {PAPERLESS_URL} did not become reachable within {timeout}s")


def _wait_nextcloud(timeout: int = 120) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = requests.get(f"{NEXTCLOUD_URL}/status.php", timeout=5)
            if r.status_code == 200:
                return
        except requests.RequestException:
            pass
        time.sleep(2)
    pytest.fail(f"Nextcloud at {NEXTCLOUD_URL} did not become reachable within {timeout}s")


def _wait_for_init(timeout: int = 120) -> None:
    """Wait until test users can authenticate — confirms init completed."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = requests.post(
                f"{PAPERLESS_URL}/api/token/",
                json={"username": USER1, "password": USER1_PASSWORD},
                timeout=10,
            )
            if r.status_code == 200:
                return
        except requests.RequestException:
            pass
        time.sleep(3)
    pytest.fail("Test users were not created within timeout — did test-init complete?")


# ── Paperless fixtures ────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def admin_token() -> str:
    return _paperless_token(ADMIN_USER, ADMIN_PASSWORD)


@pytest.fixture(scope="session")
def admin_session(admin_token) -> requests.Session:
    return _paperless_session(admin_token)


@pytest.fixture(scope="session")
def user1_session() -> requests.Session:
    token = _paperless_token(USER1, USER1_PASSWORD)
    return _paperless_session(token)


@pytest.fixture(scope="session")
def user2_session() -> requests.Session:
    token = _paperless_token(USER2, USER2_PASSWORD)
    return _paperless_session(token)


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
def sample_pdf(tmp_path) -> Path:
    """Write a minimal valid PDF to a temp file and return its path."""
    pdf_path = tmp_path / f"test_{uuid.uuid4().hex[:8]}.pdf"
    pdf_path.write_bytes(_minimal_pdf())
    return pdf_path


@pytest.fixture
def uploaded_document(paperless_admin_client, admin_session, sample_pdf) -> Generator:
    """Upload a document, yield its metadata dict, then delete it."""
    title = f"IntegTest-{uuid.uuid4().hex[:8]}"
    tag_context = {"year_month": "2026-03", "directory_path": "2026-03"}

    ok, err = paperless_admin_client.upload(
        str(sample_pdf), title, created_date=None, tag_context=tag_context
    )
    assert ok, f"Upload failed: {err}"

    doc = _wait_for_document(admin_session, title)
    yield doc

    # Cleanup
    doc_id = doc["id"]
    admin_session.delete(f"{PAPERLESS_URL}/api/documents/{doc_id}/", timeout=10)


# ── Nextcloud fixtures ────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def nextcloud_admin_uploader(admin_token) -> NextcloudUploader:
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
