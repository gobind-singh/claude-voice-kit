# Contributing

Thanks for helping! Bug reports, ideas and pull requests are all welcome.

## Before you start
- **Bugs:** open an issue using the *Bug report* template and include the output of `voicekit doctor`.
- **Bigger changes:** open an issue first to agree on the approach. That keeps reviews short.

## Development setup
```sh
git clone https://github.com/gobind-singh/claude-voice-kit.git && cd claude-voice-kit
./install.sh                                  # installs from this folder; re-run after changes to hooks/services
python3 -m unittest discover -s tests         # unit tests (no audio, models or network)
sh scripts/privacy-check.sh                   # no personal paths, e-mails or secrets
```
`docs/architecture.md` explains how the parts fit together and why they're built that way.

## Guidelines
- **Hooks must never block Claude Code.** They exit with code 0 on any error, return quickly, and do slow work in the
  background.
- **Keep the packages standalone.** `packages/kokoro-voice` and `packages/listen-voice` must not contain Claude-specific code.
- **Nothing personal or machine-specific in the repo.** Settings belong in `~/.config/…` and state in `~/.local/state/…`.
- **Plain Python standard library** for scripts that run on every event (hooks, CLIs). Heavy dependencies go only in the
  two package environments.
- Add or update a test in `tests/` when you fix a bug, and keep the docs in step with behaviour.

## Pull requests
- Keep each PR to one change, with a clear title and a short description of *why*.
- CI (compile, unit tests, privacy check) must pass.
- By contributing, you agree to license your contribution under the [MIT License](../LICENSE).

## How changes reach `main`
- `main` is protected: no direct pushes, force-pushes or deletion. Every change goes through a pull request.
- A pull request needs the **ci** check to pass, one approving review from a code owner (approvals are reset by new
  commits), and all review conversations resolved. Pull requests are squash-merged, so history stays linear.
- Workflows from first-time contributors' forks run only after a maintainer approves them.
