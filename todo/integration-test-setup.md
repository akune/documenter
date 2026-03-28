# Integration Test Setup

> **Status: TODO** — Concept updated after feasibility review (2026-03-28).

---

## Feasibility Assessment

The plan is **feasible as-is** with one correction: the original init strategy
assumed `docker exec` to run `manage.py` and `occ` commands, but a one-shot
init container cannot exec into sibling containers without mounting the Docker
socket. Both services expose HTTP APIs that can be used instead — this is
actually simpler and more portable.

All other design decisions hold up.

---

## Changes Since Original Plan

| Change | Impact on tests |
|---|---|
| Tags now get `set_permissions` on creation (the bug fix) | `test_tag_visible_to_user1/2` now tests real production behaviour |
| SIGTERM handled for graceful shutdown | No impact on tests |
| Import cleanup, docstring fix | No impact on tests |

The permission tests are now the **most important** tests to have — they verify
the exact fix that was made.

---

## Goal

A Docker Compose–based environment with real Nextcloud and Paperless-ngx instances,
pre-configured with multiple users and a group, usable for both manual exploration
and automated pytest runs.

---

## Directory Structure

```
tests/integration/
├── docker-compose.test.yml      # All test services
├── .env.test                    # Fixed credentials for test env (committed)
├── init/
│   ├── init_paperless.py        # Creates users, group, token via Paperless REST API
│   └── init_nextcloud.py        # Creates users, shared folder via Nextcloud OCS API
├── fixtures/
│   └── sample.pdf               # Minimal valid PDF for upload tests
├── conftest.py                  # pytest fixtures
├── test_paperless_upload.py     # Upload + metadata correctness
├── test_paperless_permissions.py# Tag/document visibility per user (key test)
└── test_nextcloud_upload.py     # WebDAV upload + file accessibility
```

Init scripts are Python (not shell) to avoid curl/jq dependencies and to share
logic with the test fixtures.

---

## Services (`docker-compose.test.yml`)

| Service | Image | Purpose |
|---|---|---|
| `paperless-redis` | `redis:7-alpine` | Task queue for Paperless |
| `paperless` | `ghcr.io/paperless-ngx/paperless-ngx:latest` | Paperless-ngx instance |
| `nextcloud` | `nextcloud:latest` | Nextcloud instance (SQLite) |
| `test-init` | `python:3.12-slim` | One-shot container: calls REST/OCS APIs to create users, groups, tokens |

Paperless uses `PAPERLESS_DBENGINE=sqlite` (supported, avoids a DB container).
Nextcloud uses SQLite (default when no external DB is configured). Both use
ephemeral anonymous volumes — each `docker compose up` starts clean.

Ports exposed on localhost for manual access:
- Paperless: `8010`
- Nextcloud: `8011`

---

## Test Users & Group

Defined in `.env.test` with fixed, non-secret credentials:

| User | Role | Services |
|---|---|---|
| `admin` | Superuser / API token owner | Paperless, Nextcloud |
| `user1` | Regular, member of `TestFamily` group | Paperless, Nextcloud |
| `user2` | Regular, member of `TestFamily` group | Paperless, Nextcloud |

---

## Initialization Strategy (corrected)

**`test-init` container** starts after both services pass their health checks
(`depends_on: condition: service_healthy`), then runs both init scripts and
exits 0. It shares the Docker network with the other services, so it can reach
them by service name (e.g. `http://paperless:8000`).

**`init_paperless.py`** — uses the Paperless REST API over the shared network:
1. Admin user is pre-created via env vars `PAPERLESS_ADMIN_USER` /
   `PAPERLESS_ADMIN_PASSWORD` / `PAPERLESS_ADMIN_MAIL` — no `manage.py` needed
2. Obtain admin token: `POST /api/token/` with admin credentials
3. Create `user1`, `user2`: `POST /api/users/`
4. Create `TestFamily` group with `GROUP_PERMISSIONS`: `POST /api/groups/`
5. Add users to group: `PATCH /api/users/{id}/` with groups list
6. Write admin token to shared volume `/test-config/paperless_token`

**`init_nextcloud.py`** — uses the Nextcloud OCS Provisioning API:
1. Admin user pre-configured via `NEXTCLOUD_ADMIN_USER` / `NEXTCLOUD_ADMIN_PASSWORD`
2. Create `user1`, `user2`: `POST /ocs/v1.php/cloud/users`
3. Create `TestFamily` group: `POST /ocs/v1.php/cloud/groups`
4. Add users to group: `POST /ocs/v1.php/cloud/users/{user}/groups`
5. Share `/Documents/Scans` with group: `POST /ocs/v2.php/apps/files_sharing/api/v1/shares`

Both scripts poll their service's health endpoint before proceeding.

---

## pytest Architecture (`conftest.py`)

**Session-scoped** (set up once per test run):
- `paperless_admin_client` — `PaperlessUploader` with admin token, `TestFamily` group
- `paperless_user1_session` / `paperless_user2_session` — `requests.Session`
  authenticated as user1/user2 for visibility assertions
- `nextcloud_admin_uploader` — `NextcloudUploader` using admin credentials
- `nextcloud_user1_session` — `requests.Session` for WebDAV PROPFIND as user1

Credentials are read from `.env.test` (not from the shared tmpfs volume — the
tokens are fixed by the init script predictably enough to hardcode in `.env.test`).

**Function-scoped**:
- `uploaded_document` — uploads `fixtures/sample.pdf`, yields doc metadata,
  deletes it on teardown via `DELETE /api/documents/{id}/`

A session-scoped `wait_for_services()` fixture polls health endpoints with a
timeout before any test runs.

---

## Test Cases

**`test_paperless_upload.py`**
- `test_upload_succeeds` — returns HTTP 202, task polls to `SUCCESS`
- `test_upload_sets_title` — document title matches
- `test_upload_sets_date` — created date matches filename
- `test_upload_creates_tags` — expected tag IDs present on document

**`test_paperless_permissions.py`** ← **most important: verifies the tag permissions fix**
- `test_tag_visible_to_user1` — `GET /api/tags/?name=...` as user1 returns the tag
- `test_tag_visible_to_user2` — same for user2
- `test_document_visible_to_user1` — document appears in user1's document list
- `test_document_not_visible_without_group` — upload without group → user1 cannot
  see it (negative test, confirms permissions are not granted by default)

**`test_nextcloud_upload.py`**
- `test_upload_succeeds` — PUT returns 201
- `test_file_accessible_to_admin` — PROPFIND as admin finds the file
- `test_file_accessible_via_group_share` — PROPFIND as user1 finds the file

---

## Running

```bash
# Manual exploration (services stay up, UIs accessible in browser)
docker compose -f tests/integration/docker-compose.test.yml up

# Automated
docker compose -f tests/integration/docker-compose.test.yml up -d --wait
pytest tests/integration/ -v
docker compose -f tests/integration/docker-compose.test.yml down -v
```

`make test-integration` wraps the automated steps.

---

## Key Design Decisions

- **No Docker socket** — init uses REST/OCS APIs over the shared Docker network,
  not `docker exec`. Simpler and more portable.
- **Ephemeral volumes** — `down -v` is a full reset; no state bleeds between runs.
- **Fixed credentials in `.env.test`** — committed, non-secret; works locally and in CI.
- **Real uploaders, no mocks** — tests call actual `PaperlessUploader` /
  `NextcloudUploader` code, not HTTP doubles.
- **Paperless task polling** — `post_document` is async; poll
  `GET /api/tasks/?task_id=...` until `status == "SUCCESS"` before asserting.
- **Init in Python** — avoids curl/jq shell dependencies; shares `requests`
  which is already in the project's `requirements.txt`.
