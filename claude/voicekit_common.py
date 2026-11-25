"""Shared paths, settings and helpers for the Claude layer of claude-voice-kit.

Everything user-specific lives outside the project folder:
  config:  ~/.config/claude-voice-kit/config.json   (settings; created with defaults)
  state:   ~/.local/state/claude-voice-kit/          (replies, mute flag, runtime files)
Override with VOICEKIT_CONFIG_DIR / VOICEKIT_STATE_DIR.
"""
import copy, json, os, shutil, subprocess

HOME = os.path.expanduser("~")
KIT_DIR = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
CONFIG_DIR = os.environ.get("VOICEKIT_CONFIG_DIR", os.path.join(HOME, ".config", "claude-voice-kit"))
STATE_DIR = os.environ.get("VOICEKIT_STATE_DIR", os.path.join(HOME, ".local", "state", "claude-voice-kit"))
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
REPLIES_FILE = os.path.join(STATE_DIR, "replies.json")
MUTED_FLAG = os.path.join(STATE_DIR, "muted")
LATEST_FILE = os.path.join(STATE_DIR, "speak-latest")
HANDSFREE_FLAG = os.path.join(STATE_DIR, "handsfree")
SESSIONS_FILE = os.path.join(STATE_DIR, "sessions.json")
PENDING_DIR = os.path.join(STATE_DIR, "pending")          # approvals waiting for a spoken answer
CONTEXT_FILE = os.path.join(STATE_DIR, "context.json")    # "it" = last agent, pending confirmation
AUDIT_LOG = os.path.join(STATE_DIR, "audit.log")
CHANNEL_DIR = os.path.join(STATE_DIR, "channels")         # one socket per channel-enabled session
KOKORO = os.path.join(KIT_DIR, "packages", "kokoro-voice", "kokoro")
LISTEN = os.path.join(KIT_DIR, "packages", "listen-voice", "listen")

DEFAULTS = {
    "alerts": {"permission": True, "question": True, "idle": False},
    "summary": {"model": "haiku", "short_reply_chars": 250, "speak_project_name": True},
    "full_read": {"keep_replies": 10},
    # Hammerspoon push-to-talk: key = right_cmd | right_option | right_shift | right_ctrl; listening starts after the
    # key is held alone for hold_ms, so quick shortcuts (Right ⌘ + Delete) never trigger it; cue_sound "" = silent
    "push_to_talk": {"key": "right_cmd", "hold_ms": 300, "cue_sound": "Tink"},
    "control": {
        "approval_timeout_seconds": 20,     # hands-free: wait this long for a spoken answer
        "confirm_risky": True,              # risky commands need "yes, approve"
        "risky_patterns": [r"\brm\b", r"\bgit\s+push\b", r"\bsudo\b", r"\bdeploy", r"\bdelete\b",
                           r"\bdrop\s+(table|database)\b", r"--force\b", r"\bkubectl\s+(delete|apply)\b",
                           r"\bterraform\s+(apply|destroy)\b", r"\bnpm\s+publish\b"],
        "confirm_broadcast": True,          # "tell everyone…" asks first
        "confirm_stop_agent": True,         # "stop builder" asks first
        # [] = every agent uses your default kokoro voice. To give each agent its own voice, list some,
        # e.g. ["af_heart", "am_michael", "bf_emma", "af_bella", "bm_george"] (avoid af_nicole: it whispers).
        "agent_voices": [],
        "ai_router": True,                  # Haiku interprets phrases the rules don't understand
        "wake_words": ["hey claude", "okay claude", "claude"],
    },
    # Read by hammerspoon/voice-kit.lua: hud = custom pop-up (false: plain hs.alert); menubar = menu bar icon;
    # held = "quiet" (count + list in the menu bar icon) or "notification" (also a macOS notification with buttons)
    "ui": {"hud": True, "menubar": True, "held": "quiet"},
}


def _merge(base, over):
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def load_config():
    try:
        with open(CONFIG_FILE) as f:
            return _merge(DEFAULTS, json.load(f))
    except Exception:
        return copy.deepcopy(DEFAULTS)


def save_config(cfg):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    tmp = CONFIG_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(cfg, f, indent=2)
    os.replace(tmp, CONFIG_FILE)


def ensure_dirs():
    os.makedirs(CONFIG_DIR, exist_ok=True)
    os.makedirs(STATE_DIR, exist_ok=True)


def is_muted():
    return os.path.exists(MUTED_FLAG)


def set_muted(muted):
    ensure_dirs()
    if muted:
        open(MUTED_FLAG, "w").close()
    elif os.path.exists(MUTED_FLAG):
        os.remove(MUTED_FLAG)


def handsfree():
    return os.path.exists(HANDSFREE_FLAG)


def set_handsfree(on):
    ensure_dirs()
    if on:
        open(HANDSFREE_FLAG, "w").close()
    elif os.path.exists(HANDSFREE_FLAG):
        os.remove(HANDSFREE_FLAG)


def audit(event, **fields):
    import time
    ensure_dirs()
    try:
        with open(AUDIT_LOG, "a") as f:
            f.write(json.dumps({"time": time.strftime("%Y-%m-%d %H:%M:%S"), "event": event, **fields}) + "\n")
    except OSError:
        pass


def claude_bin():
    return shutil.which("claude") or os.path.join(HOME, ".local", "bin", "claude")


def project_name(cwd):
    name = os.path.basename((cwd or "").rstrip("/"))
    return "home folder" if name == os.path.basename(HOME) else name


def kokoro(*args, text=None, timeout=20):
    """Run the kokoro command; returns True on success."""
    try:
        r = subprocess.run([KOKORO, *args], input=text, text=True, timeout=timeout,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return r.returncode == 0
    except Exception:
        return False


def speak(text, urgent=False, voice=None, interrupt=False, polite=False, actions=None):
    """Queue speech on the Kokoro service; fall back to macOS `say`.
    polite=True: automatic messages (briefings, alerts, approval questions). If another app is playing
    or recording audio, kokoro holds the message and shows a notification instead of talking over it.
    actions: notification buttons for a held message, e.g. [{"label": "Approve", "command": [...]}]."""
    args = (["-u"] if urgent else []) + (["-i"] if interrupt else []) + (["--voice", voice] if voice else [])
    if polite:
        args += ["--polite"] + (["--actions-json", json.dumps(actions)] if actions else [])
    if kokoro(*args, "--", text):
        return
    if polite:   # voice service down: never talk over other audio, just notify
        subprocess.Popen(["osascript", "-e", f"display notification {json.dumps(text[:200])} with title \"Claude\""],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return
    subprocess.Popen(["say", "-r", "190", text], start_new_session=True,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
