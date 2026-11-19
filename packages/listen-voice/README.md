# listen-voice

Part of claude-voice-kit. Local push-to-talk speech-to-text for Apple Silicon Macs, using NVIDIA's Parakeet model through
[transcribe.cpp](https://github.com/handy-computer/transcribe.cpp). Like kokoro-voice it's standalone: nothing in it is
Claude-specific.

## Use
    listen-voice -f speech.wav       transcribe a file
    listen-voice --start / --stop    push-to-talk: start recording, then stop and print the text
    listen-voice --cancel            stop and discard
    listen-voice --record 5          record 5 seconds, then print the text
    listen-voice --raw | --json      unpolished text / full result (text, raw, seconds, ms)
    listen-voice --wake on|off       hands-free: listen continuously for the wake phrase
    listen-voice --status

## How it works
```
 listen-voice (CLI, stdlib only) ──JSON line──► listend.py (Unix socket ~/.local/state/listen-voice/listend.sock)
                                                 ├─ recorder.py child process: the ONLY place the mic is opened;
                                                 │  it exits when recording ends, so macOS always releases the mic
                                                 ├─ Parakeet model (transcribe.cpp, Metal), ~0.1 s per phrase
                                                 ├─ polish.py: spacing, capitals, "." / "?", vocabulary and corrections
                                                 └─ wake mode: voice-activity detection → phrase → "hey claude …" → command
```
- **Model reuse:** if [Handy](https://handy.computer) (or anything else) already downloaded the Parakeet GGUF into the
  Hugging Face cache, it's used as-is, so there's no second 700 MB download.
- **Polish:** Parakeet-unified returns text without final punctuation ("is it done"). `polish.py` fixes spacing,
  capitals and the final "." or "?". It knows "Do you…" is a question and "Do everything…" an instruction.
- **Idle:** the model unloads after 10 quiet minutes and the service quits after 20. It starts again on the next request.

## Configuration (`~/.config/listen-voice/config.json`)
| Key | Default | Meaning |
|---|---|---|
| `model_repo` / `model_file` / `model_path` | Parakeet unified EN Q8 | which GGUF to use (`model_path` overrides) |
| `input_device` | system default | microphone |
| `vocabulary` | `[]` | exact spellings to enforce, e.g. `["herdr", "Kokoro"]` |
| `aliases` | `{}` | corrections, e.g. `{"harder": "herdr"}` |
| `wake.words` | `hey claude`, `okay claude` | wake phrases |
| `wake.command` | – | command run with the phrase after the wake word |
| `wake.stop_words` / `wake.barge_in_command` | `stop`, `quiet`, … | phrase that interrupts speech, and what it runs |
| `idle_unload_minutes` / `idle_exit_minutes` | 10 / 20 | idle timers |
