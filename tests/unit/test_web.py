import json
import urllib.request

from job_store import JobStore
from web import render_page, start_web_server


def _store(tmp_path):
    store = JobStore(str(tmp_path / "jobs.db"))
    done = store.create(str(tmp_path / "done.pdf"), 2 * 1024 * 1024)
    store.start(done)
    store.add_output(done, "2026-10-27_15-00-00_abcdef12.pdf", ["Nextcloud"])
    store.finish(done, True)
    failed = store.create(str(tmp_path / "<evil>.pdf"))
    store.finish(failed, False, "OCR failed: <script>alert(1)</script>")
    return store


def test_page_lists_jobs_and_escapes_html(tmp_path):
    page = render_page(_store(tmp_path), None, "1.2.0")
    assert "done.pdf" in page
    assert "2026-10-27_15-00-00_abcdef12.pdf" in page
    assert "&lt;evil&gt;.pdf" in page
    assert "<script>alert(1)</script>" not in page
    assert "Failed <b>1</b>" in page


def test_failed_file_still_in_input_is_flagged(tmp_path):
    store = JobStore(str(tmp_path / "jobs.db"))
    source = tmp_path / "kept.pdf"
    source.write_bytes(b"%PDF-1.4")
    store.finish(store.create(str(source)), False, "Paperless-ngx upload failed")
    assert "still in the input folder" in render_page(store, "failed", "dev")


def test_http_endpoints(tmp_path):
    server = start_web_server(_store(tmp_path), 0, "dev")
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        with urllib.request.urlopen(base + "/?status=failed") as response:
            page = response.read().decode()
        assert "&lt;evil&gt;.pdf" in page and "done.pdf" not in page

        with urllib.request.urlopen(base + "/api/jobs") as response:
            data = json.load(response)
        assert data["counts"]["done"] == 1
        assert data["jobs"][0]["queued_at"].endswith("+00:00")

        with urllib.request.urlopen(base + "/healthz") as response:
            assert response.read() == b"ok\n"
    finally:
        server.shutdown()
