#!/usr/bin/env python3
"""listen-voice daemon: push-to-talk recording + local speech-to-text (Parakeet via transcribe.cpp).

Standalone: nothing Claude-specific. Talk to it with the `listen-voice` command, or send one JSON
line to the Unix socket and read one JSON line back:
  {"cmd": "start"}                         begin recording from the microphone
  {"cmd": "stop", "raw": false}            stop, transcribe, return {"text", "raw", "seconds", "ms"}
  {"cmd": "cancel"}                        stop and discard
  {"cmd": "transcribe", "path": "a.wav"}   transcribe a file
  {"cmd": "status"}
  {"cmd": "wake", "on": true}              hands-free: listen continuously for the wake phrase

Wake mode: a simple voice-activity detector cuts speech into phrases. Each phrase is transcribed
locally; if it starts with a wake phrase ("hey claude …"), `wake.command` runs with the rest of the
phrase as its last argument. A phrase that is only a stop word ("stop", "quiet") runs
`wake.barge_in_command` (e.g. stop text-to-speech). Nothing leaves the Mac.

Model: reuses an existing Parakeet GGUF from the shared Hugging Face cache (e.g. the one the
Handy dictation app downloaded), so nothing is duplicated. Set "model_path" in the config to
point at any other GGUF that transcribe.cpp supports.

Microphone: the service never opens the mic itself. Each recording happens in a short-lived
`recorder.py` child process that exits when recording ends, so macOS always releases the mic and
its orange indicator, even if something goes wrong. One spare recorder waits ready, without the mic
open, so push-to-talk starts instantly.

The service is started on demand by the `listen-voice` command (no LaunchAgent), so macOS asks for
microphone access on behalf of whatever started it (Hammerspoon or your terminal). It frees the
model after `idle_unload_minutes` and quits after `idle_exit_minutes`.
"""
import json, os, queue, re, socket, subprocess, sys, threading, time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
from polish import polish  # noqa: E402

RECORDER = os.path.join(os.path.dirname(os.path.realpath(__file__)), "recorder.py")
STATE_DIR = os.path.expanduser("~/.local/state/listen-voice")
SOCK = os.path.join(STATE_DIR, "listend.sock")
CONFIG = os.path.expanduser("~/.config/listen-voice/config.json")
RATE = 16000
DEFAULTS = {
    "model_path": "",
    "model_repo": "handy-computer/parakeet-unified-en-0.6b-gguf",
    "model_file": "parakeet-unified-en-0.6b-Q8_0.gguf",
    "input_device": None,           # None = system default microphone
    "max_seconds": 60,
    "min_seconds": 0.3,
    "tail_ms": 150,                 # push-to-talk: keep recording this long after the key is released
    "silence_rms": 0.003,           # quieter than this is treated as "nothing said"
    "vocabulary": [],               # exact spellings to enforce, e.g. ["herdr", "Kokoro"]
    "aliases": {},                  # misheard -> right, e.g. {"harder": "herdr"}
    "idle_unload_minutes": 10,
    "idle_exit_minutes": 20,
    "wake": {
        "words": ["hey claude", "okay claude", "ok claude"],
        "command": [],                  # e.g. ["/path/to/voicectl"]; the phrase is appended
        "stop_words": ["stop", "quiet", "stop talking", "shut up", "be quiet", "silence"],
        "barge_in_command": [],         # e.g. ["/path/to/kokoro", "--stop"]
        "follow_up_seconds": 6,         # "hey claude" alone: the next phrase is the command
        # Echo guard: a command that exits 0 while your speakers are talking (e.g. ["kokoro",
        # "--is-speaking"]). Then only stop words count, so text-to-speech can't trigger commands.
        "busy_command": [],
        "chime": "/System/Library/Sounds/Tink.aiff",
    },
}

lock = threading.Lock()             # guards recording state
model_lock = threading.Lock()       # one transcription at a time
model = None
current = None                      # push-to-talk Recorder while the key is held
spare = None                        # pre-started Recorder, mic NOT open yet
wake_rec = None                     # Recorder for hands-free mode
wake_q = queue.Queue()
early_stop_at = 0.0                 # a "stop" that arrived before its "start" (quick key tap)
last_used = time.time()


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, file=sys.stderr, flush=True)


def config():
    cfg = json.loads(json.dumps(DEFAULTS))
    try:
        user = json.load(open(CONFIG))
        for k, v in user.items():
            cfg[k] = {**cfg[k], **v} if isinstance(v, dict) and isinstance(cfg.get(k), dict) else v
    except Exception:
        pass
    return cfg


def model_path(cfg, allow_download=False):
    if cfg["model_path"] and os.path.exists(os.path.expanduser(cfg["model_path"])):
        return os.path.expanduser(cfg["model_path"])
    import glob
    from huggingface_hub import hf_hub_download
    try:  # shared cache first (e.g. downloaded by Handy): no duplicate download
        return hf_hub_download(cfg["model_repo"], cfg["model_file"], local_files_only=True)
    except Exception:
        pass
    # Some apps (Handy) write the cache without a "main" ref, so also look in the snapshots directly.
    hub = os.environ.get("HF_HUB_CACHE") or os.path.join(
        os.environ.get("HF_HOME", os.path.expanduser("~/.cache/huggingface")), "hub")
    found = glob.glob(os.path.join(hub, "models--" + cfg["model_repo"].replace("/", "--"),
                                   "snapshots", "*", cfg["model_file"]))
    if found:
        return found[0]
    if not allow_download:
        raise FileNotFoundError(f"{cfg['model_repo']}/{cfg['model_file']} not in the local cache")
    return hf_hub_download(cfg["model_repo"], cfg["model_file"])


def ensure_model():
    global model
    if model is None:
        import transcribe_cpp
        t = time.time()
        model = transcribe_cpp.Model(model_path(config(), allow_download=True))
        log(f"model loaded in {time.time() - t:.2f}s")
    return model


def unload_model():
    global model
    with model_lock:
        if model is not None:
            try:
                model.close()
            except Exception:
                pass
            model = None
            log("model unloaded (idle)")


def transcribe(pcm, raw=False):
    cfg = config()
    t = time.time()
    with model_lock:
        m = ensure_model()
        with m.session() as s:
            text = s.run(np.ascontiguousarray(pcm, dtype=np.float32)).text or ""
    out = text if raw else polish(text, cfg["vocabulary"], cfg["aliases"])
    return {"ok": True, "text": out, "raw": text, "seconds": round(len(pcm) / RATE, 2),
            "ms": int((time.time() - t) * 1000)}


def load_wav(path):
    import soundfile as sf
    a, sr = sf.read(path, dtype="float32", always_2d=True)
    a = a.mean(axis=1)
    if sr != RATE:
        idx = np.linspace(0, len(a) - 1, int(len(a) * RATE / sr))
        a = np.interp(idx, np.arange(len(a)), a).astype(np.float32)
    return a


# ---------- recorder processes (the only place the microphone is opened) ----------
class Recorder:
    def __init__(self, max_seconds, on_block=None):
        self.on_block, self.blocks, self.started_at = on_block, [], 0.0
        self.live = threading.Event()                 # set when the first audio arrives (mic really on)
        self.proc = subprocess.Popen(
            [sys.executable, RECORDER, json.dumps(config()["input_device"]), str(max_seconds)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def _read(self):
        while True:
            data = self.proc.stdout.read(1920)        # 30 ms of float32 samples
            if not data:
                break
            arr = np.frombuffer(data[: len(data) - len(data) % 4], dtype=np.float32)
            if not self.live.is_set() and self.started_at:
                self.live_ms = int((time.time() - self.started_at) * 1000)
                self.live.set()
                if not self.on_block:
                    log(f"mic live {self.live_ms} ms after start")
            if self.on_block:
                self.on_block(arr)
            else:
                self.blocks.append(arr)

    def start(self):
        self.started_at = time.time()
        self.proc.stdin.write(b"start\n")
        self.proc.stdin.flush()

    def stop(self):
        try:
            self.proc.stdin.write(b"stop\n")
            self.proc.stdin.flush()
            self.proc.stdin.close()
        except (BrokenPipeError, OSError, ValueError):
            pass
        self.reader.join(3)                           # audio arrives before the mic is closed
        threading.Thread(target=self._reap, daemon=True).start()
        return np.concatenate(self.blocks) if self.blocks else np.zeros(0, dtype=np.float32)

    def _reap(self):
        try:
            self.proc.wait(3)
        except subprocess.TimeoutExpired:
            self.proc.kill()                          # process gone = microphone released

    def discard(self):                                # spare that was never started
        try:
            self.proc.stdin.close()
        except Exception:
            pass
        try:
            self.proc.wait(2)
        except subprocess.TimeoutExpired:
            self.proc.kill()


def _prepare_spare():
    global spare
    with lock:
        if spare is None or spare.proc.poll() is not None:
            spare = Recorder(config()["max_seconds"] + 2)


# ---------- push-to-talk ----------
def start_recording(wait_live=False):
    """Start push-to-talk recording. wait_live: return only once audio is actually arriving (up to 2 s),
    so the caller can show "Listening…" at the moment the microphone is really on."""
    global current, spare, early_stop_at
    with lock:
        if current is not None:
            r = current
        elif time.time() - early_stop_at < 3:            # its "stop" already came: don't open the mic
            early_stop_at = 0.0
            return {"ok": True, "cancelled": True}
        else:
            r = spare if spare is not None and spare.proc.poll() is None else Recorder(config()["max_seconds"] + 2)
            spare = None
            r.start()
            current = r
            threading.Thread(target=warm_model, daemon=True).start()   # load while the user is talking
    if not wait_live:
        return {"ok": True}
    live = r.live.wait(2.0)
    if current is not r:
        return {"ok": True, "cancelled": True}
    return {"ok": True, "live": live, "ms": getattr(r, "live_ms", None)}


def trim_recording():
    """Drop the audio recorded so far (e.g. our own voice, recorded before speech was stopped)."""
    with lock:
        if current is not None:
            current.blocks = []
    return {"ok": True}


def warm_model():
    with model_lock:
        try:
            ensure_model()
        except Exception as e:
            log("model load failed:", e)


def stop_recording(transcribe_it=True, raw=False):
    global current, early_stop_at
    with lock:
        r, current = current, None
        if r is None:
            early_stop_at = time.time()                # start may still be on its way: cancel it
            return {"ok": False, "error": "not recording"}
    if transcribe_it and config().get("tail_ms", 0) > 0:
        time.sleep(config()["tail_ms"] / 1000)         # don't clip the last word
    audio = r.stop()
    threading.Thread(target=_prepare_spare, daemon=True).start()
    if not transcribe_it:
        return {"ok": True, "cancelled": True}
    cfg = config()
    if len(audio) < cfg["min_seconds"] * RATE or float(np.sqrt(np.mean(audio ** 2))) < cfg["silence_rms"]:
        return {"ok": True, "text": "", "raw": "", "seconds": round(len(audio) / RATE, 2), "ms": 0,
                "note": "nothing heard"}
    return transcribe(audio, raw)


# ---------- wake mode (hands-free) ----------
def _norm(t):
    return re.sub(r"[^a-z0-9' ]", "", (t or "").lower()).strip()


def _make_vad():
    """Cut a stream of 30 ms blocks into spoken phrases (energy-based, adaptive noise floor)."""
    cfg = config()
    st = {"buf": [], "pre": [], "speech": 0, "silence": 0, "active": False, "floor": cfg["silence_rms"]}

    def feed(f):
        rms = float(np.sqrt(np.mean(f ** 2))) if len(f) else 0.0
        loud = rms > max(cfg["silence_rms"] * 2, st["floor"] * 3)
        if not st["active"]:
            if not loud:
                st["floor"] = 0.95 * st["floor"] + 0.05 * rms
            st["pre"] = (st["pre"] + [f])[-10:]           # 300 ms pre-roll
            st["speech"] = st["speech"] + 1 if loud else 0
            if st["speech"] >= 3:
                st.update(active=True, buf=list(st["pre"]), silence=0)
        else:
            st["buf"].append(f)
            st["silence"] = 0 if loud else st["silence"] + 1
            if st["silence"] >= 20 or sum(len(b) for b in st["buf"]) > RATE * 15:   # 600 ms pause / 15 s
                seg = np.concatenate(st["buf"])
                st.update(active=False, buf=[], pre=[], speech=0)
                if len(seg) > RATE * 0.4:
                    wake_q.put(seg)
    return feed


def wake_on():
    global wake_rec
    with lock:
        if wake_rec is not None and wake_rec.proc.poll() is None:
            return {"ok": True, "already": True}
        wake_rec = Recorder(0, on_block=_make_vad())
        wake_rec.start()
    log("wake mode on")
    return {"ok": True}


def wake_off():
    global wake_rec
    with lock:
        r, wake_rec = wake_rec, None
    if r:
        r.stop()
        log("wake mode off")
    return {"ok": True}


_follow = {"until": 0.0}


def handle_phrase(raw):
    """Decide what a phrase heard in wake mode means; runs the configured command.
    Returns ("barge_in" | "command" | "wake" | "ignored", text)."""
    cfg = config()
    w = cfg["wake"]
    n = _norm(raw)
    if not n:
        return "ignored", ""
    if n in [_norm(x) for x in w["stop_words"]]:
        if w["barge_in_command"]:
            subprocess.Popen(w["barge_in_command"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return "barge_in", n
    if w.get("busy_command"):
        try:
            if subprocess.run(w["busy_command"], capture_output=True, timeout=3).returncode == 0:
                _follow["until"] = 0.0
                return "ignored", raw          # our own speech coming back through the microphone
        except Exception:
            pass
    command = None
    for word in sorted(w["words"], key=len, reverse=True):
        if n == _norm(word) or n.startswith(_norm(word) + " "):
            rest = re.sub(rf"^\W*{re.escape(word)}\W*", "", raw, flags=re.I).strip()
            if not rest:                                   # "hey claude" alone: listen for the next phrase
                _follow["until"] = time.time() + w["follow_up_seconds"]
                if w.get("chime"):
                    subprocess.Popen(["afplay", w["chime"]])
                return "wake", ""
            command = rest
            break
    if command is None and time.time() < _follow["until"]:
        command = raw
    if not command:
        return "ignored", raw
    _follow["until"] = 0.0
    text = polish(command, cfg["vocabulary"], cfg["aliases"])
    log("wake command:", text)
    if w["command"]:
        subprocess.Popen([*w["command"], text], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return "command", text


def wake_worker():
    while True:
        seg = wake_q.get()
        if current is not None:             # push-to-talk in progress: ignore
            continue
        try:
            handle_phrase(transcribe(seg, raw=True)["raw"])
        except Exception as e:
            log("wake error:", e)


# ---------- server ----------
def handle(req):
    global last_used
    cmd = req.get("cmd")
    last_used = time.time()
    if cmd == "start":
        return start_recording(req.get("wait_live", False))
    if cmd == "trim":
        return trim_recording()
    if cmd == "stop":
        return stop_recording(True, req.get("raw", False))
    if cmd == "cancel":
        return stop_recording(False)
    if cmd == "transcribe":
        return transcribe(load_wav(req["path"]), req.get("raw", False))
    if cmd == "wake":
        return wake_on() if req.get("on", True) else wake_off()
    if cmd == "status":
        return {"ok": True, "recording": current is not None,
                "wake": wake_rec is not None and wake_rec.proc.poll() is None,
                "model_loaded": model is not None,
                "model": model_path(config()) if model is not None else None}
    return {"ok": False, "error": f"unknown cmd {cmd!r}"}


def serve_conn(conn):
    with conn:
        try:
            data = b""
            while not data.endswith(b"\n"):
                chunk = conn.recv(65536)
                if not chunk:
                    break
                data += chunk
            resp = handle(json.loads(data or b"{}"))
        except Exception as e:
            resp = {"ok": False, "error": f"{type(e).__name__}: {e}"}
        try:
            conn.sendall((json.dumps(resp) + "\n").encode())
        except OSError:
            pass


def idle_watch():
    global spare
    while True:
        time.sleep(10)
        cfg = config()
        idle = time.time() - last_used
        r = current
        if r is not None and time.time() - r.started_at > cfg["max_seconds"] + 5:
            log("closing a recording that was never stopped")
            stop_recording(transcribe_it=False)
        if current is not None or wake_rec is not None:
            continue
        if cfg["idle_exit_minutes"] > 0 and idle > cfg["idle_exit_minutes"] * 60:
            log("service exiting (idle)")
            if spare is not None:
                spare.discard()
            try:
                os.unlink(SOCK)
            except OSError:
                pass
            os._exit(0)
        if model is not None and cfg["idle_unload_minutes"] > 0 and idle > cfg["idle_unload_minutes"] * 60:
            unload_model()


def main():
    os.makedirs(STATE_DIR, exist_ok=True)
    if os.path.exists(SOCK):
        os.unlink(SOCK)
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.bind(SOCK)
    os.chmod(SOCK, 0o600)
    s.listen(16)
    threading.Thread(target=idle_watch, daemon=True).start()
    threading.Thread(target=wake_worker, daemon=True).start()
    threading.Thread(target=_prepare_spare, daemon=True).start()
    log("listening on", SOCK)
    while True:
        conn, _ = s.accept()
        threading.Thread(target=serve_conn, args=(conn,), daemon=True).start()


if __name__ == "__main__":
    main()
