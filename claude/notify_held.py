#!/usr/bin/env python3
"""notify_command for kokoro: show a held message as a notification with buttons (Hammerspoon).

kokoro runs this with one argument: base64 JSON of the held message
({id, text, why, actions: [{label, command}]}). Falls back to a plain macOS notification.
"""
import base64, json, shutil, subprocess, sys

b64 = sys.argv[1] if len(sys.argv) > 1 else ""
import os
hs = shutil.which("hs") or next((p for p in ("/opt/homebrew/bin/hs", "/usr/local/bin/hs") if os.path.exists(p)),
                                 "/opt/homebrew/bin/hs")
try:
    r = subprocess.run([hs, "-c", f"voiceKit.notifyHeld('{b64}')"], capture_output=True, text=True, timeout=5)
    ok = r.returncode == 0
except Exception:
    ok = False
if not ok:
    item = json.loads(base64.b64decode(b64 or "e30="))
    subprocess.run(["osascript", "-e", f"display notification {json.dumps(item.get('text', '')[:200])} "
                    f"with title {json.dumps('Claude (held: ' + item.get('why', 'other audio') + ')')}"])
