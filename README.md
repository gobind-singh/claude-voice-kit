<div align="center">

<img src="docs/images/logo.svg" width="96" alt="claude-voice-kit logo: sound bars">

# claude-voice-kit

**Talk to Claude Code and hear it talk back, across many agents at once.**

Spoken briefings · voice commands · hands-free approvals · all speech runs locally on your Mac

[![CI](https://github.com/gobind-singh/claude-voice-kit/actions/workflows/ci.yml/badge.svg)](https://github.com/gobind-singh/claude-voice-kit/actions/workflows/ci.yml)
![Platform](https://img.shields.io/badge/platform-macOS%20·%20Apple%20Silicon-black)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

<img src="docs/images/hud-listening.png" width="334" alt="On-screen pop-up: Listening… Release Right ⌘ when done">

</div>

---

## Why
Coding agents ask for your attention all day: *finished*, *needs permission*, *here's my plan*. With several agents
running, you end up tab-hopping and reading walls of text. **claude-voice-kit** lets you *listen* instead of read, and
*speak* instead of switching windows. Speech recognition and speech generation run on your Mac; your voice never leaves it.

## What you get
| | Feature | What happens |
|:-:|---|---|
| <img src="docs/images/icons/speaker.svg" width="22" alt=""> | **Spoken briefings** | When an agent finishes, you hear 2–3 sentences: *"In api. The tests pass and the PR is ready."* |
| <img src="docs/images/icons/lines.svg" width="22" alt=""> | **Plan summaries** | When Claude asks you to approve a plan, you hear what it will do and what's risky. |
| <img src="docs/images/icons/mic.svg" width="22" alt=""> | **Voice commands** | Hold **Right ⌘** and say *"what's happening"*, *"approve"*, *"tell docs to run the tests"*, *"switch to api"*. |
| <img src="docs/images/icons/headphones.svg" width="22" alt=""> | **Hands-free** | Say *"hey Claude, …"* without touching a key. Answer permission prompts out loud. Say *"stop"* to interrupt. |
| <img src="docs/images/icons/message.svg" width="22" alt=""> | **Polite** | Music, a video or a call playing? Nothing is spoken. The menu bar icon keeps the messages for later, each with **Play / Approve / Deny**. |
| <img src="docs/images/icons/bars.svg" width="22" alt=""> | **Multi-agent** | Every session is tracked by name. A **leader** agent can split work across worker agents. |

## Using it, in 3 steps
**1. Hold Right ⌘.** After a soft tick, the red *Listening…* pop-up (shown at the top) appears. Say what you want, then
let go.

**2. Watch the pop-up.** It shows what it heard, then sends it to the right agent.

<img src="docs/images/hud-transcribing.png" width="300" alt="“tell api to run the tests” · Working on it…">
<img src="docs/images/hud-done.png" width="310" alt="Sent to api · Heard “tell api to run the tests”">

**3. Listen.** When the agent finishes or needs you, you hear a short summary. To answer a permission prompt, say
*"approve"* or *"deny"*. In hands-free mode, Claude asks you out loud.

### What the pop-up colours mean
The pop-up sits at the bottom of the screen, floats above every app, lets clicks pass through and fades away by itself.

| | Colour | Meaning |
|---|---|---|
| <img src="docs/images/hud-listening.png" width="230" alt=""> | 🔴 red | listening to you |
| <img src="docs/images/hud-transcribing.png" width="210" alt=""> | 🟠 amber | working on it |
| <img src="docs/images/hud-done.png" width="215" alt=""> | 🟢 green | done |
| <img src="docs/images/hud-problem.png" width="260" alt=""> | 🟧 orange | something went wrong, with a hint |
| <img src="docs/images/hud-held.png" width="300" alt=""> | 🔵 blue | information, e.g. a message was held |

## The menu bar icon
The icon shows Claude's voice state at a glance. Click it for everything else.

| <img src="docs/images/menubar-on.svg" height="28" alt="sound bars"> | <img src="docs/images/menubar-off.svg" height="28" alt="crossed-out bars"> | <img src="docs/images/menubar-handsfree.svg" height="28" alt="bars with a dot"> | <img src="docs/images/menubar-held.svg" height="28" alt="bars with the number 2"> |
|:-:|:-:|:-:|:-:|
| voice on | voice off | hands-free on | 2 messages held |

<p align="center">
  <img src="docs/images/menu.png" width="432" alt="Menu: Claude voice, Hands-free, a held message with Approve/Deny, Read last reply in full, Replay, Stop, Voice, Speed, Keyboard shortcuts">
  <img src="docs/images/menu-shortcuts.png" width="320" alt="Keyboard shortcuts submenu: each shortcut with its keys; choose one to change it">
</p>

From the menu you can:
- turn **Claude voice** and **Hands-free** on or off
- play, approve, deny or dismiss **held messages** (each one is a submenu)
- read the last reply in full, replay it, or stop speaking
- pick a **Voice** (you hear a short sample) and a **Speed**
- change any **keyboard shortcut**: choose it, then press the new keys

## Quick start
**You need:** an Apple Silicon Mac (macOS 14.2+ recommended), [Homebrew](https://brew.sh) and
[Claude Code](https://claude.com/claude-code).

```sh
git clone https://github.com/gobind-singh/claude-voice-kit.git ~/.claude-voice-kit && ~/.claude-voice-kit/install.sh
```

The installer sets up everything else: Python via `uv`, Hammerspoon, the voice model and the speech model. You can
run it again safely, and running it again is how you update. When it prints `✅ Installed.`:

1. Allow **Hammerspoon** in *System Settings → Privacy & Security → Accessibility*.
2. **Restart your Claude Code sessions.**
3. Run `voicekit doctor`. Every line should show ✅.

Then ask Claude anything and listen for the briefing, or hold **Right ⌘** and say *"what's happening"*.

## Everyday keys
| Key | Does |
|---|---|
| **Right ⌘** (hold) | speak a command after the tick; quick shortcuts like Right ⌘ + Delete are left alone |
| ⌃⌥ **F** / **N** | read the whole reply / skip to the next section |
| ⌃⌥ **R** / **S** | repeat / stop (**fn** also stops) |
| ⌃⌥ **V** / **H** | voice on/off / hands-free on/off |
| ⌃⌥ **P** | play messages held during other audio |
| ⌃⌥ **K** | read the selected text in any app |

⌃ = Control, ⌥ = Option, ⌘ = Command. Change any shortcut from the menu bar icon or with `voicekit keys`. Every
voice command, setting and troubleshooting tip is in **[docs/usage.md](docs/usage.md)**.

## Safe by design
- **No new approvals:** voice only answers prompts Claude Code already shows. Risky commands (`rm`, `git push`, `sudo`,
  …) need *"yes, approve"*.
- **Hands-free is off by default.** When it's on and you don't answer, nothing is decided and the normal prompt appears.
- **Hooks can't block Claude:** if anything in the kit fails, Claude Code carries on as normal.
- **Audit log:** every voice action is logged. The microphone is only open while you hold the key or hands-free is on.

## Privacy
| Stays on your Mac | Sent to Claude (Haiku) |
|---|---|
| your voice, speech recognition and speech generation, the session list, the audit log | the text of each reply and of each plan you're asked to approve, to write its spoken summary; commands the built-in rules don't understand |

## How it works
```mermaid
flowchart LR
    subgraph You
        K["⌨️ Right ⌘ / hotkeys"]
        M["🎤 microphone"]
        S["🔊 speakers"]
    end

    subgraph Mac["Your Mac (local)"]
        HS["Hammerspoon<br/>hotkeys · push-to-talk<br/>on-screen HUD · menu bar"]
        LV["listen-voice<br/>Parakeet speech-to-text<br/>+ text polish"]
        VC["voicectl<br/>command router"]
        KV["kokoro-voice<br/>Kokoro text-to-speech<br/>queue · polite mode"]
        subgraph CC["Claude Code sessions (any terminal)"]
            H["hooks<br/>briefings · alerts<br/>approvals · session state"]
        end
        R[("session<br/>registry")]
        A["adapters<br/>herdr · voice channel · window"]
    end

    AI["☁️ Claude Haiku<br/>(summaries only)"]

    K --> HS
    M --> LV
    HS --> LV --> VC
    VC --> A --> CC
    VC <--> R
    H --> R
    H -- "reply text" --> AI -- "2–3 sentence briefing" --> H
    H --> KV
    VC --> KV
    KV --> S
    KV -. "other audio playing" .-> N["🔕 held quietly<br/>menu bar: Play · Approve · Deny"]
```

- **Listening:** hold Right ⌘ (or say "hey Claude"). `listen-voice` transcribes on your Mac in about 0.1 s and tidies
  the text, then `voicectl` works out the command and acts on the right session.
- **Speaking:** Claude Code **hooks** fire when an agent finishes, needs permission or proposes a plan. Haiku writes a
  short summary and `kokoro-voice` speaks it.
- **Reaching sessions:** through [herdr](https://herdr.dev) (full control), a local voice channel (any terminal), or by
  focusing the window.

More detail, including the design decisions, is in [docs/architecture.md](docs/architecture.md).

## Dictation
For dictating messages, use **[Handy](https://handy.computer)** (free, open source). It uses the same Parakeet model,
which the kit reuses, so nothing is downloaded twice. **macOS Dictation** also works.

## Project layout
```
install.sh · uninstall.sh   one-command install / removal
bin/                        voicekit (install · doctor · status · keys), claude-voice (voice channel launcher)
packages/kokoro-voice/      text-to-speech service + `kokoro` CLI (standalone)
packages/listen-voice/      speech-to-text service + `listen-voice` CLI (standalone)
claude/                     Claude Code layer: hooks, voicectl router, registry, adapters
hammerspoon/                hotkeys, push-to-talk, on-screen HUD, menu bar icon, line icons
docs/                       usage, architecture, publishing, third-party licences
docs/images/                logo, icons and screenshots (regenerate with scripts/readme-images.sh)
tests/ · scripts/           unit tests · privacy check · image capture
```

## Contributing
Issues and pull requests are welcome. See [CONTRIBUTING](.github/CONTRIBUTING.md). Run the tests with
`python3 -m unittest discover -s tests`.

## License
The code is released under the [MIT License](LICENSE). You can use, change and share it freely, including
commercially, as long as the licence notice stays with it. Models and libraries are downloaded at install time under
their own licences; see [docs/THIRD_PARTY.md](docs/THIRD_PARTY.md).
