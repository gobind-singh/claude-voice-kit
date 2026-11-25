#!/usr/bin/env python3
"""kokoro-voice daemon: keeps the Kokoro TTS model loaded and speaks text on request.

Standalone. Knows nothing about any particular client. Talk to it with the
`kokoro` command, or send one JSON line to the Unix socket and read one JSON line back:

  {"cmd": "speak", "text": "...", "voice": "af_heart", "speed": 1.0,
   "urgent": false, "interrupt": false, "clean": true, "tag": "optional-label"}
  {"cmd": "synth", "text": "...", "out": "/path/file.wav"}   -> waits until written
  {"cmd": "stop"} | {"cmd": "next"} | {"cmd": "replay", "n": 1} | {"cmd": "status"} | {"cmd": "voices"}
  {"cmd": "held"} | {"cmd": "play_held", "id": "all"} | {"cmd": "drop_held", "id": "all"}

"polite": true means: if another app is playing or recording audio when the message is about to be
spoken, hold it (held.json) and run "notify_command" instead (see audio_activity.py).

"clean" (default) turns markdown into listenable speech: headings become sections (with a
short pause), table rows are read as "column: value", code blocks are announced and
skipped, paths are shortened to the file name, URLs become "link". "next" skips to the
start of the next section (a heading, or the next message).

Threads: the main thread owns the MLX model (MLX is not thread-safe), a server thread
accepts socket connections, and a player thread plays the audio with `afplay`.
"""
import itertools, json, os, queue, re, signal, socket, subprocess, sys, tempfile
import threading, time
from collections import deque

STATE_DIR = os.path.expanduser("~/.local/state/kokoro-voice")
SOCK = os.path.join(STATE_DIR, "voiced.sock")
CONFIG = os.path.expanduser("~/.config/kokoro-voice/config.json")
MODEL_ID = "mlx-community/Kokoro-82M-bf16"
DEFAULTS = {"voice": "af_heart", "speed": 1.0, "idle_unload_minutes": 10, "idle_exit_minutes": 20,
            # "polite" messages (sent with --polite) are held instead of spoken while another app is
            # playing or recording audio: "hold" (default) or "play" (always speak).
            "when_other_audio": "hold",
            "ignore_processes": [r"\bcoreaudiod\b"],   # command-line patterns that don't count as "other audio"
            # apps that keep a silent output channel open all the time: their output is ignored,
            # their microphone use still counts (so dictation isn't talked over)
            "ignore_output_processes": [r"\bsystemsoundserverd\b"],   # e.g. [r"SomeApp"]; see `kokoro --audio-check`
            # an app that only has output open counts only if it's louder than this (dBFS), measured for
            # level_check_ms with the audio-level helper; null = every open channel counts
            "audible_threshold_db": -50,
            "level_check_ms": 250,
            "held_expire_minutes": 30,
            "notify_command": []}                  # run with one arg: base64 JSON of a held message
HISTORY_FILE = os.path.join(STATE_DIR, "history.json")
HELD_FILE = os.path.join(STATE_DIR, "held.json")
HELD_MAX = 20

gen_q = queue.PriorityQueue()   # (priority, seq, job)
play_q = queue.Queue()          # (epoch, wav_path, is_section_start, tag)
seq = itertools.count()
epoch = 0                       # bumped by stop: anything older is dropped
lock = threading.Lock()
current_proc = None
current_tag = None
speaking = False
skipping = False                # set by "next": drop audio until the next section start
history = deque(maxlen=10)
model = None
ready = threading.Event()
TMP = tempfile.mkdtemp(prefix="kokoro-voice-")
import atexit, shutil as _shutil
atexit.register(lambda: _shutil.rmtree(TMP, ignore_errors=True))


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, file=sys.stderr, flush=True)


def config():
    cfg = dict(DEFAULTS)
    try:
        cfg.update(json.load(open(CONFIG)))
    except Exception:
        pass
    return cfg


SYMBOLS = {"⌃": " Control ", "⌥": " Option ", "⌘": " Command ", "⇧": " Shift ",
           "✅": " yes ", "❌": " no ", "⚠️": " partly ", "⚠": " partly ", "★": " new ",
           "→": " to ", "►": " to ", "▶": " to ", "←": " from ", "↔": " and ", "≈": " about ",
           "×": " times ", "&": " and ", "–": ", ", "—": ", "}
PATH_RE = re.compile(r"(?<![\w/])(?:~|\.{1,2})?(?:/[\w.@+\-]+){2,}/?")
EMOJI_RE = re.compile("[\U0001F000-\U0001FAFF☀-➿─-▟️]")


def clean_inline(t):
    t = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", t)            # links / images
    t = re.sub(r"https?://\S+", "link", t)
    t = PATH_RE.sub(lambda m: os.path.basename(m.group(0).rstrip("/")) or m.group(0), t)
    for k, v in SYMBOLS.items():
        t = t.replace(k, v)
    t = EMOJI_RE.sub(" ", t)
    t = re.sub(r"#(\d)", r"number \1", t)                      # "#0" -> "number 0"
    t = re.sub(r"<([^<>]{1,40})>", r"\1", t)                     # "<project>" -> "project"
    t = re.sub(r"[*_`#<>|~]", "", t)
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"\(\s+", "(", re.sub(r"\s+\)", ")", t))
    return t.strip(" ,")


def to_blocks(text, clean=True):
    """Split text into speakable blocks: [(text, is_section_start)]."""
    if not clean:
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        return [(l, i == 0) for i, l in enumerate(lines)]
    text = re.sub(r"```.*?```", "\nCode block skipped.\n", text, flags=re.S)
    blocks, header = [], None
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("|"):                                   # table row
            cells = [c.strip() for c in line.strip("|").split("|")]
            if all(re.fullmatch(r":?-{2,}:?", c) or not c for c in cells):
                continue
            if header is None:
                header = [clean_inline(c) for c in cells]
                continue
            pairs = []
            for h, v in zip(header, cells):
                v = clean_inline(v)
                if v:
                    pairs.append(f"{h}: {v}" if h else v)
            if pairs:
                blocks.append((", ".join(pairs) + ".", False))
            continue
        header = None
        if not line or re.fullmatch(r"[-*_=]{3,}", line):
            continue
        m = re.match(r"#{1,6}\s+(.*)", line)
        if m:
            t = clean_inline(m.group(1))
            if t:
                blocks.append((t.rstrip(".:") + ".", True))
            continue
        line = re.sub(r"^[-*+]\s+", "", line)                      # bullets
        t = clean_inline(line)
        if t:
            blocks.append((t, False))
    if blocks:
        blocks[0] = (blocks[0][0], True)                           # each message starts a section
    return blocks


def clean_text(s):
    return "\n".join(t for t, _ in to_blocks(s))


def stop_all():
    global epoch, current_proc, skipping
    with lock:
        epoch += 1
        skipping = False
        p = current_proc
    while True:
        try:
            item = play_q.get_nowait()
        except queue.Empty:
            break
        try:
            os.unlink(item[1])                 # drop the generated wav of skipped speech
        except (OSError, IndexError, TypeError):
            pass
    if p and p.poll() is None:
        p.terminate()


# ---------- player thread ----------
def skip_to_next_section():
    """Stop the current audio and drop everything up to the next section start."""
    global skipping
    with lock:
        skipping = True
        p = current_proc
    if p and p.poll() is None:
        p.terminate()


def player():
    global current_proc, current_tag, speaking, skipping
    while True:
        ep, wav, section, tag = play_q.get()
        try:
            with lock:
                if ep != epoch:
                    continue
                if skipping:
                    if not section:
                        continue
                    skipping = False
                    log("skipped to next section")
                speaking = True
                current_tag = tag
                current_proc = subprocess.Popen(["afplay", wav])
                p = current_proc
            p.wait()
        except Exception as e:
            log("play error:", e)
        finally:
            with lock:
                current_proc = None
                speaking = not play_q.empty()
                if not speaking:
                    current_tag = None
            try:
                os.unlink(wav)
            except OSError:
                pass


# ---------- model work (main thread only) ----------
def synth_segments(text, voice, speed):
    import numpy as np
    lang = voice[0] if voice[:1] in ("a", "b") else "a"
    for r in model.generate(text=text, voice=voice, speed=speed, lang_code=lang):
        yield np.array(r.audio)


def do_speak(job):
    import numpy as np, soundfile as sf
    my_epoch = job["epoch"]
    pause = np.zeros(int(model.sample_rate * 0.35), dtype=np.float32)
    for text, section in job["blocks"]:
        for i, audio in enumerate(synth_segments(text, job["voice"], job["speed"])):
            if my_epoch != epoch:
                return
            if section and i == 0 and len(text) < 120:   # heading: short pause after it
                audio = np.concatenate([audio.astype(np.float32), pause])
            path = os.path.join(TMP, f"{next(seq)}.wav")
            sf.write(path, audio, model.sample_rate)
            play_q.put((my_epoch, path, section and i == 0, job.get("tag")))


def do_synth(job):
    import numpy as np, soundfile as sf
    try:
        text = "\n".join(t for t, _ in job["blocks"])
        parts = list(synth_segments(text, job["voice"], job["speed"]))
        sf.write(job["out"], np.concatenate(parts), model.sample_rate)
        job["result"] = {"ok": True, "out": job["out"]}
    except Exception as e:
        job["result"] = {"ok": False, "error": str(e)}
    job["done"].set()


def short_espeak_path():
    """espeak-ng (used by misaki for words not in its dictionary) fails when its data folder's path is
    longer than ~160 characters, e.g. when the kit lives in a deep folder. It resolves symlinks, so keep a
    small copy (~19 MB) at a short path instead."""
    try:
        import espeakng_loader
    except ImportError:
        return
    real = espeakng_loader.get_data_path()
    if len(real) < 120:
        return
    short = os.path.join(STATE_DIR, "espeak-ng-data")
    try:
        import shutil
        stamp = os.path.join(short, ".source")
        if not (os.path.isdir(short) and os.path.exists(stamp) and open(stamp).read() == real):
            if os.path.islink(short) or os.path.isfile(short):
                os.remove(short)
            shutil.rmtree(short, ignore_errors=True)
            shutil.copytree(real, short)
            with open(stamp, "w") as f:
                f.write(real)
        espeakng_loader.get_data_path = lambda: short
        log("espeak data copied to a short path:", len(real), "->", len(short), "chars")
    except OSError as e:
        log("could not shorten espeak path:", e)


def ensure_model():
    global model
    if model is not None:
        return
    short_espeak_path()
    from mlx_audio.tts.utils import load_model
    t = time.time()
    model = load_model(MODEL_ID)
    list(synth_segments("Ready.", DEFAULTS["voice"], 1.0))   # warm up G2P + kernels
    ready.set()
    log(f"model loaded in {time.time() - t:.1f}s")


def unload_model():
    """Free the model's memory after a quiet spell; it reloads (~3 s) on next use."""
    global model
    import gc
    import mlx.core as mx
    model = None
    ready.clear()
    gc.collect()
    try:
        mx.clear_cache()
    except AttributeError:
        mx.metal.clear_cache()
    log("model unloaded (idle)")


# ---------- held messages (not spoken because other audio was playing) ----------
held_lock = threading.Lock()


def held_load():
    try:
        items = json.load(open(HELD_FILE))
    except Exception:
        items = []
    ttl = float(config().get("held_expire_minutes", 30)) * 60
    return [h for h in items if time.time() - h.get("created", 0) < ttl]


def held_save(items):
    tmp = HELD_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(items[-HELD_MAX:], f)
    os.replace(tmp, HELD_FILE)


def other_audio(cfg, report=None):
    """Apps other than this service (and its afplay children) audibly using audio, or [] / None."""
    try:
        import audio_activity
        return audio_activity.other_audio_active(ignore_pids={os.getpid()},
                                                 ignore_patterns=cfg.get("ignore_processes", []),
                                                 ignore_output_patterns=cfg.get("ignore_output_processes", []),
                                                 audible_db=cfg.get("audible_threshold_db", -50),
                                                 level_ms=cfg.get("level_check_ms", 250), report=report)
    except Exception as e:
        log("audio check failed:", e)
        return None


def hold(job, apps):
    import audio_activity, base64
    item = {"id": f"{int(time.time() * 1000)}", "text": job["raw"], "voice": job["voice"],
            "speed": job["speed"], "tag": job.get("tag"), "actions": job.get("actions") or [],
            "why": audio_activity.describe(apps), "created": time.time()}
    with held_lock:
        items = held_load()
        items.append(item)
        held_save(items)
    log("held (other audio):", item["why"], "|", item["text"][:60])
    cmd = config().get("notify_command") or []
    payload = base64.b64encode(json.dumps(item).encode()).decode()
    try:
        if cmd:
            subprocess.Popen([*cmd, payload], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return
    except Exception as e:
        log("notify failed:", e)
    body = json.dumps(item["text"][:200])
    title = json.dumps("Held: " + item["why"])        # quoted for AppleScript
    subprocess.Popen(["osascript", "-e", f"display notification {body} with title {title}"],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def take_held(which):
    """Remove and return held messages: an id, or "all"."""
    with held_lock:
        items = held_load()
        picked = items if which == "all" else [h for h in items if h["id"] == which]
        held_save([h for h in items if h not in picked])
    return picked


def model_loop():
    ensure_model()
    last_used = time.time()
    while True:
        cfg = config()
        unload_min = float(cfg.get("idle_unload_minutes", 10))  # 0 = never unload model
        exit_min = float(cfg.get("idle_exit_minutes", 20))      # 0 = never quit service
        try:
            _, _, job = gen_q.get(timeout=30)
        except queue.Empty:
            idle = time.time() - last_used
            busy = speaking or not play_q.empty()
            if not busy and exit_min > 0 and idle > exit_min * 60:
                # Quit fully (0 MB). launchd won't restart a clean exit; the `kokoro`
                # command starts the service again on the next request.
                log("service exiting (idle)")
                try:
                    os.unlink(SOCK)
                except OSError:
                    pass
                _shutil.rmtree(TMP, ignore_errors=True)   # os._exit skips atexit
                os._exit(0)
            if model is not None and not busy and unload_min > 0 and idle > unload_min * 60:
                unload_model()
            continue
        last_used = time.time()
        try:
            if job["kind"] == "speak" and job.get("polite") and config().get("when_other_audio") == "hold":
                apps = other_audio(config())
                if apps:                       # someone else is using audio: don't talk over it
                    hold(job, apps)
                    continue
            ensure_model()
            (do_synth if job["kind"] == "synth" else do_speak)(job)
        except Exception as e:
            log("generate error:", e)
            if job.get("done"):
                job["result"] = {"ok": False, "error": str(e)}
                job["done"].set()


# ---------- socket server ----------
def voices():
    from huggingface_hub import snapshot_download
    d = os.path.join(snapshot_download(MODEL_ID, local_files_only=True), "voices")
    return sorted(f[:-12] for f in os.listdir(d) if f.endswith(".safetensors"))


def handle(req):
    cmd = req.get("cmd", "speak")
    cfg = config()
    if cmd == "status":
        return {"ok": True, "ready": True, "model_loaded": model is not None,
                "speaking": speaking, "tag": current_tag,
                "queued": gen_q.qsize() + play_q.qsize(), "config": cfg,
                "history": list(history)}
    if cmd == "stop":
        stop_all()
        return {"ok": True}
    if cmd == "audio_check":
        import audio_activity
        report = {}
        apps = other_audio(config(), report)
        return {"ok": True, "apps": apps, "supported": apps is not None, "silent": report.get("silent", []),
                "level_db": report.get("level_db"), "level_check": audio_activity.level_permission()}
    if cmd == "held":
        return {"ok": True, "held": held_load()}
    if cmd in ("play_held", "drop_held"):
        picked = take_held(req.get("id") or "all")
        if cmd == "play_held":
            for h in picked:
                b = to_blocks(h["text"], True)
                if b:
                    gen_q.put((1, next(seq), {"kind": "speak", "blocks": b, "raw": h["text"], "voice": h["voice"],
                                              "speed": h["speed"], "tag": h.get("tag"), "epoch": epoch}))
        return {"ok": True, "count": len(picked)}
    if cmd == "next":
        skip_to_next_section()
        return {"ok": True}
    if cmd == "voices":
        return {"ok": True, "voices": voices()}
    if cmd == "replay":
        n = int(req.get("n", 1))
        if len(history) < n:
            return {"ok": False, "error": "nothing to replay"}
        req = dict(history[-n], cmd="speak", interrupt=True, _replay=True)
        req.setdefault("clean", True)
        cmd = "speak"
    if cmd in ("speak", "synth"):
        raw = req.get("text", "")
        clean = req.get("clean", True)
        blocks = to_blocks(raw, clean)
        if not blocks:
            return {"ok": False, "error": "empty text"}
        voice = req.get("voice") or cfg["voice"]
        speed = float(req.get("speed") or cfg["speed"])
        job = {"kind": cmd, "blocks": blocks, "voice": voice, "speed": speed, "tag": req.get("tag"),
               "raw": raw, "polite": bool(req.get("polite")), "actions": req.get("actions") or []}
        if cmd == "synth":
            job.update(out=os.path.abspath(req["out"]), done=threading.Event())
            gen_q.put((0, next(seq), job))
            job["done"].wait(300)
            return job.get("result", {"ok": False, "error": "timeout"})
        if req.get("interrupt"):
            stop_all()
        job["epoch"] = epoch
        if not req.get("_replay"):
            history.append({"text": raw, "clean": clean, "voice": voice, "speed": speed,
                            "tag": req.get("tag")})
            try:  # persist so replay still works after the service quits when idle
                json.dump(list(history), open(HISTORY_FILE, "w"))
            except OSError:
                pass
        gen_q.put((0 if req.get("urgent") else 1, next(seq), job))
        return {"ok": True, "queued": True}
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
            resp = {"ok": False, "error": str(e)}
        try:
            conn.sendall((json.dumps(resp) + "\n").encode())
        except OSError:
            pass


def server():
    os.makedirs(STATE_DIR, exist_ok=True)
    if os.path.exists(SOCK):
        os.unlink(SOCK)
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.bind(SOCK)
    os.chmod(SOCK, 0o600)
    s.listen(16)
    log("listening on", SOCK)
    while True:
        conn, _ = s.accept()
        threading.Thread(target=serve_conn, args=(conn,), daemon=True).start()


def main():
    signal.signal(signal.SIGTERM, lambda *a: (stop_all(), _shutil.rmtree(TMP, ignore_errors=True), os._exit(0)))
    try:
        history.extend(json.load(open(HISTORY_FILE))[-history.maxlen:])
    except Exception:
        pass
    threading.Thread(target=player, daemon=True).start()
    threading.Thread(target=server, daemon=True).start()
    model_loop()


if __name__ == "__main__":
    main()
