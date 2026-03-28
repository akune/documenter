# Integration Test Setup

> **Status: TODO** — Concept documented, not yet implemented.

## Goal

A Docker Compose–based environment with real Nextcloud and Paperless-ngx instances,
pre-configured with multiple users and a group, usable for both manual exploration
and automated pytest runs.

---

## Directory Structure

```
tests/integration/
├── docker-compose.test.yml      # All test services
├── .env.test                    # Fixed credentials for test env
├── init/
│   ├── init_paperless.sh        # Creates users, group, API tokens in Paperless
│   └── init_nextcloud.sh        # Creates users, shared folder in Nextcloud
├── fixtures/
│   └── sample.pdf               # Minimal valid PDF for upload tests
├── conftest.py                  # pytest fixtures (service URLs, tokens, clients)
├── test_paperless_upload.py     # Upload + metadata correctness
├── test_paperless_permissions.py# Tag/document visibility per user
└── test_nextcloud_upload.py     # WebDAV upload + file accessibility
```

---

## Services (`docker-compose.test.yml`)

| Service | Image | Purpose |
|---|---|---|
| `paperless-redis` | `redis:7-alpine` | Task queue for Paperless |
| `paperless` | `ghcr.io/paperless-ngx/paperless-ngx:latest` | Paperless-ngx instance |
| `nextcloud` | `nextcloud:latest` | Nextcloud instance (SQLite) |
| `test-init` | `python:3.12-slim` | One-shot init container (runs init scripts, then exits) |

Paperless uses SQLite (`PAPERLESS_DBENGINE=sqlite`) to avoid a separate DB container.
Nextcloud uses its built-in SQLite. Both are stateless — volumes are ephemeral (no
named volumes), so each `docker compose up` starts clean.

Ports exposed on localhost for manual access:
- Paperless: `8010`
- Nextcloud: `8011`

---

## Test Users & Group

Defined in `.env.test` with fixed credentials:

| User | Role | Services |
|---|---|---|
| `admin` | Superuser / API token owner | Paperless, Nextcloud |
| `user1` | Regular, member of `TestFamily` group | Paperless, Nextcloud |
| `user2` | Regular, member of `TestFamily` group | Paperless, Nextcloud |

The `TestFamily` group in Paperless gets the same `GROUP_PERMISSIONS` as the
production config.

---

## Initialization Strategy

**`test-init` container** runs after health checks confirm both services are up
(using `depends_on: condition: service_healthy`), then executes both init scripts
and exits with code 0.

**`init_paperless.sh`** — runs inside the `paperless` container via `docker exec`
(or as a sidecar using the shared network):
1. `manage.py createsuperuser` → `admin`
2. `manage.py createsuperuser` → `user1`, `user2`
3. `manage.py drf_create_token admin` → captures token, writes to shared volume file
4. REST API calls to create `TestFamily` group and add users
5. REST API calls to verify group permissions

**`init_nextcloud.sh`** — uses `php occ` commands:
1. `occ user:add` → `user1`, `user2`
2. `occ group:add TestFamily`
3. `occ group:adduser TestFamily user1/user2`
4. `occ files_sharing:create-share` → share `/Documents/Scans` from `admin` to group `TestFamily`

Tokens and credentials are written to a shared tmpfs volume (`/test-config/`) so
pytest can read them without hardcoding.

---

## pytest Architecture (`conftest.py`)

**Session-scoped** (set up once per test run):
- `paperless_admin_client` — `PaperlessUploader` using admin token
- `paperless_user1_session` / `paperless_user2_session` — raw `requests.Session`
  authenticated as user1/user2 for visibility assertions
- `nextcloud_admin_uploader` — `NextcloudUploader` using admin credentials
- `nextcloud_user1_session` — `requests.Session` for WebDAV PROPFIND as user1

**Function-scoped**:
- `uploaded_document(paperless_admin_client, ...)` — uploads a sample PDF, yields
  the task result, then deletes it for cleanup

A session-scoped `wait_for_services()` fixture polls both health endpoints before
any test runs (no fixed `sleep`).

---

## Test Cases

**`test_paperless_upload.py`**
- `test_upload_succeeds` — upload returns HTTP 202, task completes
- `test_upload_sets_title` — document title matches
- `test_upload_sets_date` — created date matches filename
- `test_upload_creates_tags` — expected tag IDs present on document

**`test_paperless_permissions.py`**
- `test_tag_visible_to_user1` — `GET /api/tags/?name=...` as user1 returns the tag
- `test_tag_visible_to_user2` — same for user2
- `test_document_visible_to_user1` — document appears in user1's document list
- `test_document_not_visible_without_group` — upload without group → user1 cannot
  see it (negative test)

**`test_nextcloud_upload.py`**
- `test_upload_succeeds` — PUT returns 201
- `test_file_accessible_to_admin` — PROPFIND as admin finds the file
- `test_file_accessible_via_group_share` — PROPFIND as user1 finds the file in
  the shared folder

---

## Running

```bash
# Manual exploration (services stay up, UIs accessible in browser)
docker compose -f tests/integration/docker-compose.test.yml up

# Automated (pytest drives everything, tears down after)
docker compose -f tests/integration/docker-compose.test.yml up -d --wait
pytest tests/integration/
docker compose -f tests/integration/docker-compose.test.yml down -v
```

A `Makefile` target `make test-integration` wraps these three steps.

---

## Key Design Decisions

- **Ephemeral volumes** — no state bleeds between runs; `down -v` is a full reset.
- **Fixed credentials in `.env.test`** — deliberately not secret, simplifies local
  and CI use; `.env.test` is committed.
- **Real services, no mocks** — tests call the actual `PaperlessUploader` /
  `NextcloudUploader` classes, exercising the same code paths as production.
- **Init via one-shot container** — keeps service containers clean; no custom
  entrypoint patches needed.
- **Paperless task polling** — `post_document` is async; tests must poll
  `GET /api/tasks/?task_id=...` until status is `SUCCESS` before asserting
  document metadata.
