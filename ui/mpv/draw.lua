-- Copyright (C) 2026 yrmuq
-- SPDX-License-Identifier: GPL-3.0-or-later
-- Drawing helpers. Colors are "#RRGGBB". ASS alpha 00 is opaque.

local function bgr(hex)
    hex = (hex or "#FFFFFF"):gsub("#", "")
    return hex:sub(5, 6) .. hex:sub(3, 4) .. hex:sub(1, 2)
end

local function esc(text)
    text = tostring(text or "")
    return (text:gsub("\\", "\\\\"):gsub("{", "\\{"):gsub("}", "\\}"))
end

return function(K)
    K.bgr = bgr
    K.esc = esc

    function K.rect(ass, x, y, w, h, hex, alpha)
        ass:new_event()
        ass:append(string.format(
            "{\\pos(0,0)\\an7\\bord0\\shad0\\1c&H%s&\\1a&H%s&\\p1}m %d %d l %d %d l %d %d l %d %d{\\p0}",
            bgr(hex), alpha or "00",
            math.floor(x), math.floor(y),
            math.floor(x + w), math.floor(y),
            math.floor(x + w), math.floor(y + h),
            math.floor(x), math.floor(y + h)
        ))
    end

    function K.text(ass, x, y, align, size, hex, text, extra)
        ass:new_event()
        ass:append(string.format(
            "{\\pos(%d,%d)\\an%d\\bord0\\shad0\\fnSans\\fs%d\\1c&H%s&%s}%s",
            math.floor(x), math.floor(y), align or 7, size or 16, bgr(hex), extra or "", esc(text)
        ))
    end

    -- A gear built from rectangles so it does not depend on the OSD font.
    function K.gear(ass, x, y, size, hex, hole)
        local s = size
        local tooth = math.max(2, math.floor(s * 0.18))
        local reach = math.max(3, math.floor(s * 0.28))
        local cx = s / 2
        local cy = s / 2
        local bars = {
            {cx - tooth / 2, 0, tooth, reach},
            {cx - tooth / 2, s - reach, tooth, reach},
            {0, cy - tooth / 2, reach, tooth},
            {s - reach, cy - tooth / 2, reach, tooth},
        }
        for i = 1, #bars do
            local b = bars[i]
            K.rect(ass, x + b[1], y + b[2], b[3], b[4], hex, "00")
        end
        local inset = math.floor(s * 0.22)
        local tw = math.max(2, math.floor(s * 0.16))
        local corners = {
            {inset, inset},
            {s - inset - tw, inset},
            {inset, s - inset - tw},
            {s - inset - tw, s - inset - tw},
        }
        for i = 1, #corners do
            K.rect(ass, x + corners[i][1], y + corners[i][2], tw, tw, hex, "00")
        end
        local hub = math.floor(s * 0.50)
        K.rect(ass, x + (s - hub) / 2, y + (s - hub) / 2, hub, hub, hex, "00")
        if hole then
            local hs = math.floor(s * 0.18)
            K.rect(ass, x + (s - hs) / 2, y + (s - hs) / 2, hs, hs, hole, "00")
        end
    end
end
