#!/bin/sh
# claude-voice-kit installer: one command, safe to re-run (re-running also updates).
#
#   ./install.sh               from a clone of the repo
#   ./install.sh --no-hotkeys  skip the Hammerspoon hotkeys
#
# It can also be run on its own (e.g. `curl -fsSL <raw install.sh URL> | sh`): it then clones the
# repo to $VOICEKIT_DIR (default ~/.claude-voice-kit) and installs from there.
set -e
REPO_URL="${VOICEKIT_REPO:-https://github.com/gobind-singh/claude-voice-kit.git}"

say() { printf '%s\n' "$*"; }
fail() { printf '\n❌ %s\n' "$*" >&2; exit 1; }

# --- this Mac -------------------------------------------------------------------------------
[ "$(uname -s)" = "Darwin" ] || fail "claude-voice-kit runs on macOS only."
[ "$(uname -m)" = "arm64" ] || fail "claude-voice-kit needs an Apple Silicon Mac (M1 or newer)."

# --- find (or fetch) the project ------------------------------------------------------------
DIR="$(cd "$(dirname "$0")" 2>/dev/null && pwd || true)"
if [ ! -f "$DIR/bin/voicekit" ]; then
  DIR="${VOICEKIT_DIR:-$HOME/.claude-voice-kit}"
  command -v git >/dev/null 2>&1 || fail "git is needed: run  xcode-select --install  and try again."
  if [ -d "$DIR/.git" ]; then
    say "Updating $DIR …"; git -C "$DIR" pull --ff-only
  else
    say "Downloading claude-voice-kit to $DIR …"; git clone --depth 1 "$REPO_URL" "$DIR"
  fi
fi

# --- prerequisites --------------------------------------------------------------------------
if ! command -v brew >/dev/null 2>&1; then
  for b in /opt/homebrew/bin/brew /usr/local/bin/brew; do [ -x "$b" ] && eval "$("$b" shellenv)"; done
fi
command -v brew >/dev/null 2>&1 || fail "Homebrew is needed: install it from https://brew.sh and run this again."
if ! command -v uv >/dev/null 2>&1; then
  say "Installing uv (Python package manager)…"; brew install uv
fi
if ! command -v claude >/dev/null 2>&1 && [ ! -x "$HOME/.local/bin/claude" ]; then
  say "⚠️  Claude Code was not found. Install it from https://claude.com/claude-code (the voice tools still install)."
fi

exec python3 "$DIR/bin/voicekit" install "$@"
