#!/usr/bin/env python3
"""Lifecycle hook (SessionStart, UserPromptSubmit, Stop, StopFailure, Notification, SessionEnd):
keeps the session registry current so voice commands know every session, its state and its terminal.
Speaks only for failures ("builder stopped with an error"); briefings and alerts have their own hooks.
"""
import json, os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
import voicekit_common as vk  # noqa: E402
import registry  # noqa: E402

STATE_FOR = {"SessionStart": "idle", "UserPromptSubmit": "working", "Stop": "done",
             "StopFailure": "failed", "SessionEnd": "ended"}


def main():
    if os.environ.get("VOICEKIT_CHILD"):
        return
    try:
        data = json.load(sys.stdin)
    except Exception:
        return
    ev = data.get("hook_event_name", "")
    sid = data.get("session_id")
    if not sid:
        return
    fields = {"cwd": data.get("cwd"), "project": vk.project_name(data.get("cwd")),
              "transcript": data.get("transcript_path")}
    if ev in STATE_FOR:
        fields["state"] = STATE_FOR[ev]
    if ev == "UserPromptSubmit":
        prompt = (data.get("prompt") or "").strip()
        if prompt and not prompt.startswith("<"):   # skip system-injected messages (<task-notification> …)
            fields["last_prompt"] = prompt[:200]
        fields["pending"] = ""
    if ev in ("Stop", "SessionStart"):
        fields["pending"] = ""
    if ev == "Notification":
        kind = data.get("notification_type", "")
        if kind in ("permission_prompt", "elicitation_dialog"):
            fields["state"] = "waiting"
            cur = registry.get(sid) or {}
            if not cur.get("pending"):   # keep the exact request recorded by the approval hook
                fields["pending"] = data.get("message") or kind
    if os.environ.get("HERDR_TAB_ID"):          # herdr tab name ("docs") becomes the spoken name
        try:
            import adapters
            fields["label"] = adapters.herdr_tab_labels(timeout=3).get(os.environ["HERDR_TAB_ID"], "")
        except Exception:
            pass
    existing = registry.get(sid)
    if not existing or not existing.get("claude_pid"):
        pid = registry.find_claude_pid()
        fields["claude_pid"] = pid
        fields["terminal"] = registry.terminal_info(pid)
    registry.update(sid, **fields)
    if ev == "SessionStart":
        registry.replace_same_process(sid, (registry.get(sid) or {}).get("claude_pid"))

    if ev == "StopFailure" and not vk.is_muted():
        s = registry.get(sid) or {}
        vk.speak(f"{s.get('name', fields['project'])} stopped with an error.", urgent=True, voice=s.get("voice"),
                 polite=True)


if __name__ == "__main__":
    main()
