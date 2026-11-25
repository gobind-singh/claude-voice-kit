#!/usr/bin/env python3
"""Keyboard shortcuts for claude-voice-kit: one list, used by the hotkeys, the menu bar, the docs and doctor.

Each action has a default shortcut. Change one in ~/.config/claude-voice-kit/config.json:
    "shortcuts": {"read_full": "cmd+shift+F", "read_selection": null}     (null = off)
or with `voicekit keys set read_full cmd+shift+F`, or from the menu bar icon (Keyboard shortcuts → Change).

Shortcut format: modifiers and a key joined with "+", e.g. ctrl+alt+V, cmd+shift+F1, ctrl+alt+space.
Modifiers: ctrl (control, ⌃), alt (option, opt, ⌥), shift (⇧), cmd (command, ⌘). Function keys F1–F20 may be
used without a modifier; every other key needs at least one modifier.

  python3 shortcuts.py --json      the effective shortcuts as JSON (read by Hammerspoon)
"""
import json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import voicekit_common as vk

# (id, label, default). Order = order in menus and docs.
ACTIONS = [
    ("voice_toggle", "Claude voice on/off", "ctrl+alt+V"),
    ("read_full", "Read the whole last reply", "ctrl+alt+F"),
    ("next_section", "Skip to the next section", "ctrl+alt+N"),
    ("replay", "Replay the last message", "ctrl+alt+R"),
    ("stop", "Stop speaking", "ctrl+alt+S"),
    ("read_selection", "Read selected text aloud", "ctrl+alt+K"),
    ("handsfree", "Hands-free on/off", "ctrl+alt+H"),
    ("play_held", "Play held messages", "ctrl+alt+P"),
]
DEFAULTS = {a: d for a, _, d in ACTIONS}
LABELS = {a: label for a, label, _ in ACTIONS}

MOD_ALIASES = {"ctrl": "ctrl", "control": "ctrl", "⌃": "ctrl", "alt": "alt", "option": "alt", "opt": "alt",
               "⌥": "alt", "shift": "shift", "⇧": "shift", "cmd": "cmd", "command": "cmd", "⌘": "cmd"}
MOD_ORDER = ["ctrl", "alt", "shift", "cmd"]
MOD_SYMBOL = {"ctrl": "⌃", "alt": "⌥", "shift": "⇧", "cmd": "⌘"}
NAMED_KEYS = {"space": "Space", "return": "↩", "enter": "↩", "tab": "⇥", "escape": "⎋", "delete": "⌫",
              "forwarddelete": "⌦", "home": "↖", "end": "↘", "pageup": "⇞", "pagedown": "⇟",
              "left": "←", "right": "→", "up": "↑", "down": "↓"}
PUNCTUATION = set("`-=[]\\;',./")

# Shortcuts macOS or nearly every app already uses: refused so the kit never steals them.
RESERVED = {
    frozenset({"cmd"}): set("QWERTYUIOPASDFGHJKLZXCVBNM") | {"tab", "space", "`", ","},
    frozenset({"cmd", "shift"}): {"3", "4", "5", "Z", "N", "T"},
    frozenset({"cmd", "alt"}): {"escape", "D"},
    frozenset({"ctrl", "cmd"}): {"Q", "F", "space"},
    frozenset({"ctrl"}): {"space", "up", "down", "left", "right"},
    frozenset({"cmd", "ctrl", "shift"}): {"3", "4"},
}


class ShortcutError(ValueError):
    pass


def parse(text):
    """'Ctrl+Option+v' → ('ctrl', 'alt'), 'V'. Raises ShortcutError with a readable message."""
    if not isinstance(text, str) or not text.strip():
        raise ShortcutError("empty shortcut")
    spelled = text.strip()
    for sym, name in (("⌃", "ctrl+"), ("⌥", "alt+"), ("⇧", "shift+"), ("⌘", "cmd+")):
        spelled = spelled.replace(sym, name)
    parts = [p.strip() for p in re.split(r"\s*\+\s*", spelled) if p.strip()]
    if text.strip().endswith("++"):
        parts.append("+")
    mods, keys = set(), []
    for p in parts:
        m = MOD_ALIASES.get(p.lower())
        if m:
            mods.add(m)
        else:
            keys.append(p)
    if len(keys) != 1:
        raise ShortcutError(f"'{text}': give exactly one key after the modifiers, e.g. ctrl+alt+V")
    key = keys[0]
    low = key.lower()
    if re.fullmatch(r"f([1-9]|1[0-9]|20)", low):
        key = low.upper()
    elif low in NAMED_KEYS:
        key = low
    elif len(key) == 1 and (key.isalnum() or key in PUNCTUATION):
        key = key.upper()
    else:
        raise ShortcutError(f"'{key}' isn't a key name I know (letters, digits, F1–F20, space, return, tab, "
                            "arrows, or punctuation)")
    if not mods and not key.startswith("F"):
        raise ShortcutError(f"'{text}' needs a modifier (ctrl, alt/option, shift or cmd) so normal typing isn't "
                            "taken over")
    if mods == {"shift"} and not key.startswith("F"):
        raise ShortcutError(f"'{text}': shift alone only changes what you type; add ctrl, alt or cmd")
    return tuple(m for m in MOD_ORDER if m in mods), key


def normalize(text):
    mods, key = parse(text)
    return "+".join([*mods, key])


def pretty(text):
    """'ctrl+alt+V' → '⌃⌥V'. None → 'off'."""
    if not text:
        return "off"
    mods, key = parse(text)
    return "".join(MOD_SYMBOL[m] for m in mods) + NAMED_KEYS.get(key, key)


def reserved(text):
    mods, key = parse(text)
    return key in RESERVED.get(frozenset(mods), set())


def effective(cfg=None):
    """{action: 'ctrl+alt+V' or None} with the user's changes applied. Invalid entries fall back to the default."""
    user = (cfg if cfg is not None else vk.load_config()).get("shortcuts") or {}
    out = {}
    for a in DEFAULTS:
        v = user.get(a, DEFAULTS[a])
        if v is None or v is False or v == "":
            out[a] = None
            continue
        try:
            out[a] = normalize(v)
        except ShortcutError:
            out[a] = DEFAULTS[a]
    return out


def check_change(action, combo, cfg=None):
    """Validate setting `action` to `combo` (None = off). Returns the normalized combo; raises ShortcutError."""
    if action not in DEFAULTS:
        raise ShortcutError(f"unknown action '{action}'. Actions: {', '.join(DEFAULTS)}")
    if combo is None:
        return None
    combo = normalize(combo)
    if reserved(combo):
        raise ShortcutError(f"{pretty(combo)} is already used by macOS or most apps; pick another")
    for other, cur in effective(cfg).items():
        if other != action and cur == combo:
            raise ShortcutError(f"{pretty(combo)} is already used for “{LABELS[other]}”")
    return combo


def save(action, combo):
    """Set one shortcut (None = off) in the user's config file. Returns the saved value."""
    cfg = _user_config()
    combo = check_change(action, combo, vk._merge(vk.DEFAULTS, cfg))
    cfg.setdefault("shortcuts", {})[action] = combo
    vk.save_config(cfg)
    return combo


def reset(action=None):
    cfg = _user_config()
    sc = cfg.get("shortcuts") or {}
    if action:
        if action not in DEFAULTS:
            raise ShortcutError(f"unknown action '{action}'")
        sc.pop(action, None)
    else:
        sc = {}
    if sc:
        cfg["shortcuts"] = sc
    else:
        cfg.pop("shortcuts", None)
    vk.save_config(cfg)


def _user_config():
    """The user's own config.json (only their changes), not merged with defaults."""
    try:
        with open(vk.CONFIG_FILE) as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def as_list(cfg=None):
    eff = effective(cfg)
    return [{"id": a, "label": label, "combo": eff[a], "pretty": pretty(eff[a]), "default": d,
             "changed": eff[a] != normalize(d)} for a, label, d in ACTIONS]


if __name__ == "__main__":
    if "--json" in sys.argv:
        print(json.dumps(as_list()))
    else:
        for s in as_list():
            print(f"  {s['pretty']:10} {s['label']}")
