#!/usr/bin/env bash
# Bump version in all project manifests.
# Called by semantic-release via @semantic-release/exec.
# Usage: bash scripts/bump-version.sh <version>
set -euo pipefail

VERSION="${1:?Usage: bump-version.sh <version>}"

echo "Bumping all manifests to ${VERSION}"

# frontend/package.json
jq --arg v "$VERSION" '.version = $v' frontend/package.json > frontend/package.json.tmp \
  && mv frontend/package.json.tmp frontend/package.json

# frontend/package-lock.json (top-level + packages."" entry)
jq --arg v "$VERSION" '.version = $v | .packages[""].version = $v' frontend/package-lock.json > frontend/package-lock.json.tmp \
  && mv frontend/package-lock.json.tmp frontend/package-lock.json

# frontend/src-tauri/tauri.conf.json
jq --arg v "$VERSION" '.version = $v' frontend/src-tauri/tauri.conf.json > frontend/src-tauri/tauri.conf.json.tmp \
  && mv frontend/src-tauri/tauri.conf.json.tmp frontend/src-tauri/tauri.conf.json

# frontend/src-tauri/Cargo.toml
sed -i "s/^version = \".*\"/version = \"${VERSION}\"/" frontend/src-tauri/Cargo.toml

# backend/pyproject.toml
sed -i "s/^version = \".*\"/version = \"${VERSION}\"/" backend/pyproject.toml

echo "All manifests bumped to ${VERSION}"
