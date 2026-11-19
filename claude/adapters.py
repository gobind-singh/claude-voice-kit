"""Adapters: how voice commands reach a Claude session.

Order of preference per action:
  send a prompt:  voice channel (any terminal, when the session was started with `claude-voice`)
                  → herdr (`herdr agent prompt`) → plain window (activate app, paste, Enter)
  press keys:     herdr (`herdr agent send-keys`) → plain window (Escape/Enter only)
  focus:          herdr (`herdr agent focus`) + bring its terminal app to the front → app only
  read screen:    herdr (`herdr agent read`)
"""
import json, os, shutil, socket, subprocess, time

import voicekit_common as vk

HERDR = shutil.which("herdr") or os.path.expanduser("~/.local/bin/herdr")


# ---------------------------------------------------------------- herdr
def herdr_ok():
    return os.path.exists(HERDR)


def herdr(*args, timeout=15):
    """Run a herdr command; returns (ok, parsed_json_or_text)."""
    if not herdr_ok():
        return False, "herdr not installed"
    try:
        r = subprocess.run([HERDR, *args], capture_output=True, text=True, timeout=timeout)
    except Exception as e:
        return False, str(e)
    out = r.stdout.strip()
    try:
        data = json.loads(out)
        return ("error" not in data), data
    except Exception:
        return r.returncode == 0, out


def meaningful_label(label):
    """A tab name worth speaking: "docs" yes; "1", "4", "~" no."""
    label = (label or "").strip()
    return label if label and not label.isdigit() and label not in ("~", "-") else ""


def herdr_tab_labels(timeout=15):
    """{tab_id: spoken tab name} for herdr tabs you have named."""
    ok, data = herdr("api", "snapshot", timeout=timeout)
    if not ok or not isinstance(data, dict):
        return {}
    tabs = data.get("result", {}).get("snapshot", {}).get("tabs", [])
    return {t["tab_id"]: meaningful_label(t.get("label")) for t in tabs if t.get("tab_id")}


def herdr_agents():
    """herdr agents keyed by Claude session id: {session_id: {pane_id, status, name, focused, label}}."""
    ok, data = herdr("agent", "list")
    labels = herdr_tab_labels() if ok else {}
    agents = {}
    if ok and isinstance(data, dict):
        for a in data.get("result", {}).get("agents", []):
            sess = (a.get("agent_session") or {}).get("value")
            if sess:
                agents[sess] = {"pane_id": a.get("pane_id"), "status": a.get("agent_status"),
                                "name": a.get("name"), "focused": a.get("focused"), "cwd": a.get("cwd"),
                                "label": labels.get(a.get("tab_id"), "")}
    return agents


_HERDR_APP = None


def herdr_app_bundle():
    """Bundle id of the terminal app hosting the herdr client (e.g. com.mitchellh.ghostty)."""
    global _HERDR_APP
    if _HERDR_APP is not None:
        return _HERDR_APP
    _HERDR_APP = ""
    try:
        pids = subprocess.run(["pgrep", "-x", "herdr"], capture_output=True, text=True).stdout.split()
        for pid in pids:
            for _ in range(8):
                out = subprocess.run(["ps", "-o", "ppid=,comm=", "-p", pid], capture_output=True,
                                     text=True).stdout.strip()
                if not out:
                    break
                ppid, comm = out.split(None, 1)
                if ".app/" in comm:
                    app = comm[:comm.index(".app/") + 4]
                    b = subprocess.run(["mdls", "-raw", "-name", "kMDItemCFBundleIdentifier", app],
                                       capture_output=True, text=True).stdout.strip()
                    if b and b != "(null)":
                        _HERDR_APP = b
                        return b
                pid = ppid
    except Exception:
        pass
    return _HERDR_APP


def herdr_pane(s):
    """Current herdr pane of a session (live lookup first: panes move; else what the hook saw)."""
    live = herdr_agents().get(s["session_id"])
    if live:
        return live["pane_id"]
    return (s.get("terminal") or {}).get("herdr_pane")


# ---------------------------------------------------------------- channel
def channel_socket(s):
    pid = s.get("claude_pid")
    p = os.path.join(vk.CHANNEL_DIR, f"{pid}.sock") if pid else None
    return p if p and os.path.exists(p) else None


def channel_send(sock_path, text):
    try:
        c = socket.socket(socket.AF_UNIX)
        c.settimeout(3)
        c.connect(sock_path)
        c.sendall(text.encode())
        c.close()
        return True
    except OSError:
        return False


# ---------------------------------------------------------------- plain window (any terminal)
def activate_app(s):
    bundle = (s.get("terminal") or {}).get("app_bundle")
    if bundle:
        subprocess.run(["open", "-b", bundle], capture_output=True)
        return True
    return False


def osascript(script):
    return subprocess.run(["osascript", "-e", script], capture_output=True, text=True).returncode == 0


TTY_SCRIPTS = {   # apps that can tell us which terminal device (tty) their front tab is showing
    "com.apple.Terminal": 'tell application id "com.apple.Terminal" to get tty of selected tab of front window',
    "com.googlecode.iterm2": 'tell application id "com.googlecode.iterm2" to get tty of current session of current window',
}


def front_tab_is(s):
    """True only if the session's terminal app is showing exactly this session in its front tab.
    Without that proof we never type into a plain window: it could be a shell or another agent."""
    term = s.get("terminal") or {}
    script, tty = TTY_SCRIPTS.get(term.get("app_bundle") or ""), term.get("tty")
    if not script or not tty:
        return False
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=5)
    return r.returncode == 0 and r.stdout.strip() == tty


def window_paste(s, text):
    """Paste + Enter into the session's terminal window, only when its front tab is verified to be it."""
    if not front_tab_is(s) or not activate_app(s):
        return False
    saved = subprocess.run(["pbpaste"], capture_output=True, text=True).stdout
    subprocess.run(["pbcopy"], input=text, text=True)
    time.sleep(0.35)
    ok = osascript('tell application "System Events" to keystroke "v" using command down') and \
        osascript('delay 0.15\ntell application "System Events" to key code 36')
    time.sleep(0.2)
    subprocess.run(["pbcopy"], input=saved, text=True)
    return ok


KEYCODES = {"esc": 53, "enter": 36}


def window_keys(s, *keys):
    if not front_tab_is(s) or not activate_app(s):
        return False
    time.sleep(0.3)
    ok = True
    for k in keys:
        if k in KEYCODES:
            ok &= osascript(f'tell application "System Events" to key code {KEYCODES[k]}')
        elif len(k) == 1 and k.isalnum():
            ok &= osascript(f'tell application "System Events" to keystroke "{k}"')
    return ok


# ---------------------------------------------------------------- actions
def send_prompt(s, text):
    """Returns the route used, or None."""
    sock = channel_socket(s)
    if sock and channel_send(sock, text):
        return "channel"
    pane = herdr_pane(s)
    if pane:
        ok, data = herdr("agent", "prompt", pane, text)
        if ok:
            return "herdr"
        if isinstance(data, dict) and data.get("error", {}).get("code") == "agent_blocked":
            return "blocked"
    if window_paste(s, text):
        return "window"
    return None


def send_keys(s, *keys):
    pane = herdr_pane(s)
    if pane:
        ok, _ = herdr("agent", "send-keys", pane, *keys)
        if ok:
            return "herdr"
    return "window" if window_keys(s, *keys) else None


def focus(s):
    pane = herdr_pane(s)
    ok = False
    if pane:
        ok, _ = herdr("agent", "focus", pane)
    activate_app(s)
    return "herdr" if ok else "app"


def read_screen(s, lines=30):
    pane = herdr_pane(s)
    if not pane:
        return ""
    ok, out = herdr("agent", "read", pane)
    text = out if isinstance(out, str) else json.dumps(out)
    return "\n".join(text.splitlines()[-lines:])
