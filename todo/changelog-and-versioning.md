# Changelog & Versioning Mechanism

## Goal

Track all notable changes in a `CHANGELOG.md` file following the
[Keep a Changelog](https://keepachangelog.com) format, version releases using
SemVer, and automatically tag published Docker images with the corresponding
version.

---

## Version Source of Truth: `VERSION` file

A single `VERSION` file in the project root holds the current release version
(e.g. `1.2.3`). This is the canonical source used by:
- `CHANGELOG.md` (referenced in release headers)
- Docker image tags (read by GitHub Actions at build time)
- The Docker image `LABEL org.opencontainers.image.version`

No other file duplicates the version number.

---

## `CHANGELOG.md` Format

Follows [Keep a Changelog](https://keepachangelog.com) conventions:

```markdown
# Changelog

## [Unreleased]
### Fixed
- Tag permissions now set on newly created tags so all group members can see them

## [1.0.0] - 2026-03-28
### Added
- Initial release with OCR, blank page removal, QR splitting
- Paperless-ngx and Nextcloud upload support
- Group-based document permissions
```

**Change categories** (use only what applies):
- `Added` — new features
- `Changed` — changes to existing behaviour
- Fixed` — bug fixes
- `Removed` — removed features
- `Deprecated` — features to be removed in a future release
- `Security` — security fixes

During normal development, all new entries go under `[Unreleased]`. The
`[Unreleased]` section is never given a version number until release time.

---

## SemVer Rules for This Project

| Change type | Version bump |
|---|---|
| Breaking change to config format, removed env var, incompatible behaviour | MAJOR |
| New feature (new uploader target, new processing option, new config key) | MINOR |
| Bug fix, performance improvement, log/docs change | PATCH |

---

## Release Workflow

Releases are triggered manually via a helper script. The script is the only
mechanism that should ever bump the version or create a release tag.

### `scripts/release.sh <version>`

Steps performed by the script:

1. **Validate** input matches `MAJOR.MINOR.PATCH` pattern.
2. **Check** that `git status` is clean (no uncommitted changes).
3. **Update `VERSION`** file with the new version string.
4. **Update `CHANGELOG.md`**: replace `## [Unreleased]` with
   `## [X.Y.Z] - YYYY-MM-DD` and insert a fresh empty `## [Unreleased]`
   section above it.
5. **Commit** both files: `git commit -m "Release vX.Y.Z"`.
6. **Tag**: `git tag -a vX.Y.Z -m "Release vX.Y.Z"`.
7. **Push** commit and tag: `git push origin main --follow-tags`.

Pushing the tag triggers the GitHub Actions workflow (see below).

---

## GitHub Actions Changes (`docker-publish.yml`)

The existing workflow builds on every push to `main` and tags images as
`latest` + SHA. The updated workflow will:

- **Keep** the `push: branches: [main]` trigger for `latest` + SHA builds
  (useful for testing the current state).
- **Add** a `push: tags: ['v*.*.*']` trigger that builds a versioned release.

On a version tag push, `docker/metadata-action` produces these image tags:

| Tag | Example | When |
|---|---|---|
| `latest` | `kune/documenter:latest` | Every tagged release |
| Full SemVer | `kune/documenter:1.2.3` | Every tagged release |
| Major.Minor | `kune/documenter:1.2` | Every tagged release |

The version is read from the git tag itself (via `metadata-action`
`type=semver` pattern), so no extra secrets or env vars are needed.

The `Dockerfile` gains a build arg and label:

```dockerfile
ARG VERSION=dev
LABEL org.opencontainers.image.version=$VERSION
```

The workflow passes `--build-arg VERSION=${{ steps.meta.outputs.version }}`.

---

## File Summary

| File | Change |
|---|---|
| `VERSION` | New — single source of version truth |
| `CHANGELOG.md` | New — tracks all changes per release |
| `scripts/release.sh` | New — automates version bump, commit, tag, push |
| `.github/workflows/docker-publish.yml` | Updated — add tag-triggered versioned builds |
| `Dockerfile` | Updated — add `VERSION` build arg and OCI label |
