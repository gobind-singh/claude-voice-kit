"""Session registry: every Claude Code session reports itself here through hooks.

Stored in ~/.local/state/claude-voice-kit/sessions.json (file-locked; hooks of many sessions
write concurrently). Each entry:
  session_id, cwd, project, transcript, state (idle|working|waiting|done|failed|ended),
  started, updated, last_prompt, pending (what it's waiting for), claude_pid,
  terminal: {program, app_bundle, herdr_pane, tty}, alias (spoken name you gave it),
  label (herdr tab name, e.g. "docs")
Spoken name: alias (or herdr agent name) > tab name > folder name; duplicates get "2", "3", …
"""
import contextlib, fcntl, json, os, re, subprocess, time

import voicekit_common as vk

ENDED_KEEP_SECONDS = 600
STALE_SECONDS = 24 * 3600


@contextlib.contextmanager
def _locked():
    vk.ensure_dirs()
    with open(vk.SESSIONS_FILE + ".lock", "w") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        try:
            try:
                with open(vk.SESSIONS_FILE) as f:
                    data = json.load(f)
            except Exception:
                data = {}
            box = {"data": data}
            yield box
            tmp = vk.SESSIONS_FILE + ".tmp"
            with open(tmp, "w") as f:
                json.dump(box["data"], f, indent=1)
            os.replace(tmp, vk.SESSIONS_FILE)
        finally:
            fcntl.flock(lk, fcntl.LOCK_UN)


def _alive(pid):
    if not pid:
        return True
    try:
        os.kill(int(pid), 0)
        return True
    except (ProcessLookupError, ValueError):
        return False
    except PermissionError:
        return True


def _prune(data):
    now = time.time()
    for sid in list(data):
        s = data[sid]
        if s.get("state") == "ended" and now - s.get("updated", 0) > ENDED_KEEP_SECONDS:
            del data[sid]
        elif now - s.get("updated", 0) > STALE_SECONDS:
            del data[sid]
        elif s.get("state") != "ended" and not _alive(s.get("claude_pid")):
            s["state"] = "ended"
            s["updated"] = now


def update(session_id, **fields):
    if not session_id:
        return
    with _locked() as box:
        data = box["data"]
        s = data.setdefault(session_id, {"session_id": session_id, "started": time.time()})
        for k, v in fields.items():
            if v is not None:
                s[k] = v
        s["updated"] = time.time()
        _prune(data)


def replace_same_process(session_id, claude_pid):
    """/clear or /resume starts a new session id in the same Claude process: retire the old
    entry and carry its spoken name over."""
    if not claude_pid:
        return
    with _locked() as box:
        data = box["data"]
        new = data.get(session_id)
        for sid, s in data.items():
            if sid != session_id and s.get("claude_pid") == claude_pid and s.get("state") != "ended":
                s["state"] = "ended"
                s["updated"] = time.time()
                if new is not None and s.get("alias") and not new.get("alias"):
                    new["alias"] = s["alias"]


def set_alias(session_id, alias):
    update(session_id, alias=alias)


def sessions(include_ended=False):
    """Live sessions with speakable unique names and stable voices, oldest first."""
    with _locked() as box:
        _prune(box["data"])
        items = sorted(box["data"].values(), key=lambda s: s.get("started", 0))
    live = [dict(s) for s in items if include_ended or s.get("state") != "ended"]
    counts, seen = {}, {}
    for s in live:
        base = s.get("alias") or s.get("label") or s.get("project") or "session"
        counts[base] = counts.get(base, 0) + 1
    for s in live:
        base = s.get("alias") or s.get("label") or s.get("project") or "session"
        seen[base] = seen.get(base, 0) + 1
        s["name"] = base if counts[base] == 1 or seen[base] == 1 else f"{base} {seen[base]}"
    pool = vk.load_config()["control"]["agent_voices"]   # [] = every agent uses your default voice
    for i, s in enumerate(live):
        s["voice"] = pool[i % len(pool)] if pool else None
    return live


def get(session_id):
    for s in sessions(include_ended=True):
        if s["session_id"] == session_id:
            return s
    return None


def find_claude_pid(start=None):
    """Walk up from the hook process to the `claude` process that ran it."""
    pid = start or os.getppid()
    for _ in range(6):
        try:
            out = subprocess.run(["ps", "-o", "ppid=,comm=", "-p", str(pid)], capture_output=True,
                                 text=True, timeout=2).stdout.strip()
            args = subprocess.run(["ps", "-o", "args=", "-p", str(pid)], capture_output=True,
                                  text=True, timeout=2).stdout.strip()
        except Exception:
            return None
        if not out:
            return None
        ppid, comm = out.split(None, 1)
        # native install: the process is `claude`; npm install: `node …/claude-code/cli.js` or `node …/bin/claude`
        if os.path.basename(comm).startswith("claude") or \
                re.search(r"(^|/)claude(\s|$)|@anthropic-ai/claude-code", args):
            return pid
        pid = int(ppid)
    return None


def tty_of(pid):
    try:
        t = subprocess.run(["ps", "-o", "tty=", "-p", str(pid)], capture_output=True, text=True,
                           timeout=2).stdout.strip()
        return None if t in ("", "??") else "/dev/" + t
    except Exception:
        return None


def terminal_info(claude_pid):
    return {"program": os.environ.get("TERM_PROGRAM"),
            "app_bundle": os.environ.get("__CFBundleIdentifier"),
            "herdr_pane": os.environ.get("HERDR_PANE_ID"),
            "tty": tty_of(claude_pid) if claude_pid else None}
