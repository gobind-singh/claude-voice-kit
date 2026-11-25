-- claude-voice-kit: Hammerspoon hotkeys.
-- Loaded from ~/.hammerspoon/init.lua by one line that install.sh adds:
--   dofile("<kit>/hammerspoon/voice-kit.lua")
--
-- Mac keys: ⌃ = Control, ⌥ = Option (the key cross-platform docs call "Alt").
--   Control+Option+V (⌃⌥V)  Claude voice on/off (briefings + alerts)
--   Control+Option+F (⌃⌥F)  read the WHOLE last Claude reply (press again to stop)
--   Control+Option+N (⌃⌥N)  skip to the next section of what is being read
--   Control+Option+R (⌃⌥R)  replay the last spoken message
--   Control+Option+S (⌃⌥S)  stop speaking
--   Control+Option+K (⌃⌥K)  read the selected text in any app aloud
--   Control+Option+H (⌃⌥H)  hands-free mode on/off (voice approvals + "hey Claude" wake phrase)
--   Control+Option+P (⌃⌥P)  play messages held back while other audio was playing
--   Right Command (hold)    after 0.3 s alone: speak a voice command; release to run it (the HUD shows the result and what was heard)
--   fn                      stops speech (the usual dictation key, so dictating interrupts it)
--
-- On screen: hud.lua draws the pop-up (HUD), menubar.lua the menu bar icon, icons.lua the icons.

require("hs.ipc")  -- lets the `hs` command talk to Hammerspoon (used by `voicekit doctor`)

-- Loading this file again (without a full Hammerspoon reload) replaces the previous copy cleanly.
if voiceKit then
  local old = voiceKit
  for _, h in ipairs(old.hotkeys or {}) do pcall(function() h:delete() end) end
  for _, k in ipairs({ "pttWatcher", "fnWatcher", "recorder" }) do pcall(function() old[k]:stop() end) end
  for _, k in ipairs({ "armTimer", "slowTimer" }) do if old[k] then pcall(function() old[k]:stop() end) end end
  if old.hud then pcall(old.hud.destroy) end
  if old.menu then pcall(old.menu.stop) end
end

local VK = {}
local here = debug.getinfo(1, "S").source:sub(2)
VK.dir = here:match("(.*)/hammerspoon/[^/]+$")
VK.kokoro = VK.dir .. "/packages/kokoro-voice/kokoro"
VK.cvoice = VK.dir .. "/claude/cvoice"
-- The kit's own Python (always present after install); system Pythons only as a fallback.
VK.python = VK.dir .. "/packages/kokoro-voice/.venv/bin/python"
if not hs.fs.attributes(VK.python) then
  VK.python = hs.fs.attributes("/opt/homebrew/bin/python3") and "/opt/homebrew/bin/python3" or "/usr/bin/python3"
end
-- The `hs` command-line tool lets the kit talk to Hammerspoon (notifications, doctor). Homebrew's
-- Hammerspoon cask links it; for other installs, add it here.
if not hs.fs.attributes("/opt/homebrew/bin/hs") and not hs.fs.attributes("/usr/local/bin/hs") then
  pcall(function() hs.ipc.cliInstall("/opt/homebrew") end)
end

local function run(script, args, onDone)
  local full = { script }
  for _, a in ipairs(args) do table.insert(full, a) end
  hs.task.new(VK.python, onDone, full):start()
end
local function kokoro(args) run(VK.kokoro, args) end
local function cvoice(args, onDone) run(VK.cvoice, args, onDone) end

-- UI settings: "ui" in ~/.config/claude-voice-kit/config.json, e.g. {"ui": {"hud": true, "menubar": true}}.
-- "hud": false brings back Hammerspoon's plain alert box; "menubar": false hides the menu bar icon.
local configDir = os.getenv("VOICEKIT_CONFIG_DIR") or (os.getenv("HOME") .. "/.config/claude-voice-kit")
local ui = (hs.fs.attributes(configDir .. "/config.json") and (hs.json.read(configDir .. "/config.json") or {}).ui) or {}
local Icons = dofile(VK.dir .. "/hammerspoon/icons.lua")
VK.hud = dofile(VK.dir .. "/hammerspoon/hud.lua")(Icons)
VK.hud.useAlert = ui.hud == false
local HUD = VK.hud
local function refreshMenu() if VK.menu then VK.menu.refresh() end end

-- Actions shared by the hotkeys and the menu bar menu.
function VK.toggleVoice()
  cvoice({ "toggle" }, function(_, out)
    if out and out:find(": on", 1, true) then
      HUD.show("info", "Claude voice on", nil, 2, { icon = "speaker" })
      kokoro({ "-i", "--", "Claude voice on." })
    else
      HUD.show("muted", "Claude voice off", nil, 2)
    end
    refreshMenu()
  end)
end
function VK.toggleHandsfree()
  run(VK.voicectl, { "handsfree", "toggle" }, function(_, out)
    if (out or ""):find("Hands%-free on") then
      HUD.show("info", "Hands-free on", "Approvals are asked out loud · say \u{201C}hey Claude\u{201D}", 3, { icon = "headphones" })
    else
      HUD.show("muted", "Hands-free off", nil, 2, { icon = "headphones" })
    end
    refreshMenu()
  end)
end
function VK.readFull() cvoice({ "full", "--toggle" }) end
function VK.nextSection() kokoro({ "--next" }) end
function VK.replay() kokoro({ "--replay" }) end
function VK.stopSpeaking() kokoro({ "--stop" }) end
function VK.playHeld() kokoro({ "--play-held" }) end
VK.run = run
-- Voice and speed, chosen from the menu bar: saved as kokoro's defaults, with a short sample.
function VK.setVoice(voice, name)
  run(VK.kokoro, { "--set-voice", voice }, function(code)
    if code ~= 0 then return HUD.show("error", "Couldn't change the voice", voice, 3) end
    HUD.show("ok", "Voice: " .. name, nil, 2, { icon = "speaker" })
    kokoro({ "-i", "--voice", voice, "--", "Hi, I'm " .. name .. ". This is how Claude will sound." })
    if VK.menu then VK.menu.refresh() end
  end)
end
function VK.setSpeed(speed)
  run(VK.kokoro, { "--set-speed", tostring(speed) }, function(code)
    if code ~= 0 then return HUD.show("error", "Couldn't change the speed", nil, 3) end
    local label = speed == 1.0 and "Normal" or string.format("%.1f\u{00D7}", speed)
    HUD.show("ok", "Speed: " .. label, nil, 2, { icon = "speaker" })
    kokoro({ "-i", "--speed", tostring(speed), "--", "This is the new speed." })
  end)
end

function VK.readSelection()
  local saved = hs.pasteboard.getContents()
  local before = hs.pasteboard.changeCount()
  hs.eventtap.keyStroke({ "cmd" }, "c")
  hs.timer.doAfter(0.25, function()
    if hs.pasteboard.changeCount() == before then
      HUD.show("error", "No text selected", "Select some text, then press " .. VK.keyLabel("read_selection"), 2.5)
      return
    end
    local text = hs.pasteboard.getContents()
    if saved then hs.pasteboard.setContents(saved) end
    if text and #text > 0 then
      HUD.show("info", "Reading selection aloud", nil, 1.5, { icon = "speaker" })
      kokoro({ "-i", "--", text })
    end
  end)
end

-- Hold Right Command (⌘) to speak a voice command; release to transcribe it.
-- Listening starts only after the key has been held ALONE for hold_ms (default 0.3 s), with a soft
-- tick. Shortcuts like Right ⌘ + Delete or Right ⌘ + C are typed within that time, so they never
-- stop speech, open the microphone or show the strip. Pressing another key while recording cancels it.
-- Settings: "push_to_talk" in ~/.config/claude-voice-kit/config.json
--   {"key": "right_cmd" | "right_option" | "right_shift" | "right_ctrl", "hold_ms": 300, "cue_sound": "Tink" | ""}
VK.listen = VK.dir .. "/packages/listen-voice/listen"
VK.voicectl = VK.dir .. "/claude/voicectl"
local PTT_KEYS = {             -- keycode and the modifier flag it sets
  right_cmd = { 54, "cmd" }, right_option = { 61, "alt" }, right_shift = { 60, "shift" }, right_ctrl = { 62, "ctrl" },
}
local function pttSettings()
  local s = { key = "right_cmd", hold_ms = 300, cue_sound = "Tink" }
  local ok, cfg = pcall(hs.json.read, os.getenv("HOME") .. "/.config/claude-voice-kit/config.json")
  if ok and type(cfg) == "table" and type(cfg.push_to_talk) == "table" then
    for k, v in pairs(cfg.push_to_talk) do s[k] = v end
  end
  if not PTT_KEYS[s.key] then s.key = "right_cmd" end
  s.hold_ms = math.max(0, tonumber(s.hold_ms) or 300)
  return s
end
VK.ptt = pttSettings()
local PTT_KEY, PTT_FLAG = PTT_KEYS[VK.ptt.key][1], PTT_KEYS[VK.ptt.key][2]
local PTT_LABEL = ({ right_cmd = "Right \u{2318}", right_option = "Right \u{2325}", right_shift = "Right \u{21E7}",
                     right_ctrl = "Right \u{2303}" })[VK.ptt.key]
local OTHER_FLAGS = { "cmd", "alt", "ctrl", "shift", "fn" }
VK.recording = false
VK.armTimer = nil              -- running while the key is held but listening hasn't started yet
-- On-screen HUD: what was heard, then what happened (title = result, detail = what was heard).
local function quoted(text) return "\u{201C}" .. text .. "\u{201D}" end
VK.onCommand = function(text)
  HUD.show("transcribing", quoted(text), "Working on it\u{2026}", 30)
  run(VK.voicectl, { text }, function(code, out)
    local result = (out or ""):gsub("%s+$", "")
    if #result > 0 then
      HUD.show(code == 0 and "ok" or "error", result, "Heard " .. quoted(text), 5)
    else
      HUD.show(code == 0 and "ok" or "error", code == 0 and "Done" or "That didn't work", "Heard " .. quoted(text), 4)
    end
    refreshMenu()
  end)
end

-- Hands-free survives restarts: turn the wake phrase back on if it was on.
if hs.fs.attributes(os.getenv("HOME") .. "/.local/state/claude-voice-kit/handsfree") then
  run(VK.listen, { "--wake", "on" })
end
-- Push-to-talk, step by step:
--   key down (alone)  → the microphone starts quietly at once, so the first word is never lost
--   held alone for hold_ms → it's a voice command: Claude's speech stops, and the "Listening…" pop-up and
--                       tick appear as soon as the microphone is really recording (never before)
--   another key or modifier before then (Right ⌘ + Delete) → the audio is thrown away, nothing is shown
--   released          → recording continues 0.15 s (listen-voice tail_ms), then it's transcribed
VK.pttState = nil              -- nil | "arming" | "recording"
local function stopTimers()
  if VK.armTimer then VK.armTimer:stop(); VK.armTimer = nil end
  if VK.slowTimer then VK.slowTimer:stop(); VK.slowTimer = nil end
end
local function showListening()
  if VK.pttState ~= "recording" or not VK.micLive or VK.pttShown then return end
  VK.pttShown = true
  if VK.slowTimer then VK.slowTimer:stop(); VK.slowTimer = nil end
  if VK.ptt.cue_sound and VK.ptt.cue_sound ~= "" then
    local cue = hs.sound.getByName(VK.ptt.cue_sound)
    if cue then cue:volume(0.4):play() end
  end
  HUD.show("listening", "Listening\u{2026}", "Release " .. PTT_LABEL .. " when done", 60)
end
local function cancelPtt()
  stopTimers()
  if VK.pttState then run(VK.listen, { "--cancel" }) end
  if VK.pttShown then HUD.hide(0.1) end
  VK.pttState, VK.recording, VK.micLive, VK.pttShown = nil, false, false, false
end
local function confirmPtt()                          -- held long enough: it's a voice command
  VK.armTimer = nil
  VK.pttState, VK.recording = "recording", true
  kokoro({ "--stop" })                                 -- stop Claude talking over you
  if VK.ttsWasSpeaking then run(VK.listen, { "--trim" }) end   -- drop Claude's voice from the recording
  showListening()
  if not VK.pttShown then                              -- mic still starting (service waking up)
    VK.slowTimer = hs.timer.doAfter(0.6, function()
      VK.slowTimer = nil
      if VK.pttState == "recording" and not VK.pttShown then
        HUD.show("transcribing", "Starting microphone\u{2026}", "Speak after the tick", 10)
      end
    end)
  end
end
local function beginPtt()
  VK.pttState, VK.micLive, VK.pttShown, VK.ttsWasSpeaking = "arming", false, false, false
  run(VK.kokoro, { "--is-speaking" }, function(code) VK.ttsWasSpeaking = code == 0 end)
  run(VK.listen, { "--start", "--wait-live" }, function(code, out)
    if VK.pttState and code == 0 and (out or ""):find("^live") then
      VK.micLive = true
      showListening()
    end
  end)
  if VK.ptt.hold_ms == 0 then confirmPtt()
  else VK.armTimer = hs.timer.doAfter(VK.ptt.hold_ms / 1000, confirmPtt) end
end
local function onlyPttHeld(f)
  if not f[PTT_FLAG] then return false end
  for _, m in ipairs(OTHER_FLAGS) do
    if m ~= PTT_FLAG and f[m] then return false end
  end
  return true
end
VK.pttWatcher = hs.eventtap.new({ hs.eventtap.event.types.flagsChanged, hs.eventtap.event.types.keyDown }, function(e)
  local t = e:getType()
  if t == hs.eventtap.event.types.keyDown then
    if VK.pttState then cancelPtt() end              -- a shortcut (Right ⌘ + Delete) or typing: discard
    return false
  end
  local f = e:getFlags()
  if e:getKeyCode() ~= PTT_KEY then
    if VK.pttState == "arming" and not onlyPttHeld(f) then cancelPtt() end   -- another modifier joined in
    return false
  end
  if onlyPttHeld(f) and not VK.pttState then
    beginPtt()
  elseif not f[PTT_FLAG] and VK.pttState == "arming" then   -- quick tap: released before it counted
    cancelPtt()
  elseif not f[PTT_FLAG] and VK.pttState == "recording" then
    stopTimers()
    VK.pttState, VK.recording, VK.micLive, VK.pttShown = nil, false, false, false
    HUD.show("transcribing", "Transcribing\u{2026}", nil, 15)
    run(VK.listen, { "--stop" }, function(code, out)
      local text = (out or ""):gsub("^%s+", ""):gsub("%s+$", "")
      if code == 0 and #text > 0 then VK.onCommand(text)
      else HUD.show("error", "Didn't catch that", "Hold " .. PTT_LABEL .. ", wait for the tick, then speak", 2.5) end
    end)
  end
  return false
end)
VK.pttWatcher:start()

-- Held messages: automatic messages that weren't spoken because another app was playing or
-- recording audio. kokoro calls claude/notify_held.py, which calls this.
-- Buttons: Play (speak it now), extra actions such as Approve / Deny, and Dismiss (closes the
-- notification; the message stays on ⌃⌥P until it expires).
-- Held messages are quiet: no system notification. The menu bar icon shows the count and lists
-- each message with Play / Approve / Deny / Dismiss, and the HUD briefly says one was held.
-- ("ui": {"held": "notification"} brings back a macOS notification with buttons.)
VK.kokoroDo = kokoro   -- run `kokoro` with arguments (VK.kokoro is its path)
function VK.runHeldAction(item, a)
  local args = {}
  for i = 2, #a.command do table.insert(args, a.command[i]) end
  run(a.command[1], args, function() refreshMenu() end)
  kokoro({ "--drop-held", item.id })
end
local function notifyHeldSystem(item)
  local labels = {}
  for _, a in ipairs(item.actions or {}) do table.insert(labels, a.label) end
  local n = hs.notify.new(function(note)
    local t, types = note:activationType(), hs.notify.activationTypes
    if t == types.additionalActionClicked then
      local chosen = note:additionalActivationAction()
      for _, a in ipairs(item.actions or {}) do
        if a.label == chosen then VK.runHeldAction(item, a) end
      end
    elseif t == types.actionButtonClicked or t == types.contentsClicked then
      kokoro({ "--play-held", item.id })
    end
  end, {
    title = "Claude \u{00B7} held (" .. (item.why or "other audio") .. ")",
    informativeText = item.text, hasActionButton = true, actionButtonTitle = "Play",
    otherButtonTitle = "Dismiss", withdrawAfter = 0,
  })
  if #labels > 0 then
    n:additionalActions(labels)
    pcall(function() n:alwaysShowAdditionalActions(true) end)
  end
  n:send()
  VK.lastHeldNote = n
end
function VK.notifyHeld(b64)
  local item = hs.json.decode(hs.base64.decode(b64))
  if not item then return end
  if ui.held == "notification" then notifyHeldSystem(item) end
  local count = VK.menu and VK.menu.state().held or 1
  local title = count > 1 and (count .. " messages held") or "Message held"
  local hint = (item.actions and #item.actions > 0) and "Answer from the menu bar icon" or (VK.keyLabel("play_held") .. " to play")
  local why = (item.why and #item.why > 0) and item.why or "Other audio was playing"
  HUD.show("info", title, why .. " \u{00B7} " .. hint, 3, { icon = "message" })
  refreshMenu()
end

-- Keyboard shortcuts. The list (actions, defaults, the user's changes) lives in claude/shortcuts.py and
-- ~/.config/claude-voice-kit/config.json ("shortcuts"); `voicekit keys` and the menu bar change it.
VK.actions = {
  voice_toggle = VK.toggleVoice, read_full = VK.readFull, next_section = VK.nextSection, replay = VK.replay,
  stop = VK.stopSpeaking, read_selection = VK.readSelection, handsfree = VK.toggleHandsfree, play_held = VK.playHeld,
}
local FALLBACK_SHORTCUTS = {   -- used only if the shortcut list can't be read
  { id = "voice_toggle", combo = "ctrl+alt+V" }, { id = "read_full", combo = "ctrl+alt+F" },
  { id = "next_section", combo = "ctrl+alt+N" }, { id = "replay", combo = "ctrl+alt+R" },
  { id = "stop", combo = "ctrl+alt+S" }, { id = "read_selection", combo = "ctrl+alt+K" },
  { id = "handsfree", combo = "ctrl+alt+H" }, { id = "play_held", combo = "ctrl+alt+P" },
}
local KEYNAMES = { space = "space", ["return"] = "return", tab = "tab", escape = "escape", delete = "delete",
  forwarddelete = "forwarddelete", home = "home", ["end"] = "end", pageup = "pageup", pagedown = "pagedown",
  left = "left", right = "right", up = "up", down = "down" }
local function splitCombo(combo)
  local mods, key = {}, nil
  for part in combo:gmatch("[^+]+") do
    if part == "ctrl" or part == "alt" or part == "shift" or part == "cmd" then table.insert(mods, part)
    else key = part end
  end
  if key and #key == 1 then key = key:lower()
  elseif key and key:match("^F%d+$") then key = key:lower()
  elseif key then key = KEYNAMES[key] or key end
  return mods, key
end
function VK.loadShortcuts()
  local out, ok = hs.execute(string.format('"%s" "%s/claude/shortcuts.py" --json', VK.python, VK.dir))
  local list = ok and hs.json.decode(out or "") or nil
  VK.shortcuts = type(list) == "table" and list or FALLBACK_SHORTCUTS
  return VK.shortcuts
end
function VK.keyLabel(id)
  for _, s in ipairs(VK.shortcuts or {}) do if s.id == id then return s.pretty or s.combo or "off" end end
  return "off"
end
function VK.bindShortcuts()
  for _, h in ipairs(VK.hotkeys or {}) do pcall(function() h:delete() end) end
  VK.hotkeys, VK.shortcutProblems = {}, {}
  for _, s in ipairs(VK.shortcuts or {}) do
    local fn = VK.actions[s.id]
    if fn and s.combo and s.combo ~= hs.json.null then
      local mods, key = splitCombo(s.combo)
      local ok, hk = pcall(hs.hotkey.bind, mods, key, fn)
      if ok and hk then table.insert(VK.hotkeys, hk)
      else table.insert(VK.shortcutProblems, (s.pretty or s.combo) .. " (" .. (s.label or s.id) .. ")") end
    end
  end
end
function VK.reloadShortcuts()
  VK.loadShortcuts()
  VK.bindShortcuts()
  if VK.menu then VK.menu.refresh() end
end
VK.reloadShortcuts()

-- Change a shortcut by pressing it: the HUD asks, the next key press is captured (Esc cancels,
-- Delete turns the shortcut off), and `voicekit keys` checks and saves it.
local CAPTURE_KEYS = { [hs.keycodes.map["escape"]] = "escape", [hs.keycodes.map["delete"]] = "delete" }
function VK.recordShortcut(id, label)
  if VK.recorder then VK.recorder:stop() end
  for _, h in ipairs(VK.hotkeys) do h:disable() end        -- so pressing a current shortcut doesn't run it
  local function finish()
    if VK.recorder then VK.recorder:stop(); VK.recorder = nil end
    if VK.recordTimeout then VK.recordTimeout:stop(); VK.recordTimeout = nil end
    for _, h in ipairs(VK.hotkeys) do h:enable() end
  end
  local function apply(args, okMsg)
    run(VK.dir .. "/bin/voicekit", args, function(code, out)
      VK.reloadShortcuts()
      local line = (out or ""):match("[^\n]+") or ""
      if code == 0 then HUD.show("ok", okMsg, label, 3, { icon = "keyboard" })
      else HUD.show("error", "Not changed", (line:gsub("^✗%s*", "")), 4, { icon = "keyboard" }) end
    end)
  end
  HUD.show("info", "Press the new shortcut", label .. " \u{00B7} Esc cancels \u{00B7} Delete turns it off", 10,
           { icon = "keyboard" })
  VK.recorder = hs.eventtap.new({ hs.eventtap.event.types.keyDown }, function(e)
    local f, code = e:getFlags(), e:getKeyCode()
    local special = CAPTURE_KEYS[code]
    local hasMod = f.cmd or f.alt or f.ctrl
    if special == "escape" and not hasMod then finish(); HUD.show("muted", "Shortcut unchanged", label, 2); return true end
    if special == "delete" and not hasMod then finish(); apply({ "keys", "off", id }, "Shortcut turned off"); return true end
    local key = hs.keycodes.map[code]
    if not key then return true end
    local parts = {}
    for _, m in ipairs({ "ctrl", "alt", "shift", "cmd" }) do if f[m] then table.insert(parts, m) end end
    table.insert(parts, key)
    finish()
    local combo = table.concat(parts, "+")
    apply({ "keys", "set", id, combo }, "Shortcut changed")
    return true
  end):start()
  VK.recordTimeout = hs.timer.doAfter(10, function() finish(); HUD.hide(0.2) end)
end

-- fn pressed alone (the usual dictation key, e.g. Handy or macOS Dictation): stop speech.
VK.fnWatcher = hs.eventtap.new({ hs.eventtap.event.types.flagsChanged }, function(e)
  local f = e:getFlags()
  if f.fn and not (f.cmd or f.alt or f.ctrl or f.shift) then kokoro({ "--stop" }) end
  return false
end)
VK.fnWatcher:start()

-- Menu bar icon: voice on/off, hands-free, held messages, and the same actions as the hotkeys.
-- Hammerspoon's own icon is hidden to save menu bar space (the notch hides icons that don't fit);
-- "ui": {"hammerspoon_icon": true} shows it again.
if ui.menubar ~= false and ui.hammerspoon_icon ~= true then hs.menuIcon(false) end
if ui.hammerspoon_icon == true then hs.menuIcon(true) end
if ui.menubar ~= false then
  VK.menu = dofile(VK.dir .. "/hammerspoon/menubar.lua")(VK, Icons).start()
end

voiceKit = VK  -- global, so watchers aren't garbage-collected and doctor can inspect
HUD.show("ok", "Claude voice kit ready", nil, 1.5, { icon = "mic" })
