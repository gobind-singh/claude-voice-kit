-- claude-voice-kit: the menu bar icon.
-- Shows at a glance: voice on (mic) or off (crossed-out mic), a small dot when hands-free is
-- on, and how many messages are held. Click it for the same actions as the hotkeys.
-- State comes from the files the kit already writes; a path watcher keeps it current.

return function(VK, Icons)
  local MB = {}
  local HOME = os.getenv("HOME")
  local STATE = os.getenv("VOICEKIT_STATE_DIR") or (HOME .. "/.local/state/claude-voice-kit")
  local KOKORO_STATE = HOME .. "/.local/state/kokoro-voice"
  local KOKORO_CONFIG = HOME .. "/.config/kokoro-voice/config.json"

  local function exists(p) return hs.fs.attributes(p) ~= nil end

  function MB.state()
    local held = 0
    local items = exists(KOKORO_STATE .. "/held.json") and hs.json.read(KOKORO_STATE .. "/held.json") or {}
    local cfg = exists(KOKORO_CONFIG) and hs.json.read(KOKORO_CONFIG) or {}
    local ttl = (tonumber(cfg.held_expire_minutes) or 30) * 60
    for _, h in ipairs(type(items) == "table" and items or {}) do
      if os.time() - (tonumber(h.created) or 0) < ttl then held = held + 1 end
    end
    return { muted = exists(STATE .. "/muted"), handsfree = exists(STATE .. "/handsfree"), held = held }
  end

  local SHORTCUTS = {
    { "⌃⌥V", "Claude voice on/off" },
    { "⌃⌥F", "Read the whole last reply" },
    { "⌃⌥N", "Skip to the next section" },
    { "⌃⌥R", "Replay the last message" },
    { "⌃⌥S", "Stop speaking" },
    { "⌃⌥K", "Read selected text aloud" },
    { "⌃⌥H", "Hands-free on/off" },
    { "⌃⌥P", "Play held messages" },
    { "Right ⌘ (hold)", "Speak a voice command" },
    { "fn", "Stop speaking" },
  }

  local function img(name) return Icons.image(name, 16) end

  local function menu()
    local s = MB.state()
    local keys = {}
    for _, k in ipairs(SHORTCUTS) do
      table.insert(keys, { title = hs.styledtext.new(k[1] .. "    ", { font = { name = ".AppleSystemUIFontDemi", size = 13 } })
                                   .. hs.styledtext.new(k[2], { font = { name = ".AppleSystemUIFont", size = 13 } }) })
    end
    return {
      { title = "Claude voice", checked = not s.muted, image = img(s.muted and "speakerOff" or "speaker"),
        fn = VK.toggleVoice },
      { title = "Hands-free", checked = s.handsfree, image = img("headphones"), fn = VK.toggleHandsfree },
      { title = "-" },
      { title = s.held > 0 and ("Play held messages (" .. s.held .. ")") or "No held messages",
        disabled = s.held == 0, image = img("play"), fn = VK.playHeld },
      { title = "Read last reply in full", image = img("lines"), fn = VK.readFull },
      { title = "Replay last message", image = img("replay"), fn = VK.replay },
      { title = "Stop speaking", image = img("stop"), fn = VK.stopSpeaking },
      { title = "-" },
      { title = "Keyboard shortcuts", image = img("keyboard"), menu = keys },
    }
  end

  function MB.refresh()
    if not MB.item then return end
    local s = MB.state()
    MB.item:setIcon(Icons.image(s.muted and "micOff" or "mic", 18, { badge = s.handsfree }), true)
    MB.item:setTitle(s.held > 0 and tostring(s.held) or nil)
    MB.item:setTooltip("Claude voice " .. (s.muted and "off" or "on")
      .. (s.handsfree and " · hands-free" or "")
      .. (s.held > 0 and (" · " .. s.held .. " held") or ""))
  end

  function MB.start()
    MB.item = hs.menubar.new(true, "claude-voice-kit")
    if not MB.item then return MB end
    MB.menu = menu
    MB.item:setMenu(menu)
    MB.later = hs.timer.delayed.new(0.3, MB.refresh)
    MB.watchers = {}
    for _, dir in ipairs({ STATE, KOKORO_STATE }) do
      if exists(dir) then
        table.insert(MB.watchers, hs.pathwatcher.new(dir .. "/", function() MB.later:start() end):start())
      end
    end
    MB.poll = hs.timer.doEvery(60, MB.refresh)   -- held messages expire without a file change
    MB.refresh()
    return MB
  end

  function MB.stop()
    for _, w in ipairs(MB.watchers or {}) do w:stop() end
    if MB.poll then MB.poll:stop() end
    if MB.later then MB.later:stop() end
    if MB.item then MB.item:delete(); MB.item = nil end
  end

  return MB
end
