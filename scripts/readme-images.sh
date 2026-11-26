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
// Hammerspoon's menu windows that are on screen and visible, front to back. A menu that was just
// closed can stay listed (sometimes under the same window number), so we always pick at capture time.
func menuWindows() -> [[String: Any]] {
  let list = CGWindowListCopyWindowInfo([.optionOnScreenOnly], kCGNullWindowID) as? [[String: Any]] ?? []
  return list.filter { w in
    (w[kCGWindowOwnerPID as String] as? Int32) == pid
      && (w[kCGWindowLayer as String] as? Int) == Int(CGWindowLevelForKey(.popUpMenuWindow))
      && ((w[kCGWindowAlpha as String] as? Double) ?? 1) > 0
  }
}
for _ in 0..<100 { if !menuWindows().isEmpty { break }; usleep(50_000) }   // up to 5 s
usleep(600_000)   // let the menu finish drawing
let found = menuWindows()
for w in found {
  FileHandle.standardError.write("\(out): window \(w[kCGWindowNumber as String] ?? "?") \(((w[kCGWindowBounds as String] as? [String: Any]) ?? [:]).sorted { $0.key < $1.key }.map { "\($0.key)=\($0.value)" }.joined(separator: " "))\n".data(using: .utf8)!)
}
if let id = found.first?[kCGWindowNumber as String] as? Int {
  let p = Process()
  p.executableURL = URL(fileURLWithPath: "/usr/sbin/screencapture")
  p.arguments = ["-x", "-l", String(id), out]
  try? p.run(); p.waitUntilExit()
} else {
  FileHandle.standardError.write("\(out): menu window not found\n".data(using: .utf8)!)
}
// Press Esc until the menu has really closed: Hammerspoon is stuck until it does.
for _ in 0..<5 {   // a few tries at most: once the menu is gone, Esc would reach your app
  for down in [true, false] {
    CGEvent(keyboardEventSource: nil, virtualKey: 53, keyDown: down)?.post(tap: .cghidEventTap)
  }
  usleep(200_000)
  if menuWindows().isEmpty { break }
}
SWIFT
swiftc -O -o "$TMP/menucap" "$TMP/menucap.swift" 2>/dev/null

# The menu captures depend on timing: now and then the second one catches the first menu before it has
# closed. The two menu pictures must differ, so try up to 3 times.
for attempt in 1 2 3; do
  rm -f "$ROOT"/docs/images/*.png "$TMP/done"   # so a failed capture can't leave an old picture behind
  hs -c "return dofile('$ROOT/scripts/readme-images.lua')('$ROOT', '$TMP')" >/dev/null &   # the done file is what counts
  i=0
  while [ ! -f "$TMP/done" ]; do
    i=$((i + 1)); [ $i -gt 120 ] && { echo "✗ timed out (if a menu is still open, press Esc)"; exit 1; }
    sleep 0.25
  done
  M1="$ROOT/docs/images/menu.png"; M2="$ROOT/docs/images/menu-shortcuts.png"
  [ -f "$M1" ] && [ -f "$M2" ] && ! cmp -s "$M1" "$M2" && break
  echo "… a menu picture is missing or the two matched (attempt $attempt); trying again"
  [ $attempt -eq 3 ] && { echo "✗ couldn't capture the shortcuts menu"; cat "$TMP/menucap.log" 2>/dev/null; exit 1; }
done
echo "✅ images written to docs/images/:"
ls "$ROOT/docs/images" "$ROOT/docs/images/icons"
