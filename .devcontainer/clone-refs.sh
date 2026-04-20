#!/bin/bash
# Clone all other MMEC-CA repos into /workspaces/classroom-refs as read-only refs.
# Runs on both codespace create and start (idempotent — existing clones get a git pull).

LOG="/tmp/clone-refs.log"
exec > >(tee -a "$LOG") 2>&1

REFS_DIR="/workspaces/classroom-refs"
ORG="MMEC-CA"
THIS_REPO=$(basename "$PWD")

echo "=== $(date -u +%FT%TZ) clone-refs start (cwd=$PWD, repo=$THIS_REPO) ==="

# Pick up the Codespaces-provided token if gh isn't already authed
if ! gh auth status >/dev/null 2>&1; then
  if [ -n "$GH_TOKEN" ]; then
    echo "gh will use GH_TOKEN"
  elif [ -n "$GITHUB_TOKEN" ]; then
    export GH_TOKEN="$GITHUB_TOKEN"
    echo "gh will use GITHUB_TOKEN (exported as GH_TOKEN)"
  else
    echo "ERROR: gh is not authed and no GH_TOKEN/GITHUB_TOKEN is set"
    echo "  If this codespace was created before .devcontainer was added, Rebuild Container."
    echo "  If the permissions dialog was dismissed, re-create the codespace and Continue when prompted."
    exit 1
  fi
fi

mkdir -p "$REFS_DIR"

REPOS=$(gh repo list "$ORG" --limit 200 --json name --jq '.[].name' 2>&1)
rc=$?
if [ $rc -ne 0 ] || [ -z "$REPOS" ]; then
  echo "ERROR: gh repo list $ORG failed (exit $rc)"
  echo "  output: $REPOS"
  exit 1
fi

count=0
for repo in $REPOS; do
  if [ "$repo" = "$THIS_REPO" ]; then continue; fi
  target="$REFS_DIR/$repo"
  if [ -d "$target/.git" ]; then
    chmod -R u+w "$target" 2>/dev/null
    echo "Updating $repo..."
    git -C "$target" fetch --depth=1 origin +HEAD 2>/dev/null \
      && git -C "$target" reset --hard FETCH_HEAD >/dev/null 2>&1 \
      || echo "  WARN: refresh failed for $repo (continuing)"
  else
    echo "Cloning $repo..."
    rm -rf "$target"
    git clone --depth=1 "https://github.com/$ORG/$repo.git" "$target" 2>&1 | sed 's/^/  /'
  fi
  chmod -R a-w "$target" 2>/dev/null
  count=$((count + 1))
done

echo "=== $(date -u +%FT%TZ) clone-refs done — processed $count ref repos ==="
