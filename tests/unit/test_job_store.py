import time

from job_store import JobStore, STATUS_DONE, STATUS_FAILED, STATUS_PROCESSING, STATUS_QUEUED


def test_job_lifecycle(tmp_path):
    store = JobStore(str(tmp_path / "jobs.db"))
    job_id = store.create("/input/scan.pdf", 1234)
    assert store.list_jobs()[0]["status"] == STATUS_QUEUED

    store.start(job_id)
    store.set_step(job_id, "Document 1/2: OCR")
    job = store.list_jobs()[0]
    assert job["status"] == STATUS_PROCESSING
    assert job["step"] == "Document 1/2: OCR"

    store.add_output(job_id, "2026-10-27_15-00-00_abcdef12.pdf", ["Nextcloud", "Paperless-ngx"])
    store.finish(job_id, True)
    job = store.list_jobs()[0]
    assert job["status"] == STATUS_DONE
    assert job["step"] is None
    assert job["outputs"] == [
        {"filename": "2026-10-27_15-00-00_abcdef12.pdf", "targets": ["Nextcloud", "Paperless-ngx"]}
    ]
    assert job["finished_at"] >= job["started_at"]


def test_failed_job_keeps_error_and_filter(tmp_path):
    store = JobStore(str(tmp_path / "jobs.db"))
    ok = store.create("/input/a.pdf")
    bad = store.create("/input/b.pdf")
    store.finish(ok, True)
    store.finish(bad, False, "Nextcloud upload failed: 507")

    failed = store.list_jobs(status=STATUS_FAILED)
    assert [j["id"] for j in failed] == [bad]
    assert failed[0]["error"] == "Nextcloud upload failed: 507"
    assert store.counts() == {STATUS_QUEUED: 0, STATUS_PROCESSING: 0, STATUS_DONE: 1, STATUS_FAILED: 1}


def test_open_jobs_are_marked_interrupted_after_restart(tmp_path):
    path = str(tmp_path / "jobs.db")
    store = JobStore(path)
    store.start(store.create("/input/a.pdf"))
    store.create("/input/b.pdf")
    store.close()

    reopened = JobStore(path)
    jobs = reopened.list_jobs()
    assert {j["status"] for j in jobs} == {STATUS_FAILED}
    assert all("restart" in j["error"] for j in jobs)


def test_old_finished_jobs_are_purged(tmp_path):
    path = str(tmp_path / "jobs.db")
    store = JobStore(path, retention_days=30)
    old = store.create("/input/old.pdf")
    store.finish(old, True)
    store._execute("UPDATE jobs SET finished_at = ? WHERE id = ?", (time.time() - 31 * 86400, old))
    store.finish(store.create("/input/new.pdf"), True)

    store.purge_old()
    assert [j["source"] for j in store.list_jobs()] == ["/input/new.pdf"]
