# Architecture

## Today (built)
```
 🎤 any dictation app (Handy, macOS Dictation, …) ──► Claude Code session (any terminal)
                                     │ reply done             │ needs you
                                     ▼                        ▼
             claude/hooks/speak_summary.py (Stop)   claude/hooks/speak_alert.py (Notification)
             saves full reply (last 10)             instant alert, no AI call
             Haiku briefing → "In <project>. …"     urgent: jumps the queue
                                     └──────────┬─────────────┘
                                                ▼
                       packages/kokoro-voice: voiced (Unix socket) ◄── `kokoro` command
                       Kokoro-82M on MLX · queue · urgent · replay · sections/next · tags
                       fallback if unavailable: macOS `say`
 ⌨️ hammerspoon/voice-kit.lua: ⌃⌥V on/off · ⌃⌥F full read · ⌃⌥N next · ⌃⌥R replay · ⌃⌥S stop · ⌃⌥K selection · fn stops
```

### Design choices
- **The voice is a standalone package.** `packages/kokoro-voice` has no Claude-specific code, so anything can use it.
- **Summaries come from a separate AI call (Haiku).** It's reliable but adds about 3 seconds, and falls back to the first paragraph if the call fails.
  Replies under 250 characters are read as they are.
- **The project name is spoken first,** so you can tell which session finished.
- **Briefings queue instead of overlapping.** A newer reply from the same moment replaces a stale briefing.
- **The idle alert is off by default** because it repeats ("Claude is waiting for your answer").
- **Full replies are saved even when muted,** so a full read always works.
- **Idle policy:** the voice model unloads after 10 minutes (~270 MB left) and the service quits after 20 (0 MB).
  It restarts on demand in ~1–5 s. launchd restarts it only after a crash.
- **PyTorch is kept on purpose:** it enables misaki's optional transformer grammar mode, which gives better
  pronunciation of words like "read" and "lead". See `packages/kokoro-voice/README.md`.
- **Settings live outside the project:** `~/.config/claude-voice-kit`, `~/.local/state/claude-voice-kit`, and
  `~/.config/kokoro-voice`. The project folder can be replaced or updated freely.

## Phase 0 findings (verified on Claude Code 2.1.326)
- **PermissionRequest hook:** `allow` runs the tool with no prompt; `deny` blocks it and Claude sees the message;
  no decision shows the normal prompt. It works alongside other tools' PermissionRequest hooks.
- **Channels:** a ~50-line Python stdio MCP server declaring `experimental["claude/channel"]` can push prompts into a
  session. It needs `--dangerously-load-development-channels server:<name>` plus a confirmation screen on each launch, so
  it's an optional path. herdr is the main way to send prompts.
- **Speech-to-text:** Parakeet-unified GGUF via `transcribe-cpp` (prebuilt Metal wheel) takes 0.05–0.1 s per phrase and
  loads in 0.4 s. The model has no punctuation/capitalisation switch and no vocabulary option, so `polish.py` adds them.

## Voice control (built)
```
 🎤 hold Right Command (⌘) or "hey Claude" ─► listen-voice: Parakeet speech-to-text (reuses an existing local model, e.g. Handy's)
                               → polish: spacing, capitals, . and ?  → fix known project/agent names
                                       │ text
 voice-control service ◄─────────────┘
   router: instant rules ("approve", "stop", "status") → Haiku only for unclear phrases → action
           remembers "it" = the last agent mentioned
   session registry ◄── event hook in every session (start · prompt · done · needs you · end · terminal)
   actions:
     approve / deny ──► PermissionRequest hook (any terminal; only in hands-free mode)
     send prompt ────► voice channel (Claude Code Channels, any terminal) → herdr → any window
     focus / Esc ────► adapters: herdr · any window (Hammerspoon)
   attention: needs permission > failed > done ─► kokoro (one voice by default, optionally a voice per agent)
   on-screen strip ("Heard: approve → builder ✓") · audit log
```

### Voice-control rules
- **No new approvals.** Voice only answers the permission prompts Claude Code already shows.
- **Hands-free mode (⌃⌥H) turns voice approvals on.** When it's off, nothing changes. When it's on, the hook waits up to
  20 s for a spoken answer. With no answer, nothing is decided and the normal screen prompt appears.
- **Extra confirmations, only for actions you start by voice:**
  - risky commands (`rm`, `git push`, `sudo`, deploy, delete) need "yes, approve"
  - "tell everyone…" and stopping agents ask first
- **Command key:** hold Right Command (⌘). fn stays the dictation key of your dictation app.

### Phases (all built and tested)
| # | Phase | How it was verified |
|---|---|---|
| 0 ✅ | Checks | PermissionRequest allow/deny/no-decision, Channels push, Parakeet speed, Right ⌘ hold |
| 1 ✅ | listen-voice + polish | recorded dictation samples; live push-to-talk with the microphone |
| 2 ✅ | Registry + attention | sessions learned from hooks and herdr; per-agent names and voices; names survive /clear |
| 3 ✅ | Command core | status, what's it asking, approve via herdr keys (only when a prompt is on screen), risky needs "yes approve", hands-free approve/deny through the hook |
| 4 ✅ | Instructions | "tell X to …" via herdr, clear/compact/model, confirmations, Haiku fallback ("how is everyone getting on" → status) |
| 5 ✅ | Agent lifecycle | "start an agent in work to …" opened a herdr pane and ran the task; rename; stop (Esc, asks first) |
| 6 ✅ | Hands-free | wake phrase, follow-up phrase, "stop" barge-in, own speech ignored; live test from speakers to microphone |
| 7 ✅ | Leader mode | leader started with `--append-system-prompt-file`, used herdr to inspect workers, reported back |

### Lessons from testing
- herdr rejects launch commands longer than the terminal's input-line limit, so the leader prompt is passed as a file.
- An agent can ask a second question right after an approval. Key presses are therefore sent only when herdr reports the
  agent `blocked` at that moment.
- **The microphone stayed open while idle** (macOS showed the orange indicator) after some push-to-talk sequences. Likely
  cause: a quick key tap where "stop" arrived before "start". Fix: the service never opens the mic itself. Each
  recording runs in a short-lived `recorder.py` process that exits when recording ends, so macOS always releases the
  mic. A "stop" that arrives early cancels its "start". A spare recorder waits ready with the mic closed. Measured:
  release plus transcribe in 0.12–0.14 s, and the mic off after every release, quick tap, crash and hands-free off.
- **Plan approvals weren't briefed.** A plan waiting for approval isn't a finished reply, so the Stop hook doesn't run.
  It arrives as a PermissionRequest for `ExitPlanMode`, with the plan in `tool_input.plan` (plus `planFilePath`).
  `voice_approval.py` now saves the plan for ⌃⌥F and speaks a Haiku briefing of it: in the background normally, or
  before "Approve the plan?" in hands-free mode. The generic "needs your approval for the plan" alert is skipped.
- **Don't talk over other audio.** `audio_activity.py` reads CoreAudio's per-process list (ctypes, macOS 14.2+) to see
  which apps have audio output or input running. "Polite" messages (everything automatic) are checked just before they're
  generated. If another app is active, the message is held (`held.json`, 30 min) and `notify_command` →
  `notify_held.py` → `voiceKit.notifyHeld` shows a silent notification with Play / Dismiss and the message's actions.
  Approval buttons run `voicectl approve|deny <session id>`. Lessons:
  - macOS reports *open* audio channels, not sound. Some apps (e.g. dictation or chat apps) keep output open permanently, hence
    `ignore_output_processes` (output ignored, microphone still counts).
  - Two notifications sent together race.
  - Buttons must target the session id: names can change between the question and the click.
  - macOS doesn't report "Dismiss" clicks, so dismissed messages stay on ⌃⌥P until they expire.
  - **Open isn't audible.** A Discord tab in Safari kept `com.apple.WebKit.GPU`'s output open for days, and
    `systemsoundserverd` keeps its channel open after alert sounds, so nearly every message was held. The
    `audio-level` helper (Swift, Core Audio process tap, macOS 14.2+) now measures apps that only have output open
    for 0.25 s and ignores them below -50 dBFS; if several are open and something is loud, each is measured to name
    the right app. Lessons: the helper re-launches itself with responsibility disclaimed so macOS asks permission
    for the helper rather than for the Python service; an ad-hoc signature changes on every build and macOS then asks
    again, so the installer rebuilds only when the source changes.
- **Fresh-install test found a crash for deep install folders.** espeak-ng (misaki's fallback for unknown words) can't
  read its data when that folder's path is over ~160 characters, and it resolves symlinks. `voiced.short_espeak_path()`
  copies the 19 MB data folder to `~/.local/state/kokoro-voice/` when the path is long.
- **An install test broke every Claude session.** Hooks were recognised by the folder name "claude-voice-kit". A copy in
  another folder was therefore neither replaced by the next install nor removed by uninstall. After that copy was
  deleted, its hooks ran a missing script, and `python3` exits with **code 2** for a missing file, which Claude Code treats
  as "block" ("UserPromptSubmit operation blocked by hook"). Fixes:
  - hook commands carry a marker (`VOICEKIT_HOOK=1`) and end in `|| true`, so they are found wherever the kit lives and
    can never block
  - `voicekit doctor` flags hooks that point at missing scripts
  - unit tests cover all three
- A Ruby gem also installs a `listen` command, so ours is called `listen-voice`.
- The approval hook records the exact request ("run rm x.txt"). The generic Notification message must not overwrite it,
  because the risky check depends on it.
