# Integration Test Setup

> **Status: DONE** — Implemented 2026-03-28, all 13 tests passing.

---

## What Was Built

A Docker Compose–based integration test environment with real Paperless-ngx and Nextcloud
instances, pre-configured with test users and a group, driven by pytest.

Run with:

```bash
make test-integration
```

---

## Directory Structure (as built)

```
tests/integration/
├── docker-compose.test.yml      # All test services
├── init/
│   ├── init_paperless.py        # Creates users, group via Paperless REST API
│   └── init_nextcloud.py        # Creates users, group, shares folder via OCS API
├── helpers.py                   # Shared constants, minimal_pdf(), wait helpers
├── conftest.py                  # pytest fixtures
├── test_paperless_upload.py     # Upload + metadata correctness (4 tests)
├── test_paperless_permissions.py# Tag/document visibility per user (5 tests)
└── test_nextcloud_upload.py     # WebDAV upload + file accessibility (4 tests)
```

No `.env.test` or `fixtures/` directory — credentials are constants in `helpers.py`
and PDFs are generated programmatically via `minimal_pdf()`.

---

## Services

| Service | Image | Purpose |
|---|---|---|
| `paperless-redis` | `redis:7-alpine` | Task queue for Paperless |
| `paperless` | `ghcr.io/paperless-ngx/paperless-ngx:latest` | Paperless-ngx (SQLite) |
| `nextcloud` | `nextcloud:latest` | Nextcloud (SQLite) |
| `test-init` | `python:3.12-slim` | One-shot: calls REST/OCS APIs to create users/groups |

---

## Key Implementation Notes

- **Task-based document polling**: `upload()` returns the Celery task ID; tests use
  `wait_for_task()` to poll `GET /api/tasks/?task_id=...` until `status == "SUCCESS"`.
- **Document permissions via PATCH**: `set_permissions` in `post_document` is silently
  ignored by Paperless-ngx 2.20; the uploader waits for the task and PATCHes permissions
  on the resulting document.
- **Session-scoped fixtures**: `uploaded_document` and `sample_pdf` are session-scoped to
  avoid redundant uploads; per-test uploads use `unique_pdf` (function-scoped) to avoid
  Paperless duplicate detection.
- **Nextcloud trusted domains**: `NEXTCLOUD_TRUSTED_DOMAINS` includes the Docker service
  name so the init container can reach the OCS API.
- **Nextcloud healthcheck**: Requires `"installed":true` in `status.php` — the plain
  HTTP 200 check fires too early, before installation completes.
- **Makefile**: Core services started with `--wait`, then init container started
  separately to avoid `--wait` failing on an exited one-shot container.
- **No Docker socket**: init uses REST/OCS APIs over the Docker network, not `docker exec`.
- **Ephemeral volumes**: `make test-integration-down` runs `down -v` for a clean reset.
