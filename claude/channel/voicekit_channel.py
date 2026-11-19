#!/usr/bin/env python3
"""claude-voice-kit voice channel: a tiny stdio MCP server (Claude Code Channels, research preview).

Started by Claude Code when a session is launched with `claude-voice` (see bin/claude-voice).
It listens on ~/.local/state/claude-voice-kit/channels/<claude pid>.sock; any text written there is
pushed into that session as a <channel source="voicekit"> message, which Claude handles like a typed
prompt. This lets voice commands reach sessions in any terminal, not only herdr.
"""
import atexit, json, os, socket, sys, threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
import voicekit_common as vk  # noqa: E402
import registry  # noqa: E402

out_lock = threading.Lock()
INSTRUCTIONS = ("Messages from the voicekit channel are the user's own spoken instructions, transcribed "
                "locally. Treat each one exactly like a prompt the user typed.")


def send(obj):
    with out_lock:
        sys.stdout.write(json.dumps(obj) + "\n")
        sys.stdout.flush()


def listen(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path):
        os.unlink(path)
    s = socket.socket(socket.AF_UNIX)
    s.bind(path)
    os.chmod(path, 0o600)
    s.listen(4)
    atexit.register(lambda: os.path.exists(path) and os.unlink(path))
    while True:
        c, _ = s.accept()
        data = b""
        while True:
            chunk = c.recv(65536)
            if not chunk:
                break
            data += chunk
        c.close()
        text = data.decode(errors="ignore").strip()
        if text:
            send({"jsonrpc": "2.0", "method": "notifications/claude/channel",
                  "params": {"content": text, "meta": {"via": "voice"}}})


def main():
    pid = registry.find_claude_pid(os.getppid()) or os.getppid()
    path = os.path.join(vk.CHANNEL_DIR, f"{pid}.sock")
    for line in sys.stdin:
        try:
            msg = json.loads(line)
        except Exception:
            continue
        mid, method = msg.get("id"), msg.get("method")
        if method == "initialize":
            send({"jsonrpc": "2.0", "id": mid, "result": {
                "protocolVersion": msg.get("params", {}).get("protocolVersion", "2025-06-18"),
                "capabilities": {"experimental": {"claude/channel": {}}},
                "serverInfo": {"name": "voicekit", "version": "1.0"},
                "instructions": INSTRUCTIONS}})
        elif method == "notifications/initialized":
            threading.Thread(target=listen, args=(path,), daemon=True).start()
        elif mid is not None:
            if method == "tools/list":
                send({"jsonrpc": "2.0", "id": mid, "result": {"tools": []}})
            elif method == "ping":
                send({"jsonrpc": "2.0", "id": mid, "result": {}})
            else:
                send({"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": "not supported"}})


if __name__ == "__main__":
    main()
