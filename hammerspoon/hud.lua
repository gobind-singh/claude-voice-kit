-- claude-voice-kit: the on-screen HUD (heads-up display).
-- A small dark pill near the bottom of the screen that shows what the voice kit is doing:
-- listening, transcribing, done, problem. It floats above all apps, clicks pass through it,
-- and it fades away by itself. Drawn with hs.canvas; icons come from icons.lua.
--
--   HUD.show(state, title [, detail [, secs [, opts]]])   states: listening, transcribing, ok,
--                                                         error, info, muted
--   HUD.hide([fade])
-- opts.icon overrides the state's icon. HUD.useAlert = true falls back to Hammerspoon's plain
-- hs.alert (set "ui": {"hud": false} in ~/.config/claude-voice-kit/config.json).

return function(Icons)
  local HUD = { useAlert = false }

  local STATES = {
    listening    = { color = { red = 1.00, green = 0.36, blue = 0.38 }, icon = "mic",        secs = 30, anim = "listen" },
    transcribing = { color = { red = 1.00, green = 0.74, blue = 0.30 }, icon = "spinner",    secs = 30, anim = "spin" },
    ok           = { color = { red = 0.36, green = 0.86, blue = 0.52 }, icon = "check",      secs = 4 },
    error        = { color = { red = 1.00, green = 0.58, blue = 0.32 }, icon = "warning",    secs = 4 },
    info         = { color = { red = 0.45, green = 0.68, blue = 1.00 }, icon = "message",    secs = 3 },
    muted        = { color = { red = 0.62, green = 0.64, blue = 0.70 }, icon = "speakerOff", secs = 2.5 },
  }

  -- Layout (points)
  local M = 28                   -- room around the pill for its shadow
  local PADX, GAP = 12, 12
  local BADGE, ICON = 32, 18     -- coloured circle behind the icon; icon size
  local BARS, BAR_W, BAR_GAP, BAR_H = 5, 3, 3, 18
  local BOTTOM = 64              -- pill distance from the bottom of the usable screen
  local TITLE = { font = { name = ".AppleSystemUIFontDemi", size = 14 }, color = { white = 1, alpha = 0.96 } }
  local DETAIL = { font = { name = ".AppleSystemUIFont", size = 12 }, color = { white = 1, alpha = 0.58 } }
  local BG = { red = 0.085, green = 0.09, blue = 0.10, alpha = 0.94 }

  local function withAlpha(c, a)
    return { red = c.red, green = c.green, blue = c.blue, white = c.white, alpha = a }
  end

  local function textWidth(s, style)
    return hs.drawing.getTextDrawingSize(s, { font = style.font.name, size = style.font.size }).w
  end

  -- Shorten text with "…" so it fits in maxW.
  local function fit(s, style, maxW)
    if textWidth(s, style) <= maxW then return s end
    local n = utf8.len(s) or #s
    local lo, hi = 1, n
    while lo < hi do
      local mid = (lo + hi + 1) // 2
      local cut = s:sub(1, (utf8.offset(s, mid + 1) or (#s + 1)) - 1) .. "…"
      if textWidth(cut, style) <= maxW then lo = mid else hi = mid - 1 end
    end
    return s:sub(1, (utf8.offset(s, lo + 1) or (#s + 1)) - 1):gsub("%s+$", "") .. "…"
  end

  local function styled(s, style)
    return hs.styledtext.new(s, { font = style.font, color = style.color,
                                  paragraphStyle = { lineBreak = "truncateTail" } })
  end

  -- Build every element of the pill, plus the indexes the animation needs.
  local function build(st, title, detail, iconName, screen)
    local sf = screen:frame()
    local maxText = math.min(520, sf.w * 0.6)
    local bars = st.anim == "listen"
    title = fit(title, TITLE, maxText)
    detail = detail and #detail > 0 and fit(detail, DETAIL, maxText) or nil
    local tw = math.max(textWidth(title, TITLE), detail and textWidth(detail, DETAIL) or 0)
    local ph = detail and 56 or 48
    local pw = math.max(200, PADX + BADGE + GAP + tw + (bars and (GAP + BARS * (BAR_W + BAR_GAP)) or 0) + PADX + 10)
    local frame = { x = sf.x + (sf.w - pw) / 2 - M, y = sf.y + sf.h - BOTTOM - ph - M, w = pw + 2 * M, h = ph + 2 * M }

    local els, idx = {}, {}
    local function add(e) table.insert(els, e); return #els end
    add({ type = "rectangle", action = "strokeAndFill", fillColor = BG,
          strokeColor = { white = 1, alpha = 0.10 }, strokeWidth = 1,
          frame = { x = M, y = M, w = pw, h = ph }, roundedRectRadii = { xRadius = ph / 2, yRadius = ph / 2 },
          withShadow = true, shadow = { blurRadius = 22, color = { alpha = 0.55 }, offset = { h = -6, w = 0 } } })
    local cx, cy = M + PADX + BADGE / 2, M + ph / 2
    idx.badge = add({ type = "circle", action = "fill", center = { x = cx, y = cy }, radius = BADGE / 2,
                      fillColor = withAlpha(st.color, 0.18) })
    idx.icon = #els + 1
    for _, e in ipairs(Icons.elements(iconName, cx - ICON / 2, cy - ICON / 2, ICON, st.color)) do add(e) end
    local tx = M + PADX + BADGE + GAP
    if detail then
      add({ type = "text", text = styled(title, TITLE), frame = { x = tx, y = cy - 19, w = tw + 6, h = 19 } })
      add({ type = "text", text = styled(detail, DETAIL), frame = { x = tx, y = cy + 1, w = tw + 6, h = 17 } })
    else
      add({ type = "text", text = styled(title, TITLE), frame = { x = tx, y = cy - 9.5, w = tw + 6, h = 19 } })
    end
    if bars then
      idx.bars, idx.barX, idx.cy = {}, {}, cy
      local bx = M + pw - PADX - 6 - BARS * (BAR_W + BAR_GAP) + BAR_GAP
      for i = 1, BARS do
        local x = bx + (i - 1) * (BAR_W + BAR_GAP)
        idx.barX[i] = x
        idx.bars[i] = add({ type = "rectangle", action = "fill", fillColor = withAlpha(st.color, 0.9),
                            frame = { x = x, y = cy - 2, w = BAR_W, h = 4 },
                            roundedRectRadii = { xRadius = BAR_W / 2, yRadius = BAR_W / 2 } })
      end
    end
    return frame, els, idx, { cx = cx, cy = cy }
  end

  local function stopAnim()
    if HUD.animTimer then HUD.animTimer:stop(); HUD.animTimer = nil end
  end

  local function startAnim(st, idx, center)
    stopAnim()
    if not st.anim then return end
    local c, t0 = HUD.canvas, hs.timer.secondsSinceEpoch()
    HUD.animTimer = hs.timer.doEvery(1 / 30, function()
      if HUD.canvas ~= c then return stopAnim() end
      local t = hs.timer.secondsSinceEpoch() - t0
      if st.anim == "listen" then
        c[idx.badge].fillColor = withAlpha(st.color, 0.16 + 0.12 * (0.5 + 0.5 * math.sin(t * 4)))
        for i, el in ipairs(idx.bars) do
          local h = 4 + (BAR_H - 4) * math.abs(math.sin(t * (5 + i * 1.7) + i)) * (0.55 + 0.45 * math.sin(t * 1.9 + i * 2))
          c[el].frame = { x = idx.barX[i], y = idx.cy - h / 2, w = BAR_W, h = h }
        end
      elseif st.anim == "spin" then
        local a = (t * 360) % 360
        local spin = Icons.elements("spinner", center.cx - ICON / 2, center.cy - ICON / 2, ICON, st.color, { angle = a })
        c[idx.icon + #spin - 1].startAngle = spin[#spin].startAngle
        c[idx.icon + #spin - 1].endAngle = spin[#spin].endAngle
      end
    end)
  end

  -- Fading canvases are kept here until deleted, so they aren't garbage-collected mid-fade.
  HUD.fading = {}

  function HUD.hide(fade)
    stopAnim()
    if HUD.hideTimer then HUD.hideTimer:stop(); HUD.hideTimer = nil end
    local c = HUD.canvas
    if not c then return end
    HUD.canvas = nil
    fade = fade or 0.25
    c:hide(fade)
    local key = tostring(c)
    HUD.fading[key] = { canvas = c, timer = hs.timer.doAfter(fade + 0.1, function()
      c:delete(); HUD.fading[key] = nil
    end) }
  end

  function HUD.show(state, title, detail, secs, opts)
    opts = opts or {}
    local st = STATES[state] or STATES.info
    if HUD.useAlert then
      hs.alert.closeAll(0)
      hs.alert.show(title .. (detail and #detail > 0 and ("  ·  " .. detail) or ""),
                    { atScreenEdge = 2, textSize = 18 }, secs or st.secs)
      return
    end
    local iconName = opts.icon or st.icon
    local screen = hs.screen.mainScreen()   -- the screen with the focused window
    local frame, els, idx, center = build(st, title, detail, iconName, screen)
    if HUD.hideTimer then HUD.hideTimer:stop(); HUD.hideTimer = nil end
    local c = HUD.canvas
    if c then
      c:frame(frame)
      c:replaceElements(els)
    else
      c = hs.canvas.new(frame)
      c:level(hs.canvas.windowLevels.overlay)
      c:behaviorAsLabels({ "canJoinAllSpaces", "stationary", "fullScreenAuxiliary" })
      c:wantsLayer(true)
      c:replaceElements(els)
      HUD.canvas = c
      c:show(0.15)
    end
    startAnim(st, idx, center)
    HUD.hideTimer = hs.timer.doAfter(secs or st.secs, function() HUD.hide() end)
  end

  function HUD.destroy()
    HUD.hide(0)
    for _, f in pairs(HUD.fading) do pcall(function() f.timer:stop(); f.canvas:delete() end) end
    HUD.fading = {}
  end

  return HUD
end
