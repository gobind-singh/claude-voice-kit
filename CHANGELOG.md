# Changelog

## Unreleased
- Polite mode checks whether other apps are **audibly** playing, not just whether their audio channel is open, using a
  small `audio-level` helper (needs System Audio Recording permission). A silent browser tab (e.g. Discord in Safari)
  or dictation app no longer holds every message. macOS's system-sound helper is ignored by default.
- Right ⌘ push-to-talk starts listening only after the key is held alone for 0.3 s (with a soft tick), so shortcuts
  like Right ⌘ + Delete no longer stop speech or open the microphone. Key, delay and tick are configurable
  (`push_to_talk`).
- Licence changed to MIT.

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
