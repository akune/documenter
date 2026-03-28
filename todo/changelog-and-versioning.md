# Changelog & Versioning Mechanism

> **Status: DONE** — Implemented in commit `f9c1dd9`, released as `v1.0.1`.

## What was implemented

All items from the original plan are complete:

| File | Status |
|---|---|
| `VERSION` | ✅ Created — holds `1.0.1` |
| `CHANGELOG.md` | ✅ Created — v1.0.0 and v1.0.1 entries, empty `[Unreleased]` |
| `scripts/release.sh` | ✅ Created — automates version bump, commit, tag, push |
| `.github/workflows/docker-publish.yml` | ✅ Updated — versioned builds on `v*.*.*` tags |
| `Dockerfile` | ✅ Updated — `ARG VERSION=dev` + OCI version label |
| `README.md` | ✅ Updated — "Releases" section documents the workflow |

## Deviations from original plan

- **`latest` tag**: Originally planned to be published on both main pushes and
  version tags. Changed so `latest` is only updated on version tag releases
  (not every main push). Main branch pushes produce a SHA-tagged image only.

## Release workflow (as built)

```bash
./scripts/release.sh <MAJOR.MINOR.PATCH>
```

> **Important:** Only add entries under `## [Unreleased]` in `CHANGELOG.md`
> during development. Do not write the version header manually — the script
> does this. Writing it manually causes a duplicate header on the next release.

On a version tag push, GitHub Actions publishes:

| Tag | When |
|---|---|
| `kune/documenter:1.2.3` | Every tagged release |
| `kune/documenter:1.2` | Every tagged release |
| `kune/documenter:latest` | Every tagged release |
| `kune/documenter:<sha>` | Every push to main |
