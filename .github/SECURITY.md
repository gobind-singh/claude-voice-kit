# Security policy

claude-voice-kit can answer Claude Code permission prompts and send instructions to coding agents by voice, so
security issues matter here.

## Reporting a vulnerability
Please **don't open a public issue**. Use GitHub's private reporting instead: *Security → Report a vulnerability* on
this repository. Include steps to reproduce and the impact. You'll get a reply within a week.

## In scope
- A way to approve a permission prompt, or send input to a session, that the user didn't intend: wrong session, wrong
  command, or bypassing the "yes, approve" check for risky commands.
- Injection through text the kit passes on (to AppleScript, Hammerspoon, shells or the voice channel).
- Anything that makes a hook block or crash Claude Code, or leaves the microphone open without the user's knowledge.
- Personal data being written into the repository or sent anywhere other than documented in the README.
