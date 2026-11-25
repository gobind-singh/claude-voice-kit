#!/usr/bin/env python3
"""Which apps are using audio right now (playing sound or recording)? macOS 14.2+.

Uses CoreAudio's per-process list (kAudioHardwarePropertyProcessObjectList) through ctypes. That list
says which apps have an audio channel *open*, not whether they make sound: a Discord tab in Safari or a
dictation app keeps output open in silence. So apps that only have output open are also measured with the
small `audio-level` helper (audio_level.swift, built by the installer), which reports how loud they really
are. Without the helper or its permission, every open channel counts, as before.
Used by voiced to avoid talking over music, videos and calls.

  python3 audio_activity.py          print apps using audio as JSON
"""
import ctypes, ctypes.util, json, os, re, subprocess, sys


def _fourcc(s):
    return int.from_bytes(s.encode(), "big")


class _Addr(ctypes.Structure):
    _fields_ = [("mSelector", ctypes.c_uint32), ("mScope", ctypes.c_uint32), ("mElement", ctypes.c_uint32)]


_CA = None
SYSTEM_OBJECT = 1
GLOBAL, MAIN = _fourcc("glob"), 0
PROCESS_LIST, PID, BUNDLE = _fourcc("prs#"), _fourcc("ppid"), _fourcc("pbid")
RUNNING_IN, RUNNING_OUT = _fourcc("piri"), _fourcc("piro")


def _lib():
    global _CA
    if _CA is None:
        _CA = ctypes.CDLL(ctypes.util.find_library("CoreAudio"))
        _CA.AudioObjectGetPropertyDataSize.argtypes = [ctypes.c_uint32, ctypes.POINTER(_Addr), ctypes.c_uint32,
                                                       ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)]
        _CA.AudioObjectGetPropertyData.argtypes = [ctypes.c_uint32, ctypes.POINTER(_Addr), ctypes.c_uint32,
                                                   ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32), ctypes.c_void_p]
    return _CA


def _get_u32(obj, sel):
    ca, a = _lib(), _Addr(sel, GLOBAL, MAIN)
    v, size = ctypes.c_uint32(0), ctypes.c_uint32(4)
    if ca.AudioObjectGetPropertyData(obj, ctypes.byref(a), 0, None, ctypes.byref(size), ctypes.byref(v)) != 0:
        raise OSError(f"CoreAudio property {sel} failed")
    return v.value


def _get_i32(obj, sel):
    v = _get_u32(obj, sel)
    return v - (1 << 32) if v >= (1 << 31) else v


def processes():
    """All processes CoreAudio knows about: [{pid, output, input}]. Raises OSError if unsupported."""
    ca, a = _lib(), _Addr(PROCESS_LIST, GLOBAL, MAIN)
    size = ctypes.c_uint32(0)
    if ca.AudioObjectGetPropertyDataSize(SYSTEM_OBJECT, ctypes.byref(a), 0, None, ctypes.byref(size)) != 0:
        raise OSError("process list not supported (macOS 14.2+ needed)")
    n = size.value // 4
    ids = (ctypes.c_uint32 * n)()
    if n and ca.AudioObjectGetPropertyData(SYSTEM_OBJECT, ctypes.byref(a), 0, None, ctypes.byref(size), ids) != 0:
        raise OSError("process list read failed")
    out = []
    for obj in ids:
        try:
            out.append({"pid": _get_i32(obj, PID), "output": bool(_get_u32(obj, RUNNING_OUT)),
                        "input": bool(_get_u32(obj, RUNNING_IN))})
        except OSError:
            continue
    return out


def _command(pid):
    try:
        return subprocess.run(["ps", "-o", "command=", "-p", str(pid)], capture_output=True, text=True,
                              timeout=2).stdout.strip()
    except Exception:
        return ""


def _name(cmd):
    m = re.search(r"/([^/]+)\.app/", cmd)
    return m.group(1) if m else os.path.basename(cmd.split()[0]) if cmd else "?"


def _ancestors(pid):
    seen = set()
    for _ in range(8):
        seen.add(pid)
        try:
            pp = int(subprocess.run(["ps", "-o", "ppid=", "-p", str(pid)], capture_output=True, text=True,
                                    timeout=2).stdout.strip() or 0)
        except Exception:
            break
        if pp <= 1:
            break
        pid = pp
    return seen


LEVEL_HELPER = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".build", "audio-level")


def output_level(pids, ms=250):
    """Peak level (dBFS, -120 = silence) of these processes' combined output over `ms`, or None if it
    can't be measured (helper not built, no permission, error)."""
    if not pids or not os.access(LEVEL_HELPER, os.X_OK):
        return None
    try:
        r = subprocess.run([LEVEL_HELPER, ",".join(str(p) for p in pids), str(int(ms))], capture_output=True,
                           text=True, timeout=5)
        d = json.loads(r.stdout or "{}")
    except Exception:
        return None
    return float(d["peak_db"]) if d.get("ok") and "peak_db" in d else None


def level_permission():
    """'granted' / 'denied' / 'unknown' for the helper's System Audio Recording permission, or 'missing'."""
    if not os.access(LEVEL_HELPER, os.X_OK):
        return "missing"
    try:
        r = subprocess.run([LEVEL_HELPER, "--status"], capture_output=True, text=True, timeout=5)
        return json.loads(r.stdout).get("permission", "unknown")
    except Exception:
        return "unknown"


def other_audio_active(ignore_pids=(), ignore_patterns=(), ignore_output_patterns=(), audible_db=None,
                       level_ms=250, report=None):
    """Apps (other than ignored ones) currently playing or recording audio.
    ignore_output_patterns: apps that keep a silent output channel open all the time (some dictation and chat apps do);
    their output is ignored but their microphone use still counts.
    audible_db: if set, apps that only have *output* open are measured, and they count only if their output
    is louder than this (dBFS). Microphone use always counts. If measuring fails, they count.
    report: optional dict, filled with {"level_db", "silent": [apps with output open but silent]}.
    Returns [{pid, name, output, input}], or None if this macOS can't tell."""
    try:
        procs = [p for p in processes() if p["output"] or p["input"]]
    except OSError:
        return None
    ignore_pids = set(ignore_pids)
    found = []
    for p in procs:
        if p["pid"] in ignore_pids or p["pid"] == os.getpid():
            continue
        cmd = _command(p["pid"])
        if any(re.search(pat, cmd) for pat in ignore_patterns):
            continue
        if p["output"] and any(re.search(pat, cmd) for pat in ignore_output_patterns):
            p = {**p, "output": False}
            if not p["input"]:
                continue
        # a child of an ignored process (e.g. our afplay) is ignored too
        if ignore_pids and _ancestors(p["pid"]) & ignore_pids:
            continue
        found.append({**p, "name": _name(cmd)})
    if audible_db is not None:
        out_only = [p for p in found if p["output"] and not p["input"]]
        level = output_level([p["pid"] for p in out_only], level_ms) if out_only else None
        if report is not None:
            report["level_db"] = level
        silent = []
        if level is not None and level < audible_db:          # open but silent: doesn't count
            silent = out_only
        elif level is not None and len(out_only) > 1:          # something is loud: find out which app
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(len(out_only)) as ex:
                levels = list(ex.map(lambda p: output_level([p["pid"]], level_ms), out_only))
            silent = [p for p, lv in zip(out_only, levels) if lv is not None and lv < audible_db]
            if len(silent) == len(out_only):                   # mixed loud but no single app is: keep all
                silent = []
        if report is not None:
            report["silent"] = silent
        found = [p for p in found if p not in silent]
    return found


def describe(apps):
    """'Music is playing' / 'zoom.us is using the microphone'."""
    if not apps:
        return ""
    a = apps[0]
    what = "is playing" if a["output"] and not a["input"] else "is using the microphone"
    more = f" (+{len(apps) - 1} more)" if len(apps) > 1 else ""
    return f"{a['name']} {what}{more}"


if __name__ == "__main__":
    r = other_audio_active()
    print(json.dumps(r, indent=2) if r is not None else '"unsupported"')
