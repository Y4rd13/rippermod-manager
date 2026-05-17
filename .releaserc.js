"use strict";

// On nexus-compliant we ship to Nexus Mods only after the maintainer manually
// promotes the GitHub Release from draft to published — that publish event
// fires `.github/workflows/upload-nexus.yml`. Keep main on the default
// auto-publish flow (it has no Nexus upload).
const branch =
  process.env.GITHUB_REF_NAME ||
  process.env.BRANCH_NAME ||
  process.env.BRANCH ||
  "";

const isNexusBranch = branch === "nexus-compliant";

module.exports = {
  repositoryUrl: "https://github.com/Y4rd13/rippermod-manager",
  tagFormat: "v${version}",
  branches: [
    "main",
    { name: "nexus-compliant", channel: "nexus", prerelease: "nexus" },
  ],
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
        draftRelease: isNexusBranch,
      },
    ],
  ],
};
