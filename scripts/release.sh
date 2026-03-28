#!/usr/bin/env bash
# release.sh — Bump version, update CHANGELOG, commit, tag, and push.
# Usage: ./scripts/release.sh <MAJOR.MINOR.PATCH>

set -euo pipefail

VERSION="${1:-}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# ── Validate ──────────────────────────────────────────────────────────────────

if [[ -z "${VERSION}" ]]; then
  echo "Usage: $0 <MAJOR.MINOR.PATCH>" >&2
  exit 1
fi

if ! [[ "${VERSION}" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "Error: version must be MAJOR.MINOR.PATCH (e.g. 1.2.3)" >&2
  exit 1
fi

if [[ -n "$(git -C "${ROOT}" status --porcelain)" ]]; then
  echo "Error: working directory is not clean. Commit or stash changes first." >&2
  exit 1
fi

if git -C "${ROOT}" rev-parse "v${VERSION}" &>/dev/null; then
  echo "Error: tag v${VERSION} already exists." >&2
  exit 1
fi

TODAY="$(date +%Y-%m-%d)"

# ── Update VERSION ─────────────────────────────────────────────────────────────

echo "${VERSION}" > "${ROOT}/VERSION"

# ── Update CHANGELOG.md ───────────────────────────────────────────────────────
# Replace the first occurrence of "## [Unreleased]" with a versioned header,
# then insert a fresh "[Unreleased]" section above it.

CHANGELOG="${ROOT}/CHANGELOG.md"

if ! grep -q "## \[Unreleased\]" "${CHANGELOG}"; then
  echo "Error: no [Unreleased] section found in CHANGELOG.md" >&2
  exit 1
fi

# Use awk: on the first match, print new Unreleased + blank line + versioned header
awk -v ver="${VERSION}" -v date="${TODAY}" '
  /^## \[Unreleased\]$/ && !done {
    print "## [Unreleased]"
    print ""
    print "## [" ver "] - " date
    done=1
    next
  }
  { print }
' "${CHANGELOG}" > "${CHANGELOG}.tmp" && mv "${CHANGELOG}.tmp" "${CHANGELOG}"

# ── Commit, tag, push ─────────────────────────────────────────────────────────

git -C "${ROOT}" add VERSION CHANGELOG.md
git -C "${ROOT}" commit -m "Release v${VERSION}"
git -C "${ROOT}" tag -a "v${VERSION}" -m "Release v${VERSION}"
git -C "${ROOT}" push origin main --follow-tags

echo "Released v${VERSION}"
