# kokoro-voice

Part of claude-voice-kit. Local, free, natural text-to-speech for Apple Silicon Macs, using the Kokoro-82M model through mlx-audio.
It's a standalone tool and knows nothing about Claude or any other client. Anything that can run a
command (or write to a Unix socket) can use it.

## Use
    kokoro "Hello"                 speak
    kokoro -f notes.md             speak a file (markdown cleaned)
    pbpaste | kokoro               speak clipboard
    kokoro -o out.wav "Hello"      save to file
    kokoro -i "..." / -u "..."     interrupt / urgent (jump queue)
    kokoro --stop | --next | --replay [N] | --status | --voices
    kokoro --tag NAME "..."        label speech; --status shows the playing tag
    kokoro --set-voice bf_emma --set-speed 1.1
    kokoro --set-idle-unload 10    free model memory after 10 quiet minutes (0 = never)
    kokoro --set-idle-exit 20      quit the service after 20 quiet minutes (0 = never); restarts on next use
    kokoro --polite "..."          don't talk over other apps: hold the message and notify instead
    kokoro --held | --play-held [ID] | --drop-held [ID]     held messages
    kokoro --audio-check           which other apps count as "using audio" right now

Voices: names starting `af_`/`am_` are American English and `bf_`/`bm_` are British English. Run `kokoro --voices` to list them all.

## Architecture
```
 kokoro (CLI, stdlib only) ──JSON line──► voiced.py (Unix socket ~/.local/state/kokoro-voice/voiced.sock)
   └─ starts the service if it's not running     │
                                                  ├─ main thread:   Kokoro model (MLX), text → wav segments
                                                  ├─ server thread: speak / synth / stop / replay / status / voices
                                                  └─ player thread: plays segments in order with afplay
```
- **Queue:** messages play one after another. `-u` (urgent) jumps ahead of queued items, and `-i` stops current speech first.
- **Replay:** the last 10 messages are kept in `~/.local/state/kokoro-voice/history.json`, so replay works after a restart.
- **Text cleaning (markdown to speech):** headings become sections with a short pause, bullets are read line by line,
  table rows become "column: value", code blocks are announced as "Code block skipped", paths are shortened to the
  file name, URLs become "link", and symbols (⌃ ⌥ ⌘ ✅ ❌ → …) are spoken as words. `--raw` turns this off.
- **Sections:** `--next` stops the current audio and jumps to the next heading (or the next message).
- **Tags:** clients can label speech (`--tag`). `--status` reports the tag that is playing, so a client can
  toggle its own speech without stopping other speech.

## Configuration (`~/.config/kokoro-voice/config.json`)
| Key | Default | Meaning |
|---|---|---|
| `voice` | `af_heart` | default voice |
| `speed` | `1.0` | speaking speed |
| `idle_unload_minutes` | `10` | free the model's memory after this many quiet minutes (0 = never) |
| `idle_exit_minutes` | `20` | quit the whole service after this many quiet minutes (0 = never) |
| `when_other_audio` | `hold` | `hold`: polite messages wait while another app plays or records audio; `play`: always speak |
| `ignore_output_processes` | `[]` | apps that keep a silent output channel open; their output is ignored, their microphone use still counts |
| `ignore_processes` | `coreaudiod` | apps that never count as "other audio" |
| `held_expire_minutes` | `30` | how long held messages are kept |
| `notify_command` | – | command run with a held message (base64 JSON), e.g. to show a notification |

### Idle policy (why 10 then 20)
| Quiet for | State | Memory | First words after |
|---|---|---|---|
| 0–10 min | model loaded | ~650–760 MB | < 1 s |
| 10–20 min | model unloaded, libraries stay | ~270 MB | ~1.5 s |
| 20+ min | service quit | 0 MB | ~4–5 s |

The LaunchAgent uses `KeepAlive = {SuccessfulExit = false}`. A crash is restarted at once, but an idle quit
(exit code 0) is not. The `kokoro` command starts the service again on the next request. `kokoro --stop`
never wakes it.

## Dependencies and why
| Package | Why |
|---|---|
| `mlx-audio` | runs Kokoro on the Apple GPU (MLX) |
| `misaki[en]` | turns English text into phonemes (pronunciation) |
| `en-core-web-sm` | the small spaCy grammar model misaki uses for part-of-speech tagging |
| `soundfile` | writes wav files |
| **PyTorch** (pulled in by `misaki[en]`) | **kept on purpose**, see below |

**PyTorch is kept on purpose.** Many English words are spelled the same but pronounced differently (*read*: "reed"/"red";
*lead*: "leed"/"led"). misaki picks the pronunciation from a grammar model's part-of-speech tags. The default small
model (`en_core_web_sm`) sometimes guesses wrong. For example, it says "I read books every day" in the past tense, and the metal
"lead" like the verb. misaki has an optional transformer mode (`trf=True` with `en_core_web_trf`) that understands more
context, and that mode needs PyTorch. It isn't switched on by default, but PyTorch stays installed so it can be enabled
without changing dependencies. Cost: ~130 MB of extra memory while the service runs, because spaCy's `thinc` loads PyTorch
whenever it's installed, and ~500 MB of disk.

## Parts
- `voiced.py`: the service (log: `~/.local/state/kokoro-voice/voiced.log`)
- `kokoro`: the command (Python standard library only)
- `audio_activity.py`: which apps are using audio, via CoreAudio's per-process list (macOS 14.2+, ctypes)
- LaunchAgent `~/Library/LaunchAgents/com.claude-voice-kit.kokoro.plist` (installed by `voicekit install` from `launchd/kokoro.plist.template`): starts at login, restarts after a crash, runs offline (`HF_HUB_OFFLINE=1`)

## Install / uninstall
Part of claude-voice-kit: run `./install.sh` / `./uninstall.sh` in the project root.

## Platform
macOS on Apple Silicon (MLX, `afplay`, launchd, CoreAudio). A Windows or Linux port would need a different engine
(e.g. kokoro-onnx) and audio player.
