"use strict";

// Nexus-compliant edition release config.
//
// This branch ships an independent product (Full edition lives on `main`).
// We use semantic-release's standard SemVer flow with a `nexus-v` tag prefix
// to avoid colliding with main's `v` tags. Each commit on this branch follows
// conventional-commits semantics (feat → minor, fix → patch, feat! → major).
//
// Distribution: every release is created as a GitHub draft. Nexus Mods upload
// only fires when the maintainer manually promotes the draft to published
// (`.github/workflows/upload-nexus.yml` listens to the `release: published`
// event). This guarantees no surprise uploads to the public Nexus page.
//
// History note: prior tags used the prerelease format `v2.0.0-nexus.N`. That
// scheme pinned the base at 2.0.0 because semantic-release prerelease branches
// freeze the base. Migrated to independent SemVer in May 2026. The
// `nexus-v2.0.0` baseline tag preserves continuity with the last
// `v2.0.0-nexus.14` release.

module.exports = {
  repositoryUrl: "https://github.com/Y4rd13/rippermod-manager",
  tagFormat: "nexus-v${version}",
  branches: ["nexus-compliant"],
  plugins: [
    ["@semantic-release/commit-analyzer", { preset: "conventionalcommits" }],
    [
      "@semantic-release/release-notes-generator",
      { preset: "conventionalcommits" },
    ],
    [
      "@semantic-release/exec",
      {
        successCmd:
          'echo "new_release_version=${nextRelease.version}" >> $GITHUB_OUTPUT',
      },
    ],
    [
      "@semantic-release/github",
      {
        draftRelease: true,
      },
    ],
  ],
};
