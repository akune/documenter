#!/bin/bash
#
# Wrapper script to run paperless_import.py in a Docker container
#
# Usage:
#   ./paperless-import.sh /path/to/documents [options]
#
# Options are passed through to paperless_import.py:
#   --dry-run, -d              Show what would be uploaded without actually uploading
#   --tags, -t TAGS            Additional tags to apply (can be specified multiple times)
#                              Supports variables: ${directory_path}, ${year_month}, ${filename}, ${title}
#   --no-recursive, -R         Do not search subdirectories
#   --verbose, -v              Enable verbose output
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGE_NAME="documenter:latest"
ENV_FILE="${SCRIPT_DIR}/.env"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

usage() {
    echo "Usage: $0 <path-to-documents> [options]"
    echo ""
    echo "Import existing documents to Paperless-ngx"
    echo ""
    echo "Arguments:"
    echo "  path-to-documents    Local path to search for PDF documents"
    echo ""
    echo "Options (passed to paperless_import.py):"
    echo "  --dry-run, -d              Show what would be uploaded without uploading"
    echo "  --tags, -t TAGS            Additional tags (can be used multiple times)"
    echo "                             Supports variables for dynamic tag names"
    echo "  --no-recursive, -R         Do not search subdirectories"
    echo "  --verbose, -v              Enable verbose output"
    echo ""
    echo "Examples:"
    echo "  $0 ~/Documents/Scans --dry-run"
    echo "  $0 ~/Documents/Scans --tags Archive --verbose"
    echo "  $0 ~/Documents/Archive/2023 -t 'Cabinet-\${directory_path}'"
    echo ""
    echo "Tag Variables:"
    echo "  \${directory_path}  Relative path from search directory"
    echo "  \${year_month}      Year and month from document (YYYY-MM)"
    echo "  \${filename}        Document filename"
    echo "  \${title}           Document title"
    echo ""
    echo "Configuration:"
    echo "  The script uses ${ENV_FILE} for Paperless-ngx credentials."
    echo "  Required variables: PAPERLESS_URL, PAPERLESS_API_TOKEN"
    echo "  PAPERLESS_DEFAULT_TAGS also supports variables."
    exit 1
}

error() {
    echo -e "${RED}Error: $1${NC}" >&2
    exit 1
}

info() {
    echo -e "${GREEN}$1${NC}"
}

warn() {
    echo -e "${YELLOW}$1${NC}"
}

# Check if at least one argument is provided
if [ $# -lt 1 ]; then
    usage
fi

# First argument is the path
DOCUMENTS_PATH="$1"
shift

# Resolve to absolute path
if [[ "$DOCUMENTS_PATH" != /* ]]; then
    DOCUMENTS_PATH="$(cd "$DOCUMENTS_PATH" 2>/dev/null && pwd)" || error "Path does not exist: $DOCUMENTS_PATH"
fi

# Validate the path exists and is a directory
if [ ! -d "$DOCUMENTS_PATH" ]; then
    error "Path does not exist or is not a directory: $DOCUMENTS_PATH"
fi

# Check for .env file
if [ ! -f "$ENV_FILE" ]; then
    error ".env file not found at: $ENV_FILE"
fi

# Check if Docker is available
if ! command -v docker &> /dev/null; then
    error "Docker is not installed or not in PATH"
fi

# Check if the image exists, build if necessary
if ! docker image inspect "$IMAGE_NAME" &> /dev/null; then
    warn "Docker image '$IMAGE_NAME' not found. Building..."
    (cd "$SCRIPT_DIR" && docker compose build) || error "Failed to build Docker image"
fi

info "Importing documents from: $DOCUMENTS_PATH"
echo ""

# Run the import script in a container
# - Mount the documents directory as read-only
# - Pass the .env file for configuration
# - Remove the container after execution
docker run --rm \
    --env-file "$ENV_FILE" \
    -v "$DOCUMENTS_PATH:/documents:ro" \
    "$IMAGE_NAME" \
    python3 /app/src/paperless_import.py /documents "$@"

echo ""
info "Done."