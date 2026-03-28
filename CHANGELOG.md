# Changelog

All notable changes to this project will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
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
