-- claude-voice-kit: the menu bar icon.
-- Shows at a glance: voice on (sound bars) or off (crossed-out bars), a small dot when hands-free
-- is on, and how many messages are held. Click it for the held messages (each with Play, its
-- actions such as Approve / Deny, and Dismiss) and the same actions as the hotkeys.
-- State comes from the files the kit already writes; a path watcher keeps it current.

return function(VK, Icons)
  local MB = {}
  local HOME = os.getenv("HOME")
  local STATE = os.getenv("VOICEKIT_STATE_DIR") or (HOME .. "/.local/state/claude-voice-kit")
  local KOKORO_STATE = HOME .. "/.local/state/kokoro-voice"
  local KOKORO_CONFIG = HOME .. "/.config/kokoro-voice/config.json"

  local function exists(p) return hs.fs.attributes(p) ~= nil end

  local function heldItems()
    local items = exists(KOKORO_STATE .. "/held.json") and hs.json.read(KOKORO_STATE .. "/held.json") or {}
    local cfg = exists(KOKORO_CONFIG) and hs.json.read(KOKORO_CONFIG) or {}
    local ttl = (tonumber(cfg.held_expire_minutes) or 30) * 60
    local live = {}
    for _, h in ipairs(type(items) == "table" and items or {}) do
      if os.time() - (tonumber(h.created) or 0) < ttl then table.insert(live, h) end
    end
    return live
  end

  function MB.state()
    local items = heldItems()
    return { muted = exists(STATE .. "/muted"), handsfree = exists(STATE .. "/handsfree"), held = #items,
             items = items }
  end

  local function short(text, n)
    text = (text or ""):gsub("%s+", " ")
    return #text > n and (text:sub(1, n - 1) .. "\u{2026}") or text
  end

  -- One menu entry per held message, newest first: Play, its own actions (Approve / Deny …), Dismiss.
  local function heldEntries(items)
    local out = {}
    for i = #items, 1, -1 do
      local h = items[i]
      local sub = { { title = "Play", image = Icons.image("play", 16), fn = function() VK.kokoro({ "--play-held", h.id }) end } }
      for _, a in ipairs(h.actions or {}) do
        table.insert(sub, { title = a.label, fn = function() VK.runHeldAction(h, a) end })
      end
      table.insert(sub, { title = "-" })
      table.insert(sub, { title = "Dismiss", fn = function() VK.kokoro({ "--drop-held", h.id }) end })
      if h.why and #h.why > 0 then table.insert(sub, { title = "Held because " .. h.why, disabled = true }) end
      local actionable = h.actions and #h.actions > 0
      table.insert(out, { title = short(h.text, 60), image = Icons.image(actionable and "warning" or "message", 16),
                          menu = sub })
    end
    return out
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
    local m = {
      { title = "Claude voice", checked = not s.muted, image = img(s.muted and "speakerOff" or "speaker"),
        fn = VK.toggleVoice },
      { title = "Hands-free", checked = s.handsfree, image = img("headphones"), fn = VK.toggleHandsfree },
      { title = "-" },
    }
    if s.held > 0 then
      table.insert(m, { title = "Held while other audio played", disabled = true })
      for _, e in ipairs(heldEntries(s.items)) do table.insert(m, e) end
      table.insert(m, { title = "Play all held (" .. s.held .. ")", image = img("play"), fn = VK.playHeld })
      table.insert(m, { title = "Dismiss all", fn = function() VK.kokoro({ "--drop-held", "all" }) end })
    else
      table.insert(m, { title = "No held messages", disabled = true, image = img("message") })
    end
    for _, e in ipairs({
      { title = "Read last reply in full", image = img("lines"), fn = VK.readFull },
      { title = "Replay last message", image = img("replay"), fn = VK.replay },
      { title = "Stop speaking", image = img("stop"), fn = VK.stopSpeaking },
      { title = "-" },
      { title = "Keyboard shortcuts", image = img("keyboard"), menu = keys },
    }) do table.insert(m, e) end
    return m
  end

  function MB.refresh()
    if not MB.item then return end
    local s = MB.state()
    MB.item:setIcon(Icons.image(s.muted and "barsOff" or "bars", 18, { badge = s.handsfree }), true)
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
