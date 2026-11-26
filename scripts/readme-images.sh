#!/bin/sh
# Regenerates the README / docs images in docs/images/ from the kit's own drawing code
# (scripts/readme-images.lua). Needs Hammerspoon running with the `hs` tool, Screen Recording
# permission for Hammerspoon, and Xcode's command-line tools (for a tiny capture helper).
# The HUD pop-up and the menu bar menu appear on screen for a few seconds while they are captured.
set -e
ROOT=$(cd "$(dirname "$0")/.." && pwd)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

command -v hs >/dev/null || { echo "✗ the hs command was not found (is Hammerspoon installed and running?)"; exit 1; }

# Default shortcuts (an empty config folder means "no changes"), so the pictures show the defaults.
PY="$ROOT/packages/kokoro-voice/.venv/bin/python"; [ -x "$PY" ] || PY=python3
mkdir -p "$TMP/config"
VOICEKIT_CONFIG_DIR="$TMP/config" "$PY" "$ROOT/claude/shortcuts.py" --json > "$TMP/shortcuts.json"

# Helper: waits for Hammerspoon's open menu, saves a picture of that window, then presses Esc to close it.
cat > "$TMP/menucap.swift" <<'SWIFT'
import Cocoa
let pid = Int32(CommandLine.arguments[1])!
let out = CommandLine.arguments[2]
func menuWindow() -> Int? {
  let list = CGWindowListCopyWindowInfo([.optionOnScreenOnly], kCGNullWindowID) as? [[String: Any]] ?? []
  for w in list where (w[kCGWindowOwnerPID as String] as? Int32) == pid
                   && (w[kCGWindowLayer as String] as? Int) == Int(CGWindowLevelForKey(.popUpMenuWindow)) {
    return w[kCGWindowNumber as String] as? Int
  }
  return nil
}
var id: Int? = nil
for _ in 0..<40 { if let w = menuWindow() { id = w; break }; usleep(50_000) }
usleep(600_000)   // let the menu finish drawing
if let id = id {
  let p = Process()
  p.executableURL = URL(fileURLWithPath: "/usr/sbin/screencapture")
  p.arguments = ["-x", "-l", String(id), out]
  try? p.run(); p.waitUntilExit()
} else {
  FileHandle.standardError.write("menu window not found\n".data(using: .utf8)!)
}
for down in [true, false] {
  CGEvent(keyboardEventSource: nil, virtualKey: 53, keyDown: down)?.post(tap: .cghidEventTap)
}
SWIFT
swiftc -O -o "$TMP/menucap" "$TMP/menucap.swift" 2>/dev/null

rm -f "$ROOT"/docs/images/*.png   # so a failed capture can't leave an old picture behind
hs -c "return dofile('$ROOT/scripts/readme-images.lua')('$ROOT', '$TMP')" >/dev/null &   # replies may lag; the done file is what counts
i=0
while [ ! -f "$TMP/done" ]; do
  i=$((i + 1)); [ $i -gt 120 ] && { echo "✗ timed out (if a menu is still open, press Esc)"; exit 1; }
  sleep 0.25
done
echo "✅ images written to docs/images/:"
ls "$ROOT/docs/images" "$ROOT/docs/images/icons"
