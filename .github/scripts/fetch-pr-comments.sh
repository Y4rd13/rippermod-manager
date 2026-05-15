#!/usr/bin/env bash
#
# Fetch existing PR discussion state and write to /tmp/pr_comments_context.txt.
# Used by claude-pr-review.yml to inject resolved/outdated thread state into
# the review prompt so Claude does not re-raise settled issues.
#
# Environment:
#   GH_TOKEN     — required (github.token from the workflow)
#   REPO_OWNER   — required
#   REPO_NAME    — required
#   PR_NUMBER    — required
#   OUTPUT_FILE  — optional, defaults to /tmp/pr_comments_context.txt
#
set -euo pipefail

: "${GH_TOKEN:?GH_TOKEN is required}"
: "${REPO_OWNER:?REPO_OWNER is required}"
: "${REPO_NAME:?REPO_NAME is required}"
: "${PR_NUMBER:?PR_NUMBER is required}"

OUTPUT_FILE="${OUTPUT_FILE:-/tmp/pr_comments_context.txt}"
QUERY_RESULT="/tmp/pr_query_result.json"

# Default empty payload in case the query fails (non-fatal).
echo '{"data":{"repository":{"pullRequest":{"reviewThreads":{"nodes":[]},"reviews":{"nodes":[]}}}}}' > "$QUERY_RESULT"

gh api graphql -f query='
  query($owner: String!, $name: String!, $number: Int!) {
    repository(owner: $owner, name: $name) {
      pullRequest(number: $number) {
        reviewThreads(first: 100) {
          nodes {
            isResolved
            isOutdated
            path
            line
            comments(first: 3) {
              nodes { author { login } body }
            }
          }
        }
        reviews(first: 50) {
          nodes { author { login } state body }
        }
      }
    }
  }
' -F owner="$REPO_OWNER" -F name="$REPO_NAME" -F number="$PR_NUMBER" \
  > "$QUERY_RESULT" 2>/dev/null || echo "Warning: gh api graphql failed, using empty context" >&2

{
  echo "=== Resolved or outdated review threads (DO NOT re-raise these issues) ==="
  jq -r '.data.repository.pullRequest.reviewThreads.nodes[]
    | select(.isResolved == true or .isOutdated == true)
    | "- path=\(.path // "?") line=\(.line // "?") resolved=\(.isResolved) outdated=\(.isOutdated)\n  \((.comments.nodes[0].body // "")[0:300])"' \
    "$QUERY_RESULT" 2>/dev/null || true
  echo
  echo "=== Open review threads (context only) ==="
  jq -r '.data.repository.pullRequest.reviewThreads.nodes[]
    | select(.isResolved == false and .isOutdated == false)
    | "- path=\(.path // "?") line=\(.line // "?")\n  \((.comments.nodes[0].body // "")[0:300])"' \
    "$QUERY_RESULT" 2>/dev/null || true
  echo
  echo "=== Prior review summaries ==="
  jq -r '.data.repository.pullRequest.reviews.nodes[]
    | "- [\(.author.login)] \(.state): \((.body // "")[0:300])"' \
    "$QUERY_RESULT" 2>/dev/null || true
} > "$OUTPUT_FILE"

line_count=$(wc -l < "$OUTPUT_FILE")
echo "Wrote PR discussion context to $OUTPUT_FILE (${line_count} lines)"
