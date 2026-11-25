# Using claude-voice-kit

- [Install and first run](#install-and-first-run)
- [Hotkeys](#hotkeys)
- [Voice commands](#voice-commands)
- [Hands-free mode](#hands-free-mode)
- [When other audio is playing](#when-other-audio-is-playing)
- [Which terminals](#which-terminals)
- [Command-line tools](#command-line-tools)
- [Settings](#settings)
- [Resource use](#resource-use)
- [Troubleshooting](#troubleshooting)
- [Uninstall](#uninstall)

## Install and first run
```sh
git clone https://github.com/gobind-singh/claude-voice-kit.git ~/.claude-voice-kit && ~/.claude-voice-kit/install.sh
```
- **Requirements:** Apple Silicon Mac, [Homebrew](https://brew.sh), [Claude Code](https://claude.com/claude-code).
  macOS 14.2+ is needed to detect other audio; on older versions, messages are always spoken.
- **Installed by the script if missing:** `uv`, [Hammerspoon](https://www.hammerspoon.org), the Kokoro voice model, the
  Parakeet speech model.
- **Downloads:** about 1.8 GB, plus about 700 MB for the speech model unless [Handy](https://handy.computer) already
  downloaded it. Re-running the installer is safe and is how you update.

One-time steps after `✅ Installed.`:

| Step | Where |
|---|---|
| Allow Hammerspoon to control your keyboard | System Settings → Privacy & Security → **Accessibility** |
| Allow Hammerspoon to use the microphone | macOS asks the first time you hold Right ⌘ |
| Allow "System Audio Recording" for audio-level | macOS asks during install (volume check only; nothing recorded) |
| Restart your Claude Code sessions | your terminal |
| Check everything | `voicekit doctor` |

## Hotkeys
| Key | Does |
|---|---|
| **Right ⌘ (hold)** | after a soft tick (0.3 s), speak a voice command; release to run it. A pop-up (HUD) at the bottom of the screen shows listening → transcribing → the result and what was heard |
| ⌃⌥H | hands-free mode on/off |
| ⌃⌥V | Claude's voice on/off (mute) |
| ⌃⌥F | read the whole last reply or plan (press again to stop) |
| ⌃⌥N | skip to the next section |
| ⌃⌥R | repeat the last message |
| ⌃⌥S | stop speaking |
| ⌃⌥P | play messages held while other audio was playing |
| ⌃⌥K | read the selected text in any app |
| fn | stop speaking (fn is the usual dictation key, so you're never talked over) |

Listening starts only after Right ⌘ has been held **on its own** for 0.3 s, so shortcuts such as Right ⌘ + Delete or
Right ⌘ + C never stop speech, open the microphone or flash the strip. Wait for the tick, then speak. To change the key,
the delay or the tick, set `push_to_talk` in `~/.config/claude-voice-kit/config.json`, then reload Hammerspoon:

```json
"push_to_talk": {"key": "right_cmd", "hold_ms": 300, "cue_sound": "Tink"}
```
`key` can be `right_cmd`, `right_option`, `right_shift` or `right_ctrl`. `cue_sound` is any macOS sound name, or `""` for none.

## Voice commands
Hold **Right ⌘**, or say **"hey Claude, …"** in hands-free mode.

| Area | Say |
|---|---|
| Overview | "what's happening" · "who needs me" · "what's api doing" |
| Approvals | "what's it asking" · "approve" · "yes approve" (for risky commands) · "always allow" · "deny" · "pick option 2" |
| Instruct | "tell reviewer to check the diff" · "tell it to run the tests" · "tell everyone to commit" (asks first) |
| Navigate | "switch to api" · "go to docs" |
| Control | "stop api" (asks first) · "clear api" · "compact" · "use sonnet in api" |
| Agents | "start an agent in api to fix the tests" · "name this one reviewer" |
| Leader | "start the leader" · "tell the leader to split the refactor between two agents" |
| Listening | "stop" · "repeat" · "read it all" · "next" · "faster" · "slower" · "mute Claude" · "hands free on" |

- **Agent names:** the herdr tab name, then the folder name ("api", or "api 2" when two share a folder), unless you name
  the agent yourself.
- **"It"** means the agent you mentioned last.
- **Unclear phrases** are passed to Claude Haiku, which picks the closest command. Turn this off with
  `control.ai_router: false`.

### Safety rules
- Voice only answers permission prompts that Claude Code already shows. It never adds approvals.
- With hands-free **off** (the default), "approve" presses the key only while a prompt is on screen in herdr.
- Risky commands (`rm`, `git push`, `sudo`, deploy, delete, …) need **"yes, approve"**. You can change the patterns with
  `control.risky_patterns`.
- "Tell everyone" and "stop" always ask "yes or no" first.
- Every voice action is logged in `~/.local/state/claude-voice-kit/audit.log`.

## Hands-free mode
Toggle with **⌃⌥H** or say "hands free on".
- The microphone listens for **"hey Claude, …"**, and everything is transcribed locally. Saying just "hey Claude" makes the
  next phrase the command.
- Permission prompts are **asked out loud**. The agent waits 20 s for "approve" or "deny"; with no answer, nothing is
  decided and the normal prompt appears.
- Saying **"stop"** while the kit is talking interrupts it.

## When other audio is playing
If another app is audibly playing sound or using the microphone (music, a video, a call, dictation), automatic messages
(briefings, alerts, plan summaries, approval questions) are **not spoken**. Nothing pops up to interrupt you: the HUD
briefly says "Message held", and the **menu bar icon** shows how many are waiting. Click it to see each one:
- **Play:** speak it now.
- **Approve / Deny** (or **Approve plan / Keep planning**): answers the waiting prompt directly.
- **Dismiss:** removes it. Messages stay for 30 minutes; **⌃⌥P** plays them all.

To also get a macOS notification with buttons, set `"ui": {"held": "notification"}` in
`~/.config/claude-voice-kit/config.json`.

Anything you ask for yourself (⌃⌥F, ⌃⌥K, replay, replies to voice commands) always plays.

- **Only real sound counts.** Many apps keep a silent audio channel open (a Discord tab in Safari, dictation apps).
  A quick volume check (0.25 s) ignores those. It needs the **System Audio Recording** permission, which the installer
  asks for once; it only measures volume and records nothing.
- `kokoro --audio-check` shows which apps count as "using audio" right now, and which are open but silent.
- To always ignore an app's output, add it to `ignore_output_processes` in `~/.config/kokoro-voice/config.json`; its
  microphone use still counts.
- To always speak, set `"when_other_audio": "play"`.

## Which terminals
| | herdr | any other terminal |
|---|---|---|
| Briefings, alerts, plan summaries | ✅ | ✅ |
| Status ("what's happening") | ✅ | ✅ |
| Hands-free approvals | ✅ | ✅ |
| Approve an on-screen prompt with hands-free off | ✅ | — |
| Send instructions ("tell api to …") | ✅ | ✅ when started with `claude-voice`¹, otherwise pasted into the front window |
| Switch, stop, start agents, leader | ✅ | basic (brings the window forward) |

¹ `claude-voice` is `claude` plus a local voice channel. It uses Claude Code *Channels*, a research preview, so Claude
Code asks you to confirm "local development" at each launch.

## Command-line tools
| Command | Purpose |
|---|---|
| `voicekit doctor` · `status` · `paths` · `install` · `uninstall` | check, inspect, install, remove |
| `voicectl "<command>"` · `voicectl agents` · `voicectl handsfree on\|off` | voice commands from the keyboard |
| `cvoice on\|off\|full\|replay\|stop\|alerts` | Claude voice controls |
| `kokoro "text"` · `-f file.md` · `--voices` · `--set-voice` · `--set-speed` · `--held` · `--audio-check` | text-to-speech |
| `listen-voice -f speech.wav` · `--record 5` · `--wake on\|off` | speech-to-text |
| `claude-voice` | start Claude Code with the voice channel |

## Settings
| File | What you can change |
|---|---|
| `~/.config/claude-voice-kit/config.json` | push-to-talk key and delay, which alerts are spoken, summary model, approval timeout, risky patterns, confirmations, per-agent voices (`agent_voices`), AI router, wake words, on-screen UI (`ui`: `hud`, `menubar`) |
| `~/.config/kokoro-voice/config.json` | voice, speed, idle timers, behaviour when other audio is playing, ignored apps |
| `~/.config/listen-voice/config.json` | speech model, microphone, vocabulary and corrections ("harder" → "herdr"), wake phrases |

### On screen
- **HUD:** a small dark pop-up near the bottom of the screen. Its colour shows the state: red = listening,
  amber = working, green = done, orange = problem, blue = info. It floats above every app, clicks pass
  through it, and it fades away by itself.
- **Menu bar icon:** sound bars (crossed out when Claude's voice is off), a dot when hands-free is on, and the
  number of held messages. Click it for voice on/off, hands-free, each held message (Play, Approve / Deny, Dismiss),
  replay, stop, and the shortcut list.
- To turn either off, set `"ui": {"hud": false}` (back to Hammerspoon's plain alert box) or
  `"ui": {"menubar": false}` in `~/.config/claude-voice-kit/config.json`, then reload Hammerspoon.

`voicekit paths` lists every file the kit uses. Settings live outside the project folder, so updating never touches them.

## Resource use
Measured on an M-series Mac:

| State | Memory | CPU |
|---|---|---|
| Just used | ~0.9 GB | ~0% (bursts while speaking or transcribing) |
| After 10 quiet minutes | ~0.4 GB (models unloaded) | ~0% |
| After 20 quiet minutes | ~65 MB (only Hammerspoon; the services restart on demand) | ~0% |

| Action | Time |
|---|---|
| Hooks per Claude event | 0.1–0.3 s (the summary runs in the background) |
| Spoken summary after a reply | about 3 s (Haiku) plus about 0.5 s until speech starts |
| Release Right ⌘ → transcript | about 0.1–0.5 s |
| First speech after a quiet spell | +1.5 s (model reload) or +4–5 s (service restart) |

## Troubleshooting
| Problem | Fix |
|---|---|
| Something isn't working | `voicekit doctor`: it names each failing part and how to fix it |
| Hotkeys don't respond | Allow Hammerspoon in Accessibility, then open Hammerspoon → Reload Config |
| No briefing after a reply | Restart that Claude session. Then run `cvoice status`: Claude's voice may be muted (⌃⌥V) |
| Messages never play | `kokoro --audio-check`. If it says the volume check is off, run `voicekit install` and allow System Audio Recording |
| Right ⌘ shows "Didn't catch that" | Allow Hammerspoon to use the microphone (Privacy & Security → Microphone) |
| A hook shows an error in Claude Code | `voicekit doctor` flags hooks pointing at missing files; `voicekit install` repairs them |
| Logs | `~/.local/state/kokoro-voice/voiced.log` · `~/.local/state/listen-voice/listend.log` · `~/.local/state/claude-voice-kit/audit.log` |

## Uninstall
```sh
~/.claude-voice-kit/uninstall.sh            # removes hooks, services, commands and hotkeys (keeps settings)
~/.claude-voice-kit/uninstall.sh --purge    # also deletes settings, saved replies and the voice model
```
Then delete the folder. Hammerspoon, uv and Handy stay installed; remove them with Homebrew if you like. Uninstall
removes only this kit's hooks and leaves hooks from other tools alone.
