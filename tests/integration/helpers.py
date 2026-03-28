"""
Shared constants and helper functions for integration tests.
Importable by both conftest.py and test modules.
"""
import time
import uuid

import requests

# ── Service coordinates ────────────────────────────────────────────────────────

PAPERLESS_URL = "http://localhost:8010"
NEXTCLOUD_URL = "http://localhost:8011"

ADMIN_USER = "admin"
ADMIN_PASSWORD = "admin"
USER1 = "user1"
USER1_PASSWORD = "Nxt-Cl0ud-Test!U1"
USER2 = "user2"
USER2_PASSWORD = "Nxt-Cl0ud-Test!U2"
GROUP_NAME = "TestFamily"
NEXTCLOUD_TARGET_DIR = "/Documents/Scans"


# ── PDF generation ────────────────────────────────────────────────────────────

def minimal_pdf() -> bytes:
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


# ── Paperless helpers ─────────────────────────────────────────────────────────

def paperless_token(username: str, password: str) -> str:
    """Fetch a Paperless-ngx API token."""
    r = requests.post(
        f"{PAPERLESS_URL}/api/token/",
        json={"username": username, "password": password},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["token"]


def paperless_session(token: str) -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "Authorization": f"Token {token}",
        "Accept": "application/json; version=6",
    })
    return s


def wait_for_task(session: requests.Session, task_id: str, timeout: int = 180) -> int:
    """Poll until a Paperless-ngx task succeeds. Returns the related document ID."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = session.get(
            f"{PAPERLESS_URL}/api/tasks/",
            params={"task_id": task_id},
            timeout=10,
        )
        if r.status_code == 200:
            results = r.json()
            if results:
                task = results[0]
                status = task.get("status")
                if status == "SUCCESS":
                    related_doc = task.get("related_document")
                    if related_doc is not None:
                        return int(related_doc)
                elif status in ("FAILURE", "REVOKED"):
                    raise RuntimeError(
                        f"Paperless task {task_id} failed with status {status}: "
                        f"{task.get('result', '')}"
                    )
        time.sleep(3)
    raise TimeoutError(f"Paperless task '{task_id}' did not complete within {timeout}s")


def wait_for_document(session: requests.Session, title: str, timeout: int = 120) -> dict:
    """Poll until a document with the given title appears in Paperless-ngx."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = session.get(
            f"{PAPERLESS_URL}/api/documents/",
            params={"title__iexact": title},
            timeout=10,
        )
        if r.status_code == 200:
            results = r.json().get("results", [])
            if results:
                return results[0]
        time.sleep(3)
    raise TimeoutError(f"Document '{title}' did not appear in Paperless-ngx within {timeout}s")
