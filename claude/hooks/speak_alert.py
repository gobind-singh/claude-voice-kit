#!/usr/bin/env python3
"""Notification hook: speak Claude Code alerts aloud (urgent, jumps the speech queue).

Which alerts are spoken is set in config.json -> "alerts":
  permission: Claude needs permission to run a tool          (default on)
  question:   Claude asks you to choose (elicitation dialog)  (default on)
  idle:       "Claude is waiting for your input" reminder     (default off: it repeats)
Change with `cvoice alerts <name> on|off`. Everything is muted by `cvoice off`.
"""
import json, os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
import voicekit_common as vk  # noqa: E402
import registry  # noqa: E402


def classify(kind, msg):
    m = msg.lower()
    if kind == "permission_prompt" or (not kind and "permission" in m):
        return "permission", msg or "Claude needs your permission."
    if kind == "elicitation_dialog":
        return "question", "Claude has a question for you."
    if kind == "idle_prompt" or (not kind and "waiting" in m):
        return "idle", "Claude is waiting for your answer."
    return None, None


def main():
    if os.environ.get("VOICEKIT_CHILD") or vk.is_muted():
        return
    try:
        data = json.load(sys.stdin)
    except Exception:
        return
    name, text = classify(data.get("notification_type", ""), (data.get("message") or "").strip())
    if not name or not vk.load_config()["alerts"].get(name):
        return
    if name == "permission" and vk.handsfree():
        return            # hands-free: the approval hook already asked out loud
    m = (data.get("message") or "").lower()
    if name == "permission" and ("exitplanmode" in m.replace(" ", "") or "approval for the plan" in m):
        return            # plan approval: the approval hook speaks a plan briefing instead
    s = registry.get(data.get("session_id")) or {}
    who = s.get("name") or vk.project_name(data.get("cwd"))
    if who and who != "home folder":
        text = f"In {who}. {text}"
    vk.speak(text, urgent=True, voice=s.get("voice"), polite=True)


if __name__ == "__main__":
    main()
