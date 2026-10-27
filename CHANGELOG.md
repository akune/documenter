# Changelog

All notable changes to this project will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Status web interface (port `WEB_PORT`, default 8080): lists queued, processing, done and failed documents with the current processing step, the generated files and their targets, and the error messages of failed documents. It marks failed source files that are still in the input folder. JSON at `/api/jobs`, health check at `/healthz`.
- Job history in SQLite (`STATE_DB`, default `/data/documenter.db`), kept for `HISTORY_DAYS` (default 90). Jobs that were open when the service stopped are marked as interrupted.
- Unit tests for the job history and the web interface (`tests/unit`)

### Changed
- Duplicate file system events for the same file (e.g. create and move) no longer queue it twice, so they no longer show up as "file no longer exists" errors
- `docker-compose.yml` publishes port 8080 and mounts `./data` for the job history

## [1.1.2] - 2026-10-12

### Fixed
- Python dependencies pinned to the versions of the working v1.1.0 image. The v1.1.1 image installed ocrmypdf 17.13.0, while the ocrmypdf 17.4.0 source tree of the base image shadows it via `PYTHONPATH`. It then failed at startup with `ModuleNotFoundError: No module named 'deprecation'`. Do not use v1.1.1.

## [1.1.1] - 2026-10-12

### Fixed
- Paperless-ngx 3.x compatibility: the uploader now requests REST API version 9 instead of 6. Paperless-ngx 3.x rejects versions below 9 with `406 Invalid version in "Accept" header`, so tags (e.g. `Inbox/<yyyy-mm>`) were no longer looked up or created and new documents arrived without them. Version 10 is not used yet because it changes the `/api/tasks/` response format.
- Integration tests: helpers, fixtures and the Paperless init script request API version 9 as well
- Dockerfile: base image pinned to `jbarlow83/ocrmypdf:v17.4.0` (the base of v1.1.0). Current `latest` no longer runs as root, so the `apt-get` step failed and no image could be built.
- README: added missing `PAPERLESS_GROUP` environment variable to configuration table
- README: fixed duplicate step number in Quick Start list

## [1.1.0] - 2026-03-28

### Added
- Integration test setup: Docker Compose environment with Paperless-ngx, Nextcloud, Redis, and a one-shot init container
- `tests/integration/init/init_paperless.py` — creates test users and TestFamily group via Paperless REST API
- `tests/integration/init/init_nextcloud.py` — creates test users, group, and shares scan folder via Nextcloud OCS API
- `tests/integration/conftest.py` — pytest session/function fixtures for uploaders, user sessions, and document lifecycle
- `tests/integration/test_paperless_upload.py` — upload correctness tests (title, date, tags)
- `tests/integration/test_paperless_permissions.py` — group permission tests, including regression test for tag visibility fix
- `tests/integration/test_nextcloud_upload.py` — WebDAV upload, admin access, and group share visibility tests
- `Makefile` with `make test-integration` target

### Fixed
- `PaperlessUploader.upload()` now waits for the Celery consumer task and sets group permissions via PATCH after document creation (`set_permissions` in `post_document` is silently ignored by Paperless-ngx 2.20)
- Integration tests: `PaperlessUploader.upload()` returns the Celery task ID on success, enabling reliable task-based document polling
- Integration tests: `uploaded_document` and `sample_pdf` fixtures are now session-scoped to avoid redundant uploads across tests
- Integration tests: per-test uploads use `unique_pdf` fixture to avoid Paperless duplicate-detection failures
- Integration tests: `_wait_for_init` now also verifies Nextcloud user1 WebDAV authentication, triggering home-directory creation before tests run
- Integration tests: Nextcloud healthcheck now requires `"installed":true` in `status.php` so the init container does not start before installation is complete
- Integration tests: Nextcloud `NEXTCLOUD_TRUSTED_DOMAINS` now includes the Docker service name so the init container can reach the OCS API
- Integration tests: Nextcloud test-user passwords updated to pass Nextcloud 33's compromised-password policy
- Integration tests: Makefile `test-integration-up` starts core services with `--wait` first, then starts the one-shot init container separately to avoid `--wait` failing on an exited container
- Integration tests: `init_nextcloud.py` verifies `installed:true` before making OCS API calls
- Dockerfile: re-declare `ARG VERSION` after `FROM` so the OCI version label is correctly set (fixes build warning)
- SIGTERM (Docker stop/restart) now triggers graceful shutdown, same as Ctrl+C
- Shutdown timeout increased from 5 s to 60 s so large PDFs finish processing before exit
- Observer thread is now always joined via `finally`, even if the main loop exits unexpectedly
- Source file is no longer deleted when any upload step fails
- Inline `import shutil` and `import json` moved to module-level imports
- Misplaced docstring in `_get_or_create_group` moved above the first statement

## [1.0.1] - 2026-03-28

### Fixed
- Tags created via the Paperless-ngx API now receive group permissions (`set_permissions`)
  so all group members can see them, not just the API token owner
- Docker `latest` image tag is now only updated on version releases, not every push to main

### Added
- `CHANGELOG.md` tracking all notable changes
- `VERSION` file as the single source of version truth
- `scripts/release.sh` to automate version bump, commit, tag, and push
- `Dockerfile` now labels images with `org.opencontainers.image.version`

## [1.0.0] - 2026-03-28

### Added
- Initial Docker-based PDF document processor using OCRmyPDF
- OCR with invisible text layer, deskew, rotation correction, and page cleaning
- Blank page detection and removal
- QR code–based document splitting (`[dmsqrnd]` marker)
- Nextcloud upload via WebDAV
- Paperless-ngx upload via REST API
- Filename format `YYYY-MM-DD_hh-mm-ss_HASH.pdf` with date extraction
- Tag template variable support (`${directory_path}`, `${year_month}`, `${filename}`, `${title}`)
- Group-based document permissions in Paperless-ngx (`PAPERLESS_GROUP`)
- Group permissions applied to newly created tags so all group members can see them
- CLI tool (`paperless-import.sh`) for batch-importing existing documents
- GitHub Actions workflow for multi-platform Docker Hub publishing (`linux/amd64`, `linux/arm64`)
