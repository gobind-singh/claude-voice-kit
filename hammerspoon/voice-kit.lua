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
--   Right Command (hold)    after 0.3 s alone: speak a voice command; release to run it (strip shows "Heard: … → result")
--   fn                      stops speech (the usual dictation key, so dictating interrupts it)

require("hs.ipc")  -- lets the `hs` command talk to Hammerspoon (used by `voicekit doctor`)

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

local mods = { "ctrl", "alt" }  -- "alt" = Option (⌥)
VK.hotkeys = {}
local function bind(key, fn) table.insert(VK.hotkeys, hs.hotkey.bind(mods, key, fn)) end

bind("V", function()
  cvoice({ "toggle" }, function(_, out)
    if out and out:find(": on", 1, true) then
      hs.alert.show("🔊 Claude voice ON")
      kokoro({ "-i", "--", "Claude voice on." })
    else
      hs.alert.show("🔇 Claude voice OFF")
    end
  end)
end)
bind("F", function() cvoice({ "full", "--toggle" }) end)
bind("N", function() kokoro({ "--next" }) end)
bind("R", function() kokoro({ "--replay" }) end)
bind("S", function() kokoro({ "--stop" }) end)
bind("K", function()
  local saved = hs.pasteboard.getContents()
  local before = hs.pasteboard.changeCount()
  hs.eventtap.keyStroke({ "cmd" }, "c")
  hs.timer.doAfter(0.25, function()
    if hs.pasteboard.changeCount() == before then
      hs.alert.show("Voice kit: no text selected")
      return
    end
    local text = hs.pasteboard.getContents()
    if saved then hs.pasteboard.setContents(saved) end
    if text and #text > 0 then kokoro({ "-i", "--", text }) end
  end)
end)

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
local OTHER_FLAGS = { "cmd", "alt", "ctrl", "shift", "fn" }
VK.recording = false
VK.armTimer = nil              -- running while the key is held but listening hasn't started yet
local function stripMessage(msg, secs)
  hs.alert.closeAll(0)
  hs.alert.show(msg, { atScreenEdge = 2, textSize = 18 }, secs or 30)
end
-- On-screen strip: what was heard, then what happened ("Heard: approve → Approved.").
VK.onCommand = function(text)
  stripMessage("Heard: " .. text .. "  …", 30)
  run(VK.voicectl, { text }, function(code, out)
    local result = (out or ""):gsub("%s+$", "")
    local mark = code == 0 and "✓" or "⚠️"
    stripMessage("Heard: " .. text .. (#result > 0 and ("  →  " .. result) or "") .. "  " .. mark, 5)
  end)
end

-- Control+Option+H (⌃⌥H): hands-free mode on/off (voice approvals + "hey Claude" wake phrase)
bind("H", function()
  run(VK.voicectl, { "handsfree", "toggle" }, function(_, out)
    stripMessage(((out or ""):find("on") and "🎧 " or "🔕 ") .. (out or ""):gsub("%s+$", ""), 3)
  end)
end)
-- Hands-free survives restarts: turn the wake phrase back on if it was on.
if hs.fs.attributes(os.getenv("HOME") .. "/.local/state/claude-voice-kit/handsfree") then
  run(VK.listen, { "--wake", "on" })
end
local function disarm()
  if VK.armTimer then VK.armTimer:stop(); VK.armTimer = nil end
end
local function startListening()
  VK.armTimer = nil
  VK.recording = true
  kokoro({ "--stop" })                                   -- don't record our own voice
  run(VK.listen, { "--start" })
  if VK.ptt.cue_sound and VK.ptt.cue_sound ~= "" then
    local cue = hs.sound.getByName(VK.ptt.cue_sound)
    if cue then cue:volume(0.4):play() end
  end
  stripMessage("🎙️ Listening…  (release the key when done)")
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
    disarm()                                             -- a shortcut (e.g. Right ⌘ + Delete): do nothing
    if VK.recording then                                 -- key used as a modifier while recording: cancel
      VK.recording = false
      run(VK.listen, { "--cancel" })
      hs.alert.closeAll(0)
    end
    return false
  end
  local f = e:getFlags()
  if e:getKeyCode() ~= PTT_KEY then
    if VK.armTimer and not onlyPttHeld(f) then disarm() end   -- another modifier joined in
    return false
  end
  if onlyPttHeld(f) and not VK.recording and not VK.armTimer then
    if VK.ptt.hold_ms == 0 then startListening()
    else VK.armTimer = hs.timer.doAfter(VK.ptt.hold_ms / 1000, startListening) end
  elseif not f[PTT_FLAG] and VK.armTimer then           -- quick tap: released before listening started
    disarm()
  elseif not f[PTT_FLAG] and VK.recording then
    VK.recording = false
    stripMessage("… transcribing", 5)
    run(VK.listen, { "--stop" }, function(code, out)
      hs.alert.closeAll(0)
      local text = (out or ""):gsub("^%s+", ""):gsub("%s+$", "")
      if code == 0 and #text > 0 then VK.onCommand(text)
      else hs.alert.show("Didn't catch that", { atScreenEdge = 2 }, 1.5) end
    end)
  end
  return false
end)
VK.pttWatcher:start()

-- Held messages: automatic messages that weren't spoken because another app was playing or
-- recording audio. kokoro calls claude/notify_held.py, which calls this.
-- Buttons: Play (speak it now), extra actions such as Approve / Deny, and Dismiss (closes the
-- notification; the message stays on ⌃⌥P until it expires).
function VK.notifyHeld(b64)
  local item = hs.json.decode(hs.base64.decode(b64))
  if not item then return end
  local labels = {}
  for _, a in ipairs(item.actions or {}) do table.insert(labels, a.label) end
  local n = hs.notify.new(function(note)
    local t = note:activationType()
    local types = hs.notify.activationTypes
    if t == types.additionalActionClicked then
      local chosen = note:additionalActivationAction()
      for _, a in ipairs(item.actions or {}) do
        if a.label == chosen then
          local args = {}
          for i = 2, #a.command do table.insert(args, a.command[i]) end
          run(a.command[1], args)
          kokoro({ "--drop-held", item.id })
        end
      end
    elseif t == types.actionButtonClicked or t == types.contentsClicked then
      kokoro({ "--play-held", item.id })
    end
  end, {
    title = "Claude · held (" .. (item.why or "other audio") .. ")",
    informativeText = item.text,
    hasActionButton = true,
    actionButtonTitle = "Play",
    otherButtonTitle = "Dismiss",
    withdrawAfter = 0,
  })
  if #labels > 0 then
    n:additionalActions(labels)
    pcall(function() n:alwaysShowAdditionalActions(true) end)
  end
  n:send()
  VK.lastHeldNote = n
  stripMessage("🔇 Held a message (" .. (item.why or "other audio") .. "). ⌃⌥P to play", 4)
end

-- Control+Option+P (⌃⌥P): play all held messages
bind("P", function() kokoro({ "--play-held" }) end)

-- fn pressed alone (the usual dictation key, e.g. Handy or macOS Dictation): stop speech.
VK.fnWatcher = hs.eventtap.new({ hs.eventtap.event.types.flagsChanged }, function(e)
  local f = e:getFlags()
  if f.fn and not (f.cmd or f.alt or f.ctrl or f.shift) then kokoro({ "--stop" }) end
  return false
end)
VK.fnWatcher:start()

voiceKit = VK  -- global, so watchers aren't garbage-collected and doctor can inspect
hs.alert.show("Claude voice kit loaded")
