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
      local sub = { { title = "Play", image = Icons.image("play", 16), fn = function() VK.kokoroDo({ "--play-held", h.id }) end } }
      for _, a in ipairs(h.actions or {}) do
        table.insert(sub, { title = a.label, fn = function() VK.runHeldAction(h, a) end })
      end
      table.insert(sub, { title = "-" })
      table.insert(sub, { title = "Dismiss", fn = function() VK.kokoroDo({ "--drop-held", h.id }) end })
      if h.why and #h.why > 0 then table.insert(sub, { title = "Held because " .. h.why, disabled = true }) end
      local actionable = h.actions and #h.actions > 0
      table.insert(out, { title = short(h.text, 60), image = Icons.image(actionable and "warning" or "message", 16),
                          menu = sub })
    end
    return out
  end

  -- Voices: the Kokoro voice files in the model cache, grouped by accent. Picking one makes it the
  -- default for everything and says a short sample in it.
  local VOICE_GROUPS = {
    { "a", "American English" }, { "b", "British English" }, { "e", "Spanish" }, { "f", "French" },
    { "h", "Hindi" }, { "i", "Italian" }, { "j", "Japanese" }, { "p", "Portuguese (Brazil)" }, { "z", "Chinese" },
  }
  local SPEEDS = { 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.5 }
  local function listVoices()
    if MB.voices then return MB.voices end
    local base = HOME .. "/.cache/huggingface/hub/models--mlx-community--Kokoro-82M-bf16/snapshots"
    local found = {}
    if exists(base) then
      for snap in hs.fs.dir(base) do
        local d = base .. "/" .. snap .. "/voices"
        if snap:sub(1, 1) ~= "." and exists(d) then
          for f in hs.fs.dir(d) do
            local v = f:match("^(%a%a_[%w_]+)%.safetensors$")
            if v then found[v] = true end
          end
        end
      end
    end
    local list = {}
    for v in pairs(found) do table.insert(list, v) end
    table.sort(list)
    MB.voices = list
    return list
  end
  local function voiceName(v)
    local name = v:sub(4):gsub("_", " ")
    return name:sub(1, 1):upper() .. name:sub(2)
  end
  local function voiceMenu(current)
    local voices, groups = listVoices(), {}
    for _, v in ipairs(voices) do
      local g, sex = v:sub(1, 1), v:sub(2, 2)
      groups[g] = groups[g] or {}
      table.insert(groups[g], { title = voiceName(v) .. (sex == "f" and "  \u{2640}" or sex == "m" and "  \u{2642}" or ""),
        checked = v == current, fn = function() VK.setVoice(v, voiceName(v)) end })
    end
    local out = {}
    for _, gr in ipairs(VOICE_GROUPS) do
      local items = groups[gr[1]]
      if items then
        if gr[1] == "a" or gr[1] == "b" then         -- English voices inline, others in a submenu
          table.insert(out, { title = gr[2], disabled = true })
          for _, it in ipairs(items) do table.insert(out, it) end
        else
          if not out.other then out.other = {}; end
          table.insert(out.other, { title = gr[2], menu = items })
        end
      end
    end
    if out.other then
      table.insert(out, { title = "-" })
      table.insert(out, { title = "Other languages", menu = out.other })
      out.other = nil
    end
    if #out == 0 then out = { { title = "Voice files not found (run voicekit install)", disabled = true } } end
    return out
  end
  local function speedMenu(current)
    local out = {}
    for _, sp in ipairs(SPEEDS) do
      table.insert(out, { title = (sp == 1.0 and "Normal" or (string.format("%.1f\u{00D7}", sp))),
        checked = math.abs((current or 1.0) - sp) < 0.01, fn = function() VK.setSpeed(sp) end })
    end
    return out
  end

  -- Keyboard shortcuts: each one shows its keys; choosing it lets you press a new shortcut.
  local function shortcutsMenu()
    local bold = { font = { name = ".AppleSystemUIFontDemi", size = 13 } }
    local plain = { font = { name = ".AppleSystemUIFont", size = 13 } }
    local out = { { title = "Choose one, then press the new keys", disabled = true } }
    for _, sc in ipairs(VK.shortcuts or {}) do
      local keys = sc.pretty or sc.combo or "off"
      table.insert(out, {
        title = hs.styledtext.new(string.format("%-8s", keys) .. "  ", bold) .. hs.styledtext.new(sc.label or sc.id, plain),
        fn = function() VK.recordShortcut(sc.id, sc.label or sc.id) end })
    end
    table.insert(out, { title = "-" })
    local ptt = (VK.ptt and VK.ptt.key or "right_cmd"):gsub("right_", "Right "):gsub("cmd", "\u{2318}")
      :gsub("option", "\u{2325}"):gsub("shift", "\u{21E7}"):gsub("ctrl", "\u{2303}")
    table.insert(out, { title = hs.styledtext.new(ptt .. " (hold)  ", bold) .. hs.styledtext.new("Speak a voice command", plain),
                        disabled = true })
    table.insert(out, { title = hs.styledtext.new("fn  ", bold) .. hs.styledtext.new("Stop speaking", plain), disabled = true })
    table.insert(out, { title = "-" })
    table.insert(out, { title = "Reset all to defaults", fn = function()
      VK.run(VK.dir .. "/bin/voicekit", { "keys", "reset" }, function() VK.reloadShortcuts()
        VK.hud.show("ok", "Shortcuts reset", "Back to \u{2303}\u{2325} + letter", 3, { icon = "keyboard" }) end)
    end })
    return out
  end

  local function kokoroConfig() return exists(KOKORO_CONFIG) and hs.json.read(KOKORO_CONFIG) or {} end

  local function img(name) return Icons.image(name, 16) end

  local function menu()
    local s = MB.state()
    local kc = kokoroConfig()
    local current = kc.voice or "af_heart"
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
      table.insert(m, { title = "Dismiss all", fn = function() VK.kokoroDo({ "--drop-held", "all" }) end })
    else
      table.insert(m, { title = "No held messages", disabled = true, image = img("message") })
    end
    for _, e in ipairs({
      { title = "Read last reply in full", image = img("lines"), fn = VK.readFull },
      { title = "Replay last message", image = img("replay"), fn = VK.replay },
      { title = "Stop speaking", image = img("stop"), fn = VK.stopSpeaking },
      { title = "-" },
      { title = "Voice: " .. voiceName(current), image = img("speaker"), menu = voiceMenu(current) },
      { title = "Speed", menu = speedMenu(tonumber(kc.speed) or 1.0) },
      { title = "-" },
      { title = "Keyboard shortcuts", image = img("keyboard"), menu = shortcutsMenu() },
      { title = "Reload hotkeys", fn = function() hs.reload() end },
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

  local POSITION_KEY = "NSStatusItem Preferred Position claude-voice-kit"

  local function create()
    for _, w in ipairs(MB.watchers or {}) do w:stop() end
    if MB.poll then MB.poll:stop() end
    MB.item = hs.menubar.new(true, "claude-voice-kit")
    if not MB.item then return end
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
  end

  -- Where the system icons (battery, Wi-Fi, Control Centre, clock …) begin, in screen points from the left.
  local function systemIconsLeft()
    local left
    for _, name in ipairs({ "com.apple.controlcenter", "com.apple.systemuiserver" }) do
      local app = hs.application.get(name)
      local ok, ax = pcall(function() return app and hs.axuielement.applicationElement(app) end)
      local bar = ok and ax and ax:attributeValue("AXExtrasMenuBar")
      for _, item in ipairs(bar and bar:attributeValue("AXChildren") or {}) do
        local pos = item:attributeValue("AXPosition")
        if pos and (not left or pos.x < left) then left = pos.x end
      end
    end
    return left
  end

  -- macOS's "preferred position" is the distance from the right edge of the screen to the icon's right edge.
  local function targetPosition()
    local left = systemIconsLeft()
    local screen = hs.screen.primaryScreen():fullFrame()
    return left and math.max(0, screen.x + screen.w - left + 2) or 400
  end

  function MB.start()
    create()
    -- MacBook notch: macOS hides menu bar icons that don't fit, leftmost (newest) first. The first time,
    -- move ours right next to the system icons. macOS then remembers the position under the icon's name,
    -- so a later ⌘-drag by the user is kept. macOS writes an icon's position a moment after it's removed
    -- (also during a Hammerspoon reload), so this runs a little later: remove, set the position, re-add.
    if not hs.settings.get("voicekit.menubarPlaced") then
      MB.placeTimer = hs.timer.doAfter(2, function()
        local target = targetPosition()
        hs.settings.set(POSITION_KEY, target)
        if MB.item then MB.item:delete(); MB.item = nil end
        MB.placeTimer = hs.timer.doAfter(0.8, function()
          MB.placeTimer = nil
          hs.settings.set(POSITION_KEY, target)
          create()
          hs.settings.set("voicekit.menubarPlaced", true)
        end)
      end)
    end
    return MB
  end

  function MB.stop()
    if MB.placeTimer then MB.placeTimer:stop(); MB.placeTimer = nil end
    for _, w in ipairs(MB.watchers or {}) do w:stop() end
    if MB.poll then MB.poll:stop() end
    if MB.later then MB.later:stop() end
    if MB.item then MB.item:delete(); MB.item = nil end
  end

  return MB
end
