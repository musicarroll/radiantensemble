#!/bin/bash
# Usage: ./gitpush.sh "Your commit message"
# Rebase onto origin before pushing to avoid merge commits.

set -euo pipefail

EXPECTED_ROOT="/home/mcarroll/Documents/python/radiantensemble/website"
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"

if [ "$REPO_ROOT" != "$EXPECTED_ROOT" ]; then
  echo "Error: run this script from the radiantensemble website repo."
  echo "Expected: $EXPECTED_ROOT"
  echo "Current:  ${REPO_ROOT:-not a git repository}"
  exit 1
fi

cd "$REPO_ROOT"

if [ -z "${1:-}" ]; then
  echo "Usage: $0 \"commit message\""
  exit 1
fi

COMMIT_MSG="$1"

# Start ssh-agent if not already running.
if [ -z "${SSH_AUTH_SOCK:-}" ]; then
  eval "$(ssh-agent -s)"
  # Prefer your ed25519 key path; fallback to common defaults.
  ssh-add ~/.ssh/archive/id_ed25519 2>/dev/null || \
  ssh-add ~/.ssh/id_ed25519 2>/dev/null || \
  ssh-add ~/.ssh/id_rsa 2>/dev/null || true
fi

# Determine current branch.
BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo main)"
if [ "$BRANCH" = "HEAD" ]; then
  BRANCH="main"
fi

echo "Adding ..."
git add -A

echo "Committing ..."
git commit -m "$COMMIT_MSG" || true  # ok if nothing to commit

echo "Syncing with origin (rebase) ..."
git fetch origin
if ! git rebase "origin/${BRANCH}"; then
  echo
  echo "Rebase has conflicts. Resolve them, then run:"
  echo "  git add <fixed files> && git rebase --continue"
  echo "When done, push with:"
  echo "  git push origin ${BRANCH}"
  exit 1
fi

echo "Pushing ..."
git push origin "${BRANCH}"
echo "Success!!"
