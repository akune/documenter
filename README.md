# Document Processor

A Docker-based service for automatic processing of scanned PDF documents.

## Features

- **Automatic monitoring** of input directory for new PDFs
- **Blank page detection and removal**
- **Deskewing** - Straightening skewed scanned pages
- **Automatic orientation detection** and correction
- **OCR** - Text recognition with invisible text layer
- **QR code based document splitting** - Automatic splitting at separator pages
- **Automatic renaming** to `YYYY-MM-DD_hh-mm-ss_HASH.pdf` format
- **Nextcloud upload** via WebDAV into `YYYY-MM` subfolders
- **Paperless-ngx upload** with configurable tags
- **Local output directory** (optional) for processed documents

## Quick Start

### 1. Configure settings

```bash
cp .env.example .env
# Edit .env and add your credentials
```

### 2. Build Docker image

```bash
docker compose build
```

### 3. Start service

```bash
docker compose up -d
```

### 4. Process PDFs

Simply place PDF files in the `./input` folder. They will automatically be:

1. Cleaned and straightened
2. Cleared of blank pages
3. OCR processed with text layer
4. Split at QR code separator pages
5. Renamed to `YYYY-MM-DD_hh-mm-ss_<MD5>.pdf`
6. Uploaded to Nextcloud (subfolder `YYYY-MM`)
7. Sent to Paperless-ngx with configured tags
8. Deleted from input folder

## Configuration

All settings are controlled via environment variables:

### OCR Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `OCR_LANGUAGE` | `deu+eng` | Tesseract language codes |
| `OCR_DESKEW` | `true` | Straighten pages |
| `OCR_CLEAN` | `true` | Remove noise |
| `OCR_ROTATE_PAGES` | `true` | Auto-rotation |

### Blank Page Detection

| Variable | Default | Description |
|----------|---------|-------------|
| `BLANK_PAGE_REMOVAL` | `true` | Enable |
| `BLANK_PAGE_THRESHOLD` | `0.99` | Threshold (0.99 = 99% white) |

### QR Code Document Splitting

| Variable | Default | Description |
|----------|---------|-------------|
| `SPLIT_QR_ENABLED` | `true` | Enable |
| `SPLIT_QR_CONTENT` | `[dmsqrnd]` | QR code content for splitting |

### Nextcloud

| Variable | Default | Description |
|----------|---------|-------------|
| `NEXTCLOUD_ENABLED` | `true` | Enable upload |
| `NEXTCLOUD_URL` | - | Server URL |
| `NEXTCLOUD_USER` | - | Username |
| `NEXTCLOUD_PASSWORD` | - | App password |
| `NEXTCLOUD_TARGET_DIR` | `/Documents/Scans` | Target directory |

### Paperless-ngx

| Variable | Default | Description |
|----------|---------|-------------|
| `PAPERLESS_ENABLED` | `true` | Enable upload |
| `PAPERLESS_URL` | - | Server URL |
| `PAPERLESS_API_TOKEN` | - | API token |
| `PAPERLESS_DEFAULT_TAGS` | `Inbox` | Default tags (comma-separated, supports variables) |
| `PAPERLESS_GROUP` | `` | Group name for document and tag permissions (optional) |

**Tag Variables:** Tags can include variables that are resolved at upload time:

| Variable | Description |
|----------|-------------|
| `${directory_path}` | Relative directory path (import) or YYYY-MM (processing) |
| `${year_month}` | Year and month from document (YYYY-MM) |
| `${filename}` | Document filename |
| `${title}` | Document title |

Example: `PAPERLESS_DEFAULT_TAGS=Inbox,Cabinet-${directory_path}`

### Output Directory

| Variable | Default | Description |
|----------|---------|-------------|
| `OUTPUT_DIR_ENABLED` | `false` | Enable output directory |
| `OUTPUT_DIR` | `/output` | Path to output directory |
| `OUTPUT_DIR_USE_SUBFOLDERS` | `true` | Use YYYY-MM subfolders |

### Processing

| Variable | Default | Description |
|----------|---------|-------------|
| `DELETE_SOURCE` | `true` | Delete source file after processing |
| `FILE_STABILITY_SECONDS` | `5` | Wait until file is fully written |
| `LOG_LEVEL` | `INFO` | Log level (DEBUG, INFO, WARNING, ERROR) |

## Creating a Nextcloud App Password

1. Open Nextcloud → Settings → Security
2. Under "App passwords" create a new password
3. Enter a name (e.g., "Document Processor")
4. Add the generated password to `.env`

## Creating a Paperless-ngx API Token

1. Open Paperless-ngx Admin → API Tokens
2. Create a new token for the user
3. Add the token to `.env`

## Directory Structure

```
documenter/
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example
├── paperless-import.sh         # CLI wrapper for importing existing documents
├── input/                      # Place PDFs here
├── output/                     # Processed PDFs (optional)
└── src/
    ├── main.py                 # Watchdog-based directory monitoring
    ├── config.py               # Configuration
    ├── pdf_processor.py        # OCR, deskew, blank page removal
    ├── document_splitter.py    # QR code based document splitting
    ├── nextcloud_uploader.py   # Nextcloud WebDAV
    ├── paperless_uploader.py   # Paperless-ngx API
    ├── paperless_import.py     # CLI tool for importing existing documents
    ├── template_resolver.py    # Variable substitution for tags
    └── utils.py                # Utility functions
```

## View Logs

```bash
docker compose logs -f documenter
```

## Importing Existing Documents

You can import already-processed documents to Paperless-ngx using the import tool.
It searches for files matching the pattern `YYYY-MM-DD_hh-mm-ss_HASH.pdf` and uploads them with appropriate tags.

### Using the Bash Wrapper (Recommended)

```bash
# Dry-run (shows what would be uploaded)
./paperless-import.sh ~/Documents/Scans --dry-run

# Import documents
./paperless-import.sh ~/Documents/Scans

# With custom tags (replaces defaults from .env)
./paperless-import.sh ~/Documents/Scans --tags Archive --tags '${year_month}' --verbose

# With dynamic tags using variables
./paperless-import.sh ~/Documents/Archive/2023 -t 'Cabinet-${directory_path}' -t Inbox
```

### Using Docker Directly

```bash
docker compose run --rm documenter python3 /app/src/paperless_import.py /documents --dry-run
```

### Options

| Option | Description |
|--------|-------------|
| `--dry-run`, `-d` | Show what would be uploaded without uploading |
| `--tags`, `-t` | Tags to apply (replaces PAPERLESS_DEFAULT_TAGS, supports variables) |
| `--no-recursive`, `-R` | Do not search subdirectories |
| `--verbose`, `-v` | Enable verbose output |

## Releases

Releases follow [Semantic Versioning](https://semver.org). All changes are documented in [CHANGELOG.md](CHANGELOG.md).

### Creating a release

```bash
./scripts/release.sh <MAJOR.MINOR.PATCH>
```

The script will:
1. Validate the version format and that the working directory is clean
2. Update `VERSION` and collapse `[Unreleased]` into a dated version entry in `CHANGELOG.md`
3. Commit, tag (`vX.Y.Z`), and push

Pushing the tag triggers GitHub Actions to build and publish multi-platform Docker images (`linux/amd64`, `linux/arm64`) tagged as `X.Y.Z`, `X.Y`, and `latest`.

> **Note:** Add all changes under `## [Unreleased]` in `CHANGELOG.md` during development. Do not add the version header manually — the release script does this.

## Integration Tests

The integration test suite spins up real Paperless-ngx and Nextcloud instances via Docker Compose, initialises test users and a group, and runs all upload and permission tests against them.

**Requirements:** Docker, `pytest`, and `requests` installed locally.

```bash
make test-integration
```

This brings up the test environment, waits for all services to be ready, runs the 13 tests, and tears everything down. Individual steps are also available:

```bash
make test-integration-up    # Start services and run init
make test-integration-down  # Tear down and remove volumes
make test-integration-logs  # View service logs
```

## Troubleshooting

### Connection error to Nextcloud

- Check if URL is correct (without trailing `/`)
- Use app password instead of regular password
- Check SSL certificate if applicable

### Connection error to Paperless-ngx

- Is API token correct?
- Is URL reachable?
- Check firewall rules

### Poor OCR quality

- Try different language codes
- Increase DPI of scan source
- Enable `OCR_CLEAN=true`

### Blank pages not detected

- Lower `BLANK_PAGE_THRESHOLD` (e.g., `0.95`)
- For pages with headers/footers, consider disabling

### QR code splitting not working

- QR code must be clearly readable (sufficient contrast)
- Content must exactly match `SPLIT_QR_CONTENT` (default: `[dmsqrnd]`)
- QR-Code Generator: https://www.qr-code-generator.com/
- To disable temporarily: set `SPLIT_QR_ENABLED=false`
