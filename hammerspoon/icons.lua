-- claude-voice-kit: our own line icons, drawn as hs.canvas shapes (no emoji, no image files).
-- Every icon is drawn on a 24×24 grid with the same stroke, then scaled, so they all match.
--   Icons.elements(name, x, y, size, color [, opts])  → list of canvas elements (for the HUD)
--   Icons.image(name, size [, opts])                  → hs.image (for the menu bar and menus)
-- opts.angle rotates the spinner; opts.badge adds a small filled dot (top right).

local Icons = {}
local STROKE = 2   -- in grid units (24 = full icon)

-- Shapes on the 24-unit grid. Each returns a list of element specs in grid coordinates;
-- `place` scales and moves them. Angles: 0 = 12 o'clock, clockwise (hs.canvas arcs).
local function line(...)  return { kind = "line", pts = { ... } } end
local function poly(...)  return { kind = "poly", pts = { ... } } end
local function rect(x, y, w, h, r, fill) return { kind = "rect", x = x, y = y, w = w, h = h, r = r, fill = fill } end
local function arc(cx, cy, r, a1, a2) return { kind = "arc", cx = cx, cy = cy, r = r, a1 = a1, a2 = a2 } end
local function dot(cx, cy, r) return { kind = "dot", cx = cx, cy = cy, r = r } end

local MIC = {
  rect(9, 2.5, 6, 11.5, 3),
  arc(12, 11, 7, 90, 270),
  line({ 12, 18 }, { 12, 21.5 }),
  line({ 8.5, 21.5 }, { 15.5, 21.5 }),
}
local SPEAKER = { poly({ 3, 9.5 }, { 7, 9.5 }, { 12, 5 }, { 12, 19 }, { 7, 14.5 }, { 3, 14.5 }) }

local SHAPES = {
  mic = MIC,
  micOff = { MIC[1], MIC[2], MIC[3], MIC[4], line({ 3, 3 }, { 21, 21 }) },
  speaker = { SPEAKER[1], arc(12, 12, 4, 45, 135), arc(12, 12, 7.5, 40, 140) },
  speakerOff = { SPEAKER[1], line({ 16, 9.5 }, { 21, 14.5 }), line({ 21, 9.5 }, { 16, 14.5 }) },
  headphones = {
    arc(12, 13.5, 8.5, -90, 90),
    rect(3.5, 13.5, 4.5, 7, 2),
    rect(16, 13.5, 4.5, 7, 2),
  },
  check = { line({ 5, 12.5 }, { 10, 17.5 }, { 19.5, 7 }) },
  warning = {
    poly({ 12, 3.5 }, { 21.5, 19.5 }, { 2.5, 19.5 }),
    line({ 12, 9.5 }, { 12, 13.5 }),
    dot(12, 16.6, 1.2),
  },
  message = {
    rect(3, 4, 18, 13, 3.5),
    line({ 8, 17 }, { 7.5, 21 }, { 12.5, 17 }),
  },
  play = { poly({ 7.5, 4.5 }, { 19.5, 12 }, { 7.5, 19.5 }) },
  stop = { rect(6, 6, 12, 12, 2.5) },
  replay = {
    arc(12, 12, 8.5, 0, 270),
    line({ 12, 3.5 }, { 7.6, 4.8 }, { 4, 8 }),
    line({ 4, 3.5 }, { 4, 8 }, { 8.5, 8 }),          -- arrowhead
  },
  lines = {
    line({ 4, 6 }, { 20, 6 }), line({ 4, 10 }, { 20, 10 }),
    line({ 4, 14 }, { 20, 14 }), line({ 4, 18 }, { 14, 18 }),
  },
  keyboard = {
    rect(2.5, 6, 19, 12, 2.5),
    line({ 8, 14.5 }, { 16, 14.5 }),
    dot(6.5, 10, 1), dot(10.2, 10, 1), dot(13.8, 10, 1), dot(17.5, 10, 1),
  },
}

-- The spinner is the only animated icon: a faint ring plus a 270° arc turned by opts.angle.
local function spinner(angle)
  return { { kind = "ring", cx = 12, cy = 12, r = 8 }, arc(12, 12, 8, angle, angle + 270) }
end

local function place(shapes, x, y, size, color, opts)
  local s = size / 24
  local function P(p) return { x = x + p[1] * s, y = y + p[2] * s } end
  local w = (opts.stroke or STROKE) * s
  local out = {}
  local base = { strokeColor = color, fillColor = color, strokeWidth = w,
                 strokeCapStyle = "round", strokeJoinStyle = "round" }
  local function add(el)
    for k, v in pairs(base) do if el[k] == nil then el[k] = v end end
    table.insert(out, el)
  end
  for _, sh in ipairs(shapes) do
    if sh.kind == "line" or sh.kind == "poly" then
      local coords = {}
      for _, p in ipairs(sh.pts) do table.insert(coords, P(p)) end
      add({ type = "segments", action = "stroke", closed = sh.kind == "poly", coordinates = coords })
    elseif sh.kind == "rect" then
      add({ type = "rectangle", action = sh.fill and "fill" or "stroke",
            frame = { x = x + sh.x * s, y = y + sh.y * s, w = sh.w * s, h = sh.h * s },
            roundedRectRadii = { xRadius = sh.r * s, yRadius = sh.r * s } })
    elseif sh.kind == "arc" then
      add({ type = "arc", action = "stroke", arcRadii = false, center = P({ sh.cx, sh.cy }),
            radius = sh.r * s, startAngle = sh.a1, endAngle = sh.a2 })
    elseif sh.kind == "ring" then
      local faint = { red = color.red, green = color.green, blue = color.blue, white = color.white,
                      alpha = (color.alpha or 1) * 0.25 }
      add({ type = "circle", action = "stroke", center = P({ sh.cx, sh.cy }), radius = sh.r * s,
            strokeColor = faint })
    elseif sh.kind == "dot" then
      add({ type = "circle", action = "fill", center = P({ sh.cx, sh.cy }), radius = sh.r * s })
    end
  end
  return out
end

function Icons.has(name) return name == "spinner" or SHAPES[name] ~= nil end

function Icons.elements(name, x, y, size, color, opts)
  opts = opts or {}
  local shapes = name == "spinner" and spinner(opts.angle or 0) or SHAPES[name] or SHAPES.message
  local out = place(shapes, x, y, size, color, opts)
  if opts.badge then
    local s = size / 24
    -- a clear ring around the badge keeps it readable where it overlaps the icon
    table.insert(out, { type = "circle", action = "fill", center = { x = x + 19.5 * s, y = y + 4.5 * s },
                        radius = 5 * s, fillColor = { alpha = 0 }, compositeRule = "clear" })
    table.insert(out, { type = "circle", action = "fill", center = { x = x + 19.5 * s, y = y + 4.5 * s },
                        radius = 3.2 * s, fillColor = color })
  end
  return out
end

-- Menu bar / menu image: drawn black and marked as a template, so macOS tints it white or
-- black to match the menu bar. hs.canvas renders at the screen's scale, so it stays sharp.
local cache = {}
function Icons.image(name, size, opts)
  opts = opts or {}
  local key = name .. ":" .. size .. ":" .. tostring(opts.badge)
  if cache[key] then return cache[key] end
  local c = hs.canvas.new({ x = 0, y = 0, w = size, h = size })
  c:replaceElements(Icons.elements(name, 0, 0, size, { white = 0, alpha = 1 }, opts))
  local img = c:imageFromCanvas()
  c:delete()
  if img then img:template(true) end
  cache[key] = img
  return img
end

return Icons
