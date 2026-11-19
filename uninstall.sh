#!/bin/sh
# claude-voice-kit uninstaller.
#   ./uninstall.sh          remove hooks, service, commands and hotkeys (keeps your settings)
#   ./uninstall.sh --purge  also delete settings, saved replies and the voice model
DIR="$(cd "$(dirname "$0")" && pwd)"
exec python3 "$DIR/bin/voicekit" uninstall "$@"
