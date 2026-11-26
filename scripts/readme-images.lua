-- claude-voice-kit: renders the README / docs images from the kit's own drawing code.
-- Run through scripts/readme-images.sh (it calls this inside Hammerspoon). It loads fresh copies of
-- icons.lua, hud.lua and menubar.lua, so the running kit is not touched.
--   docs/images/logo.svg, icons/*.svg, menubar-*.svg   vector, from the same 24×24 shapes as the menu bar
--   docs/images/hud-*.png                              the real on-screen HUD pill
--   docs/images/menu.png, menu-shortcuts.png           the real menu bar menu
-- The pop-up and the menu appear on screen for a moment while they are captured.

return function(root, tmp)
  local OUT = root .. "/docs/images"
  hs.fs.mkdir(OUT)
  hs.fs.mkdir(OUT .. "/icons")
  local Icons = dofile(root .. "/hammerspoon/icons.lua")

  local function write(path, text)
    local f = assert(io.open(path, "w"))
    f:write(text)
    f:close()
  end

  -- ── SVG: convert the canvas elements of a 24-unit icon into SVG markup ──────────────────
  local function n(v)
    local s = string.format("%.2f", v):gsub("0+$", ""):gsub("%.$", "")
    return (s == "-0" or s == "") and "0" or s
  end
  local function pt(cx, cy, r, deg)       -- hs.canvas angles: 0 = 12 o'clock, clockwise
    local a = math.rad(deg)
    return cx + r * math.sin(a), cy - r * math.cos(a)
  end
  local function svgShapes(name, opts)
    local out = {}
    for _, el in ipairs(Icons.elements(name, 0, 0, 24, { white = 0 }, opts)) do
      if el.compositeRule then
        -- the badge's clear ring: handled with a mask in svgIcon
      elseif el.type == "segments" then
        local d = {}
        for i, p in ipairs(el.coordinates) do table.insert(d, (i == 1 and "M" or "L") .. n(p.x) .. " " .. n(p.y)) end
        table.insert(out, string.format('<path d="%s%s"/>', table.concat(d, " "), el.closed and " Z" or ""))
      elseif el.type == "rectangle" then
        local f, r = el.frame, el.roundedRectRadii and el.roundedRectRadii.xRadius or 0
        table.insert(out, string.format('<rect x="%s" y="%s" width="%s" height="%s" rx="%s"%s/>',
          n(f.x), n(f.y), n(f.w), n(f.h), n(r), el.action == "fill" and ' fill="currentColor" stroke="none"' or ""))
      elseif el.type == "arc" then
        local x1, y1 = pt(el.center.x, el.center.y, el.radius, el.startAngle)
        local x2, y2 = pt(el.center.x, el.center.y, el.radius, el.endAngle)
        local large = ((el.endAngle - el.startAngle) % 360) > 180 and 1 or 0
        table.insert(out, string.format('<path d="M%s %s A%s %s 0 %d 1 %s %s"/>',
          n(x1), n(y1), n(el.radius), n(el.radius), large, n(x2), n(y2)))
      elseif el.type == "circle" then
        table.insert(out, string.format('<circle cx="%s" cy="%s" r="%s"%s/>', n(el.center.x), n(el.center.y),
          n(el.radius), el.action == "fill" and ' fill="currentColor" stroke="none"' or ""))
      end
    end
    return out
  end

  -- Fixed colours that read on both GitHub's light and dark pages. (A prefers-color-scheme rule inside
  -- the SVG follows the system setting, not GitHub's theme, so it can pick the wrong one.)
  local ACCENT, GREY = "#C96442", "#7D8590"
  local function svgIcon(name, opts, extraWidth, extra)
    opts = opts or {}
    local color = opts.color or ACCENT
    local w = 24 + (extraWidth or 0)
    local shapes = svgShapes(name, opts)
    local body
    if opts.badge then
      -- the badge dot sits in a clear ring so it stays readable where it overlaps the icon
      local dot = table.remove(shapes)
      body = '<mask id="m"><rect width="24" height="24" fill="#fff"/><circle cx="19.5" cy="4.5" r="5" fill="#000"/></mask>'
        .. '<g mask="url(#m)">' .. table.concat(shapes) .. '</g>' .. dot
    else
      body = table.concat(shapes)
    end
    return string.format('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d 24" width="%d" height="48">'
      .. '<g color="%s" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
      .. '%s%s</g></svg>\n', w, w * 2, color, body, extra or "")
  end

  for _, name in ipairs({ "bars", "barsOff", "mic", "speaker", "speakerOff", "headphones", "check", "warning",
                          "message", "play", "stop", "replay", "lines", "keyboard" }) do
    write(OUT .. "/icons/" .. name .. ".svg", svgIcon(name))
  end
  -- What the menu bar icon looks like in each state.
  write(OUT .. "/menubar-on.svg", svgIcon("bars", { color = GREY }))
  write(OUT .. "/menubar-off.svg", svgIcon("barsOff", { color = GREY }))
  write(OUT .. "/menubar-handsfree.svg", svgIcon("bars", { badge = true, color = GREY }))
  write(OUT .. "/menubar-held.svg", svgIcon("bars", { color = GREY }, 12,
    '<text x="27" y="17.5" font-family="-apple-system,BlinkMacSystemFont,Helvetica,Arial,sans-serif" font-size="14"'
    .. ' font-weight="500" fill="currentColor" stroke="none">2</text>'))

  -- Logo: the menu bar's sound bars, white on a warm rounded square.
  write(OUT .. "/logo.svg", '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128" width="128" height="128">'
    .. '<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#E5876A"/>'
    .. '<stop offset="1" stop-color="#C9603F"/></linearGradient></defs>'
    .. '<rect width="128" height="128" rx="30" fill="url(#g)"/>'
    .. '<g transform="translate(24 24) scale(3.333)" fill="none" stroke="#fff" stroke-width="2"'
    .. ' stroke-linecap="round" stroke-linejoin="round">' .. table.concat(svgShapes("bars")) .. '</g></svg>\n')

  -- ── PNG: the real HUD pill, one per state ──────────────────────────────────────────────
  local HUD = dofile(root .. "/hammerspoon/hud.lua")(Icons)
  local function q(s) return "\u{201C}" .. s .. "\u{201D}" end
  local HUDS = {
    { "hud-listening", "listening", "Listening\u{2026}", "Release Right \u{2318} when done" },
    { "hud-transcribing", "transcribing", q("tell api to run the tests"), "Working on it\u{2026}" },
    { "hud-done", "ok", "Sent to api", "Heard " .. q("tell api to run the tests") },
    { "hud-handsfree", "info", "Hands-free on", "Approvals are asked out loud \u{00B7} say " .. q("hey Claude"),
      { icon = "headphones" } },
    { "hud-held", "info", "Message held", "Other audio was playing \u{00B7} Answer from the menu bar icon",
      { icon = "message" } },
    { "hud-problem", "error", "Didn't catch that", "Hold Right \u{2318}, wait for the tick, then speak" },
  }

  -- ── PNG: the real menu, captured by a helper while it is open ──────────────────────────
  local function captureMenu(menuTable, file, done)
    local item = hs.menubar.new(false)
    item:setMenu(menuTable)
    local helper = hs.task.new(tmp .. "/menucap", function(_, _, stderr)
      local f = io.open(tmp .. "/menucap.log", "a")
      if f then f:write(stderr or ""); f:close() end
      hs.timer.doAfter(1.5, done)                    -- let the closed menu fade out first
    end, { tostring(hs.processInfo.processID), OUT .. "/" .. file })
    helper:start()
    local sf = hs.screen.mainScreen():frame()
    local mouse = hs.mouse.absolutePosition()
    hs.mouse.absolutePosition({ x = sf.x + 20, y = sf.y + sf.h - 20 })  -- keep the pointer off the menu
    item:popupMenu({ x = sf.x + sf.w / 2 - 140, y = sf.y + 80 })   -- returns when the helper presses Esc
    hs.mouse.absolutePosition(mouse)
    item:delete()
  end

  local function menus(done)
    -- A stand-in for the kit's VK table: only what menu() reads. Shortcuts are the defaults.
    local f = io.open(tmp .. "/shortcuts.json")
    local shortcuts = f and hs.json.decode(f:read("a")) or {}
    if f then f:close() end
    local noop = function() end
    local VK = setmetatable({ dir = root, shortcuts = shortcuts, ptt = { key = "right_cmd" } },
      { __index = function() return noop end })
    local realNew = hs.menubar.new
    hs.menubar.new = function() return realNew(false) end         -- never add a second icon to the menu bar
    local MB = dofile(root .. "/hammerspoon/menubar.lua")(VK, Icons)
    MB.start()
    hs.menubar.new = realNew
    -- An example held message, so the picture shows Play / Approve / Deny.
    MB.state = function()
      return { muted = false, handsfree = false, held = 1, items = { {
        id = "demo", text = "In api: Claude wants to run npm install. Approve?", why = "music was playing",
        actions = { { label = "Approve" }, { label = "Deny" } } } } }
    end
    local m = MB.menu()
    MB.stop()
    local sub
    for _, e in ipairs(m) do if e.title == "Keyboard shortcuts" then sub = e.menu end end
    captureMenu(m, "menu.png", function()
      captureMenu(sub, "menu-shortcuts.png", done)
    end)
  end

  local function nextHud(i)
    if i > #HUDS then
      HUD.destroy()
      return hs.timer.doAfter(0.5, function()
        menus(function() write(tmp .. "/done", "ok") end)
      end)
    end
    local h = HUDS[i]
    HUD.show(h[2], h[3], h[4], 10, h[5])
    hs.timer.doAfter(0.7, function()                 -- after the fade-in, mid-animation
      HUD.canvas:imageFromCanvas():saveToFile(OUT .. "/" .. h[1] .. ".png")
      nextHud(i + 1)
    end)
  end
  nextHud(1)
  return "started"
end
