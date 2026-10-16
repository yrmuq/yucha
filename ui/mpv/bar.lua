-- Copyright (C) 2026 yrmuq
-- SPDX-License-Identifier: GPL-3.0-or-later
-- Playback bar. It uses the theme, hides after 3 seconds, and carries
-- the loop button and the room button at the right end.

local mp = require("mp")

local HIDE = 3
local shown = 1
local last_move = 0
local seen_x = -1
local seen_y = -1

return function(K)
    local function clock(seconds)
        seconds = math.floor(seconds or 0)
        if seconds < 0 then seconds = 0 end
        local hours = math.floor(seconds / 3600)
        local minutes = math.floor(seconds / 60) % 60
        local secs = seconds % 60
        if hours > 0 then
            return string.format("%d:%02d:%02d", hours, minutes, secs)
        end
        return string.format("%d:%02d", minutes, secs)
    end

    local function triangle(ass, x, y, w, h, hex)
        ass:new_event()
        ass:append(string.format(
            "{\\pos(0,0)\\an7\\bord0\\shad0\\1c&H%s&\\p1}m %d %d l %d %d l %d %d{\\p0}",
            K.bgr(hex),
            math.floor(x), math.floor(y),
            math.floor(x), math.floor(y + h),
            math.floor(x + w), math.floor(y + h / 2)
        ))
    end

    local function loop_on()
        local value = mp.get_property("loop-file") or "no"
        return value == "inf" or value == "yes" or value == "always"
    end

    K.layout(function(w, h)
        if last_move == 0 then
            last_move = mp.get_time()
        end
        local m = K.m
        local bar_h = m.bar
        local right = w - (K.dock or 0)
        local pos = mp.get_property_native("mouse-pos")
        local hover = false
        if pos then
            if pos.x ~= seen_x or pos.y ~= seen_y then
                seen_x = pos.x
                seen_y = pos.y
                last_move = mp.get_time()
            end
            if pos.hover ~= false and pos.x >= 0 and pos.x <= right and pos.y >= h - bar_h then
                hover = true
                last_move = mp.get_time()
            end
        end
        local want = 1
        if not hover and mp.get_time() - last_move > HIDE then
            want = 0
        end
        shown = shown + (want - shown) * 0.35
        if math.abs(want - shown) < 0.02 then
            shown = want
        end
        K.bar_cover = math.floor(bar_h * shown + 0.5)
    end)

    K.action("toggle-loop", function()
        if loop_on() then
            mp.set_property("loop-file", "no")
        else
            mp.set_property("loop-file", "inf")
        end
    end)

    K.widget(function(ass, w, h)
        if shown < 0.04 then
            return
        end
        local m = K.m
        local pal = K.palette()
        local bar_h = m.bar
        local right = w - (K.dock or 0)
        if right < bar_h then
            return
        end
        local y = h - math.floor(bar_h * shown)
        local gap = m.gap
        local btn = math.floor(bar_h * 0.62)
        local cy = y + math.floor(bar_h / 2)

        K.rect(ass, 0, y, right, h - y, pal.bg, "00")
        K.rect(ass, 0, y, right, math.max(1, math.floor(m.scale)), pal.border, "00")
        K.hit(0, y, right, h - y, function() end)

        local x = gap
        local paused = mp.get_property_bool("pause")
        if paused == nil then
            paused = true
        end
        local px = x
        local py = cy - math.floor(btn / 2)
        K.hit(px, py, btn, btn, function()
            mp.command("cycle pause")
            last_move = mp.get_time()
        end)
        if paused then
            local tw = math.floor(btn * 0.34)
            local th = math.floor(btn * 0.46)
            triangle(ass, px + math.floor(btn * 0.36), cy - th / 2, tw, th, pal.fg)
        else
            local bw = math.max(2, math.floor(btn * 0.12))
            local bh = math.floor(btn * 0.42)
            local by = cy - bh / 2
            K.rect(ass, px + math.floor(btn * 0.32), by, bw, bh, pal.fg, "00")
            K.rect(ass, px + math.floor(btn * 0.56), by, bw, bh, pal.fg, "00")
        end
        x = x + btn + gap

        local duration = mp.get_property_number("duration", 0) or 0
        local position = mp.get_property_number("time-pos", 0) or 0
        K.text(ass, x, cy, 4, m.label, pal.fg, clock(position), "")
        local time_w = math.floor(m.label * 4.6)
        x = x + time_w

        local cluster = btn * 3 + gap * 2
        local seek_x = x
        local seek_right = right - gap - cluster - gap - time_w
        local seek_w = seek_right - seek_x
        if seek_w < btn then
            seek_w = math.max(btn, right - gap - cluster - seek_x)
            seek_right = seek_x + seek_w
        end
        local seek_h = math.max(4, math.floor(m.scale * 4))
        local seek_y = cy - math.floor(seek_h / 2)
        K.rect(ass, seek_x, seek_y, seek_w, seek_h, pal.border, "00")
        local ratio = 0
        if duration > 0 then
            ratio = position / duration
            if ratio < 0 then ratio = 0 end
            if ratio > 1 then ratio = 1 end
            K.rect(ass, seek_x, seek_y, math.floor(seek_w * ratio), seek_h, pal.accent, "00")
        end
        local knob = math.max(8, math.floor(btn * 0.28))
        local kx = seek_x + math.floor(seek_w * ratio) - math.floor(knob / 2)
        if kx < seek_x then kx = seek_x end
        if kx > seek_x + seek_w - knob then kx = seek_x + seek_w - knob end
        K.rect(ass, kx, cy - knob / 2, knob, knob, pal.fg, "00")
        K.hit(seek_x, y, seek_w, bar_h, function()
            local pos = mp.get_property_native("mouse-pos")
            local dur = mp.get_property_number("duration", 0) or 0
            if not pos or dur <= 0 then
                return
            end
            local at = (pos.x - seek_x) / seek_w
            if at < 0 then at = 0 end
            if at > 1 then at = 1 end
            mp.commandv("seek", tostring(at * dur), "absolute")
            last_move = mp.get_time()
        end)

        local tx = seek_x + seek_w + gap
        K.text(ass, tx, cy, 4, m.label, pal.muted, clock(duration), "")

        local function tool(bx, on, draw, fn)
            local by = cy - math.floor(btn / 2)
            if on then
                K.rect(ass, bx, by, btn, btn, pal.accent, "00")
            end
            draw(on and pal.button_fg or pal.fg)
            K.hit(bx, by, btn, btn, function()
                fn()
                last_move = mp.get_time()
            end)
        end

        local loop_x = right - gap - btn * 3 - gap * 2
        tool(loop_x, loop_on(), function(color)
            K.text(ass, loop_x + btn / 2, cy, 5, m.button_font, color, "↻", "")
        end, function()
            K.do_("toggle-loop")
        end)

        local fs_x = right - gap - btn * 2 - gap
        tool(fs_x, mp.get_property_bool("fullscreen"), function(color)
            local s = math.floor(btn * 0.34)
            local t = math.max(2, math.floor(m.scale))
            local ox = fs_x + math.floor((btn - s) / 2)
            local oy = cy - math.floor(s / 2)
            K.rect(ass, ox, oy, s, t, color, "00")
            K.rect(ass, ox, oy, t, s, color, "00")
            K.rect(ass, ox + s - t, oy, t, s, color, "00")
            K.rect(ass, ox, oy + s - t, s, t, color, "00")
        end, function()
            mp.command("cycle fullscreen")
        end)

        local room_x = right - gap - btn
        local room_on = (K.dock or 0) > 4
        tool(room_x, room_on, function(color)
            local lw = math.floor(btn * 0.42)
            local lh = math.max(2, math.floor(m.scale * 1.4))
            local lx = room_x + math.floor((btn - lw) / 2)
            K.rect(ass, lx, cy - lh * 3, lw, lh, color, "00")
            K.rect(ass, lx, cy - math.floor(lh / 2), lw, lh, color, "00")
            K.rect(ass, lx, cy + lh * 2, lw, lh, color, "00")
        end, function()
            K.do_("toggle-panel")
        end)
    end)
end
