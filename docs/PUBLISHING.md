# Making the repository public

The repository is designed to be public from day one: it contains no personal data, no machine paths and no secrets.
Everything user-specific lives outside it (`~/.config/…`, `~/.local/state/…`) and is created at install time.

## Checklist
1. `sh scripts/privacy-check.sh` passes. CI runs it on every push.
2. `python3 -m unittest discover -s tests` passes.
3. A fresh install works: `git clone … && ./install.sh`, then `voicekit doctor` shows all ✅.
4. Make it public: `gh repo edit --visibility public --accept-visibility-change-consequences`
5. Optional, once public: add a one-line install to the README, because the raw file is now reachable without a login:
   ```sh
   curl -fsSL https://raw.githubusercontent.com/gobind-singh/claude-voice-kit/main/install.sh | sh
   ```
   `install.sh` already supports this. When run on its own, it clones the repo to `~/.claude-voice-kit` and installs.
6. Optional: add topics (`gh repo edit --add-topic claude-code,voice,tts,speech-to-text,macos,kokoro,parakeet`).

## Forks
Set `VOICEKIT_REPO` to your fork's URL when using the one-line install, or edit `REPO_URL` in `install.sh`.
