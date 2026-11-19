#!/usr/bin/env python3
"""Stop hook: speak a short AI briefing of Claude's last reply.

- Saves the full reply (last N) so `cvoice full` / Control+Option+F can read all of it.
- Replies shorter than `summary.short_reply_chars` are spoken as they are.
- Longer replies: Claude Haiku (`claude -p`) writes a briefing of up to 3 sentences.
  If that fails, the reply's first paragraph is read.
- Runs in the background, so Claude is never blocked. A newer reply cancels a stale briefing.
"""
import json, os, re, subprocess, sys, time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
import voicekit_common as vk  # noqa: E402
import registry  # noqa: E402

BRIEF_PROMPT = """You brief a busy developer by voice. Below is a reply an AI coding \
assistant just gave them. Tell them, in plain spoken English, what it is about: \
the main point or result, and anything they must decide, answer or do next.
Rules: at most 3 short sentences, under 60 words. No markdown, lists, code, file \
paths or URLs. Speak to them as "you". Output only the briefing.

--- REPLY ---
"""


PLAN_PROMPT = """You brief a busy developer by voice. An AI coding assistant has written the plan \
below and is waiting for them to approve it. In plain spoken English, tell them: what the plan \
will do, its main steps, and anything risky or any decision they should think about.
Rules: at most 4 short sentences, under 80 words. No markdown, lists, code, file paths or URLs. \
Speak to them as "you". Do not ask for approval yourself. Output only the briefing.

--- PLAN ---
"""


def plan_brief(plan, model, timeout=45):
    """Spoken briefing of a plan waiting for approval (Haiku; first paragraph as a fallback)."""
    return ai_brief(plan, model, PLAN_PROMPT, timeout=timeout) or first_paragraph(plan)


def clean(s):
    s = re.sub(r"```.*?```", " ", s, flags=re.S)
    s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)
    s = re.sub(r"https?://\S+", "", s)
    s = re.sub(r"[*_`#>|]", "", s)
    return re.sub(r"\s+", " ", s).strip()


def first_paragraph(text):
    for p in (p.strip() for p in re.split(r"\n\s*\n", text)):
        if p and not p.startswith("#"):
            return clean(re.sub(r"(?i)^\W*(short answer|tl;?dr|summary)\W*:\W*", "", p))[:400]
    return ""


def ai_brief(text, model, prompt=BRIEF_PROMPT, timeout=45):
    try:
        r = subprocess.run(
            [vk.claude_bin(), "-p", "--model", model,
             "--settings", '{"disableAllHooks":true}',
             "--strict-mcp-config", "--tools", "", "--no-session-persistence"],
            input=prompt + text[:15000], capture_output=True, text=True,
            timeout=timeout, cwd="/tmp", env={**os.environ, "VOICEKIT_CHILD": "1"},
        )
        out = clean(r.stdout)
        return out if r.returncode == 0 and out else ""
    except Exception:
        return ""


def latest_file(session_id):
    """Per-session "newest reply" token: a newer reply from the SAME session replaces a stale briefing,
    but two agents finishing together are both spoken."""
    return f"{vk.LATEST_FILE}-{re.sub(r'[^A-Za-z0-9_-]', '', session_id or 'x')[:40]}"


def save_reply(text, project, keep):
    import fcntl
    vk.ensure_dirs()
    with open(vk.REPLIES_FILE + ".lock", "w") as lk:      # several sessions may finish at once
        fcntl.flock(lk, fcntl.LOCK_EX)
        try:
            with open(vk.REPLIES_FILE) as f:
                items = json.load(f)
        except Exception:
            items = []
        items.append({"time": time.strftime("%Y-%m-%d %H:%M:%S"), "project": project, "text": text})
        tmp = f"{vk.REPLIES_FILE}.{os.getpid()}.tmp"
        with open(tmp, "w") as f:
            json.dump(items[-keep:], f)
        os.replace(tmp, vk.REPLIES_FILE)


def last_reply_text(data):
    msg = data.get("last_assistant_message")
    if isinstance(msg, str) and msg.strip():
        return msg
    path = data.get("transcript_path")
    if not path or not os.path.exists(path):
        return ""
    texts = []
    with open(path, encoding="utf-8", errors="ignore") as f:
        for line in f:
            try:
                e = json.loads(line)
            except Exception:
                continue
            m = e.get("message") or {}
            if e.get("type") == "user" and isinstance(m.get("content"), str):
                texts = []
            elif e.get("type") == "assistant":
                for c in m.get("content") or []:
                    if isinstance(c, dict) and c.get("type") == "text":
                        texts.append(c["text"])
    return "\n\n".join(texts)


def worker(token, project, session_id=""):
    cfg = vk.load_config()["summary"]
    text = sys.stdin.read()
    if len(text) < cfg["short_reply_chars"]:
        brief = clean(text)
    else:
        brief = ai_brief(text, cfg["model"]) or first_paragraph(text)
    try:  # a newer reply arrived meanwhile: drop this one
        if open(latest_file(session_id)).read().strip() != token:
            return
    except Exception:
        pass
    s = registry.get(session_id) if session_id else None
    name = (s or {}).get("name") or project
    if brief:
        vk.speak(f"In {name}. {brief}" if name and cfg["speak_project_name"] else brief,
                 voice=(s or {}).get("voice"), polite=True)


def main():
    if len(sys.argv) > 2 and sys.argv[1] == "--worker":
        return worker(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "",
                      sys.argv[4] if len(sys.argv) > 4 else "")
    if os.environ.get("VOICEKIT_CHILD"):
        return
    try:
        data = json.load(sys.stdin)
    except Exception:
        return
    text = last_reply_text(data)
    if not text.strip():
        return
    vk.ensure_dirs()
    project = vk.project_name(data.get("cwd"))
    try:  # saved even when muted, so a full read is always possible
        save_reply(text, project, vk.load_config()["full_read"]["keep_replies"])
    except Exception:
        pass
    if vk.is_muted():
        return
    token = str(time.time_ns())
    with open(latest_file(data.get("session_id") or ""), "w") as f:
        f.write(token)
    p = subprocess.Popen([sys.executable, os.path.realpath(__file__), "--worker", token, project,
                          data.get("session_id") or ""],
                         stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True, text=True)
    p.stdin.write(text)
    p.stdin.close()


if __name__ == "__main__":
    main()
