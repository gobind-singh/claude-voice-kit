#!/usr/bin/env python3
"""PermissionRequest hook: answer Claude Code's permission prompts by voice (hands-free mode only).

- Hands-free off (default) or muted: returns immediately with no decision, so the normal prompt shows.
- Hands-free on: says "<agent> wants to run <command>. Approve?" and waits up to
  control.approval_timeout_seconds for a spoken answer (`voicectl approve|always|deny`).
  Risky commands need "yes, approve". No answer means no decision, and the normal prompt appears.
It never approves or denies on its own, and it only answers prompts Claude Code already shows.
"""
import json, os, re, sys, time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
import voicekit_common as vk  # noqa: E402
import registry  # noqa: E402

PLAN_TOOLS = {"ExitPlanMode"}


def plan_text(inp):
    """The plan Claude wants approved (inline, or from the plan file)."""
    plan = inp.get("plan") or ""
    path = inp.get("planFilePath") or inp.get("plan_file_path")
    if not plan and path and os.path.exists(path):
        plan = open(path, encoding="utf-8", errors="ignore").read()
    return plan


def announce_plan(data, plan, wait):
    """Save the plan for a full read (Control+Option+F) and speak a short briefing of it.
    wait=True (hands-free): brief now, before asking "Approve?". Otherwise in the background."""
    import speak_summary as ss
    s = registry.get(data.get("session_id")) or {}
    name = s.get("name") or vk.project_name(data.get("cwd"))
    try:
        ss.save_reply(plan, name, vk.load_config()["full_read"]["keep_replies"])
    except Exception:
        pass
    if vk.is_muted():
        return
    if not wait:
        import subprocess
        p = subprocess.Popen([sys.executable, os.path.realpath(__file__), "--plan-brief",
                              data.get("session_id") or "", name], stdin=subprocess.PIPE,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True,
                             text=True)
        p.stdin.write(plan)                      # hand over and return at once: Claude isn't blocked
        p.stdin.close()
        vk.audit("plan_briefing", session=name, chars=len(plan))
        return
    # hands-free: the hook is waiting, so keep the summary quick (the hook has a fixed time limit)
    speak_plan(plan, name, s.get("voice"), ask=False, session_id=data.get("session_id") or "", timeout=15)


VOICECTL = os.path.join(vk.KIT_DIR, "claude", "voicectl")


def approval_actions(session_id, plan=False, request_id=None):
    """Buttons shown if a question is held because other audio is playing.
    With request_id (hands-free): the button answers exactly that request, and nothing once it has expired.
    Without (a plan shown on screen): the button only acts if that session is still showing a plan prompt."""
    if request_id:
        return [{"label": "Approve plan" if plan else "Approve", "command": [VOICECTL, "approve-request", request_id]},
                {"label": "Keep planning" if plan else "Deny", "command": [VOICECTL, "deny-request", request_id]}]
    if plan:
        return [{"label": "Approve plan", "command": [VOICECTL, "approve-plan", session_id]},
                {"label": "Keep planning", "command": [VOICECTL, "keep-planning", session_id]}]
    return []


def speak_plan(plan, name, voice, ask=True, session_id="", timeout=45):
    import speak_summary as ss
    brief = ss.plan_brief(plan, vk.load_config()["summary"]["model"], timeout=timeout)
    end = " Approve it, or tell it what to change. Say read it all to hear the whole plan." if ask else ""
    vk.speak(f"In {name}. The plan is ready for your approval. {brief}{end}", urgent=True, voice=voice,
             polite=True, actions=approval_actions(session_id, plan=True))


def describe(tool, inp):
    inp = inp or {}
    if tool in PLAN_TOOLS:
        return "approve the plan"
    if tool == "Bash":
        return "run " + (inp.get("command") or "a command").strip().splitlines()[0][:120]
    if tool in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
        return f"{'edit' if tool != 'Write' else 'write'} {os.path.basename(inp.get('file_path') or inp.get('notebook_path') or 'a file')}"
    if tool in ("WebFetch", "WebSearch"):
        return "fetch " + re.sub(r"^https?://([^/]+).*", r"\1", inp.get("url") or inp.get("query") or "the web")
    if tool.startswith("mcp__"):
        parts = tool.split("__")
        return f"use {parts[-1].replace('_', ' ')} from {parts[1].replace('_', ' ')}"
    return f"use {tool}"


def short_paths(text):
    """Speak file names, not long paths."""
    return re.sub(r"(?<![\w/])(?:~|\.{1,2})?(?:/[\w.@+\-]+){2,}/?",
                  lambda m: os.path.basename(m.group(0).rstrip("/")) or m.group(0), text)


def is_risky(text, patterns):
    return any(re.search(p, text, re.I) for p in patterns)


def main():
    if len(sys.argv) > 3 and sys.argv[1] == "--plan-brief":      # background plan briefing
        s = registry.get(sys.argv[2]) or {}
        return speak_plan(sys.stdin.read(), sys.argv[3], s.get("voice"), session_id=sys.argv[2])
    raw = sys.stdin.read()
    if os.environ.get("VOICEKIT_CHILD"):
        return
    try:
        data = json.loads(raw)
    except Exception:
        return
    sid = data.get("session_id")
    tool, inp = data.get("tool_name", ""), data.get("tool_input") or {}
    desc = short_paths(describe(tool, inp))
    registry.update(sid, state="waiting", pending=desc)
    is_plan = tool in PLAN_TOOLS and bool(plan_text(inp).strip())
    hands_free = vk.handsfree() and not vk.is_muted()
    if tool in PLAN_TOOLS:
        vk.audit("plan_request", input_keys=sorted(inp.keys()))
    if is_plan:
        announce_plan(data, plan_text(inp), wait=hands_free)
    if not hands_free:
        return                                   # no decision: normal prompt

    cfg = vk.load_config()["control"]
    risky = cfg["confirm_risky"] and is_risky(json.dumps(inp) + " " + desc, cfg["risky_patterns"])
    s = registry.get(sid) or {}
    name = s.get("name") or vk.project_name(data.get("cwd"))
    req_id = f"{int(time.time() * 1000)}-{(sid or 'x')[:8]}"
    os.makedirs(vk.PENDING_DIR, exist_ok=True)
    pending = os.path.join(vk.PENDING_DIR, req_id + ".json")
    decision_file = os.path.join(vk.PENDING_DIR, req_id + ".decision")
    risky = risky and not is_plan               # a plan's text may mention "delete"; approving it is not risky
    def cleanup(*_):
        for p in (pending, decision_file):
            try:
                os.remove(p)
            except OSError:
                pass

    import signal
    signal.signal(signal.SIGTERM, lambda *a: (cleanup(), os._exit(0)))   # killed at the hook timeout
    with open(pending, "w") as f:
        json.dump({"id": req_id, "session_id": sid, "name": name, "tool": tool, "desc": desc,
                   "risky": risky, "created": time.time(), "expires": time.time() + cfg["approval_timeout_seconds"]}, f)
    if is_plan:
        ask = "Approve the plan? Say approve, or deny to keep planning."
    else:
        ask = f"{name} wants to {desc}. " + ("That's risky. Say yes approve, or deny." if risky else "Approve?")
    decision = None
    try:
        vk.speak(ask, urgent=True, voice=s.get("voice"), polite=True,
                 actions=approval_actions(sid, is_plan, request_id=req_id))
        vk.audit("approval_asked", session=name, request=desc, risky=risky)
        deadline = time.time() + cfg["approval_timeout_seconds"]
        while time.time() < deadline:
            if os.path.exists(decision_file):
                decision = open(decision_file).read().strip()
                break
            time.sleep(0.2)
    finally:
        cleanup()
    if not decision:
        vk.audit("approval_timeout", session=name, request=desc)
        return                                   # no decision: normal prompt appears

    if decision in ("allow", "always"):
        out = {"behavior": "allow"}
        if decision == "always" and data.get("permission_suggestions"):
            out["updatedPermissions"] = data["permission_suggestions"]
    else:
        out = {"behavior": "deny", "message": "Denied by voice."}
    registry.update(sid, state="working", pending="")
    vk.audit("approval_answered", session=name, request=desc, decision=decision)
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PermissionRequest", "decision": out}}))


if __name__ == "__main__":
    main()
