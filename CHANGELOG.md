# Changelog

## Unreleased
- Polite mode checks whether other apps are **audibly** playing, not just whether their audio channel is open, using a
  small `audio-level` helper (needs System Audio Recording permission). A silent browser tab (e.g. Discord in Safari)
  or dictation app no longer holds every message. macOS's system-sound helper is ignored by default.
- Right ⌘ push-to-talk counts as a voice command only after the key is held alone for 0.3 s, so shortcuts like
  Right ⌘ + Delete no longer stop speech or flash the pop-up. Key, delay and tick are configurable (`push_to_talk`).
- Push-to-talk no longer loses the first or last word: the microphone starts on key-down (discarded for shortcuts),
  the "Listening…" pop-up and tick appear only once it is really recording, Claude's own voice is trimmed from the
  start, and recording continues 0.15 s after release. `voicekit doctor` reports how fast the microphone starts.
- New on-screen HUD replaces Hammerspoon's plain alert box: our own line icons, a colour for each state
  (listening, transcribing, done, problem), animated listening bars and spinner, fades in and out.
- New menu bar icon (sound bars): voice on/off, hands-free, held-message count, and a menu with the hotkey actions.
- Held messages are quiet: no macOS notification. The menu bar icon lists each one with Play / Approve / Deny /
  Dismiss (`"ui": {"held": "notification"}` brings the notification back).
- No emoji in on-screen messages. `"ui": {"hud": false, "menubar": false}` in config.json turns either off.
- Shortcuts can be changed: from the menu bar (choose one, press the new keys), with `voicekit keys`, or in
  config.json (`shortcuts`). Clashes with macOS, common app shortcuts and other kit shortcuts are refused.
- Choose the voice (with a spoken sample) and the speed from the menu bar icon.
- The menu bar icon is placed directly left of the system icons so the MacBook notch doesn't hide it, and
  Hammerspoon's own icon is hidden to save space.
- Licence changed to MIT.
- README shows the kit's own logo, icons, HUD pop-ups and menu, with a 3-step guide to using it. The images are
  drawn from the kit's own code by `scripts/readme-images.sh`.

## 0.1.0: first release
- Spoken briefings for every Claude Code reply, written by Claude Haiku and spoken with a local Kokoro voice.
- Spoken plan summaries for plan approvals, plus a full read of any reply or plan (⌃⌥F) with section skipping.
- Spoken alerts for permission prompts, questions and failures.
- Voice commands with Right ⌘ push-to-talk, using local Parakeet speech-to-text with text polishing.
- Multi-agent control (status, approvals, instructions, switching, starting agents, leader mode) via herdr, a voice
  channel (Claude Code Channels) or the front window.
- Hands-free mode: "hey Claude" wake phrase, spoken approvals, "stop" to interrupt.
- Polite mode: holds speech while other audio plays and shows a notification with Play / Approve / Deny.
- One-command install and uninstall, `voicekit doctor`, unit tests, privacy check, CI.
- Safety: hooks can never block Claude Code; risky commands need "yes, approve"; every voice action is audited.
