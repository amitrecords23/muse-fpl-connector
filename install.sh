#!/usr/bin/env bash
# One-command installer for the Muse FPL connector (custom.fpl).
#
# Two ways to run it:
#   1. From a local clone:
#        git clone https://github.com/amitrecords23/muse-fpl-connector
#        cd muse-fpl-connector
#        chmod +x install.sh
#        ./install.sh
#   2. Without cloning (downloads the repo for you):
#        curl -fsSL https://raw.githubusercontent.com/amitrecords23/muse-fpl-connector/main/install.sh | bash
#
# It copies the connector files into ~/workspace/custom-connectors/custom.fpl/
# and the skill into ~/workspace/custom-skills/fpl/. It is safe to re-run:
# it only copies those files and creates those directories. It never touches
# your FPL login, credentials (~/.fpl-mcp/), team config, or any venv.
# Set MUSE_WORKSPACE to install somewhere else (used for testing):
#   MUSE_WORKSPACE=/tmp/test-workspace ./install.sh
#
# After installing, you still need to set your own team ID with fpl_setup
# and sign in once yourself with fpl_login. See README.md.

set -euo pipefail

REPO_URL="https://github.com/amitrecords23/muse-fpl-connector"
REPO_BRANCH="main"

WORKSPACE="${MUSE_WORKSPACE:-${HOME}/workspace}"
CONNECTOR_DIR="${WORKSPACE}/custom-connectors/custom.fpl"
SKILL_DIR="${WORKSPACE}/custom-skills/fpl"

die() {
  printf 'install.sh: error: %s\n' "$*" >&2
  exit 1
}

warn() {
  printf 'install.sh: warning: %s\n' "$*" >&2
}

# --- Prerequisites ---------------------------------------------------------
command -v python3 >/dev/null 2>&1 || die "python3 is required but was not found. Install Python 3.12+ first."

if ! python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)'; then
  warn "python3 is older than 3.12 ($(python3 --version 2>&1)). This connector needs Python 3.12+; the install will continue, but the client may not work."
fi

if ! command -v uvx >/dev/null 2>&1 && ! command -v uv >/dev/null 2>&1; then
  warn "neither uvx nor uv was found. The client runs the FPL server with 'uvx fantasy-premier-league-mcp@0.3.2' unless a venv already exists under ${CONNECTOR_DIR}/venv. Install uv from https://docs.astral.sh/uv/ (or create that venv yourself) before running the client."
fi

# --- Find the repo files ---------------------------------------------------
# When run from a clone, the files sit next to this script (or in the
# current directory). When piped from curl, BASH_SOURCE is empty and the
# files are not here, so clone the repo into a temp dir first.
SCRIPT_PATH="${BASH_SOURCE[0]:-}"
SCRIPT_DIR=""
if [[ -n "$SCRIPT_PATH" && "$SCRIPT_PATH" != "-" ]]; then
  SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_PATH")" && pwd)"
fi

REPO_DIR=""
for dir in "$SCRIPT_DIR" "$PWD"; do
  if [[ -n "$dir" \
    && -f "$dir/CONNECTOR.md" \
    && -f "$dir/connector.yaml" \
    && -f "$dir/bin/client.py" \
    && -f "$dir/skills/fpl/SKILL.md" \
    && -f "$dir/skills/fpl/skill.yaml" ]]; then
    REPO_DIR="$dir"
    break
  fi
done

TMP_CLONE=""
if [[ -z "$REPO_DIR" ]]; then
  command -v git >/dev/null 2>&1 || die "git is required to download the connector but was not found. Install git, or clone ${REPO_URL} yourself and run ./install.sh from the clone."
  TMP_CLONE="$(mktemp -d)"
  trap '[[ -n "${TMP_CLONE:-}" ]] && rm -rf "$TMP_CLONE"' EXIT
  echo "install.sh: downloading ${REPO_URL} ..."
  git clone --depth 1 --branch "$REPO_BRANCH" "$REPO_URL" "$TMP_CLONE/repo" >/dev/null
  REPO_DIR="$TMP_CLONE/repo"
fi

# --- Install ---------------------------------------------------------------
mkdir -p "$CONNECTOR_DIR/bin" "$SKILL_DIR"

cp "$REPO_DIR/CONNECTOR.md" "$REPO_DIR/connector.yaml" "$CONNECTOR_DIR/"
cp "$REPO_DIR/bin/client.py" "$CONNECTOR_DIR/bin/"
cp "$REPO_DIR/skills/fpl/SKILL.md" "$REPO_DIR/skills/fpl/skill.yaml" "$SKILL_DIR/"

# Verify the copies match the sources.
for pair in \
  "$REPO_DIR/CONNECTOR.md:$CONNECTOR_DIR/CONNECTOR.md" \
  "$REPO_DIR/connector.yaml:$CONNECTOR_DIR/connector.yaml" \
  "$REPO_DIR/bin/client.py:$CONNECTOR_DIR/bin/client.py" \
  "$REPO_DIR/skills/fpl/SKILL.md:$SKILL_DIR/SKILL.md" \
  "$REPO_DIR/skills/fpl/skill.yaml:$SKILL_DIR/skill.yaml"; do
  src="${pair%%:*}"
  dst="${pair##*:}"
  cmp -s "$src" "$dst" || die "copy check failed for $dst"
done

echo "install.sh: installed the FPL connector."
echo "  Connector: $CONNECTOR_DIR"
echo "  Skill:     $SKILL_DIR"
echo ""
echo "Next steps:"
echo "  1. Verify it lists 24 tools:"
echo "       python3 \"$CONNECTOR_DIR/bin/client.py\" list-tools"
echo "  2. Set your team ID (the number in fantasy.premierleague.com/entry/<TEAM_ID>/event/1):"
echo "       echo '{\"team_id\": 0}' > /tmp/fpl-setup.json"
echo "       python3 \"$CONNECTOR_DIR/bin/client.py\" call-tool --name fpl_setup --arguments-file /tmp/fpl-setup.json"
echo "     Replace 0 with your real team ID."
echo "  3. Sign in once yourself, in your own browser, with fpl_login (the server never sees your password)."
echo "     For that you need Playwright Chromium: uvx --from playwright playwright install chromium"
echo "  4. Approval gate: always preview a change first with dry_run=true, and only submit"
echo "     with dry_run=false after you approve that exact preview in chat."
echo "  See README.md for the full instructions."
