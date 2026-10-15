-- Copyright (C) 2026 yrmuq
-- SPDX-License-Identifier: GPL-3.0-or-later
-- Appearance only: theme, chat color, chat size. Opened by "toggle-settings".

local open = false
local scroll = 0

local swatches = {
    "#F4F1EA",
    "#111111",
    "#E0A045",
    "#7DCEA0",
    "#85C1E9",
    "#F5B7B1",
}

local function publish(K)
    K.send({
        c = "appearance",
        theme = K.cfg.theme,
        chatColor = K.cfg.chatColor,
        chatFontSize = K.cfg.chatFontSize,
        uiFontSize = K.cfg.uiFontSize,
    })
end

return function(K)
    K.action("toggle-settings", function()
        open = not open
        K.wants_esc = open
        K.sync_keys()
    end)
    K.action("close-settings", function()
        open = false
        K.wants_esc = false
        K.sync_keys()
    end)
    K.on("escape", function()
        if open then
            K.do_("close-settings")
        end
    end)

    K.widget(function(ass, w, h)
        if not open then
            return
        end
        local m = K.m
        local pal = K.palette()
        local pad = m.pad
        local gap = m.gap
        local bw = m.panel_w + pad
        local label_h = m.label + math.max(2, math.floor(gap / 2))
        local swatch = m.field_h
        local body = label_h + m.field_h + gap
        body = body + label_h + swatch + gap
        body = body + label_h + m.field_h + gap
        body = body + label_h + m.field_h + pad
        local header = pad + m.gear
        local content = header + gap + body
        local avail = h - m.margin * 2
        local viewport = math.min(content, avail)
        local max_scroll = math.max(0, body - (viewport - header - gap))
        if scroll < 0 then scroll = 0 end
        if scroll > max_scroll then scroll = max_scroll end

        local function wheel(dir)
            scroll = scroll + dir * (m.field_h + gap)
            if scroll < 0 then scroll = 0 end
            if scroll > max_scroll then scroll = max_scroll end
        end

        local x = math.floor((w - bw) / 2)
        local y = math.floor((h - viewport) / 2)
        if y < m.margin then y = m.margin end

        K.rect(ass, x, y, bw, viewport, pal.bg, "10")
        K.hit(x, y, bw, viewport, function() end, wheel)
        K.text(ass, x + pad, y + math.floor((header - m.title) / 2), 7, m.title, pal.fg, "Settings", "")

        local close = m.gear
        local cx = x + bw - pad - close
        local cy = y + math.floor((header - close) / 2)
        K.rect(ass, cx, cy, close, close, pal.field, pal.field_alpha)
        K.text(ass, cx + close / 2, cy + close / 2, 5, m.label, pal.fg, "x", "")
        K.hit(cx, cy, close, close, function()
            K.do_("close-settings")
        end, wheel)

        local clip = {x, y + header, x + bw, y + viewport}

        local function vishit(hx, hy, hw, hh, fn)
            local x0 = math.max(hx, clip[1])
            local y0 = math.max(hy, clip[2])
            local x1 = math.min(hx + hw, clip[3])
            local y1 = math.min(hy + hh, clip[4])
            if x1 - x0 >= 2 and y1 - y0 >= 2 then
                K.hit(x0, y0, x1 - x0, y1 - y0, fn, wheel)
            end
        end

        local function stepper(sy, value, on_minus, on_plus)
            local side = m.field_h
            local num_w = side + gap
            local minus = x + pad
            local plus = minus + side + gap + num_w
            K.rect(ass, minus, sy, side, side, pal.field, pal.field_alpha, clip)
            K.text(ass, minus + side / 2, sy + side / 2, 5, m.button_font, pal.fg, "-", "", clip)
            vishit(minus, sy, side, side, on_minus)
            K.text(ass, minus + side + gap + num_w / 2, sy + side / 2, 5, m.button_font, pal.fg, tostring(value), "", clip)
            K.rect(ass, plus, sy, side, side, pal.field, pal.field_alpha, clip)
            K.text(ass, plus + side / 2, sy + side / 2, 5, m.button_font, pal.fg, "+", "", clip)
            vishit(plus, sy, side, side, on_plus)
        end

        local fy = y + header + gap - scroll
        K.text(ass, x + pad, fy, 7, m.label, pal.muted, "Theme", "", clip)
        fy = fy + label_h
        local labels = {"dark", "light"}
        local btn_w = math.floor((bw - pad * 2 - gap) / 2)
        for i = 1, #labels do
            local name = labels[i]
            local bx = x + pad + (i - 1) * (btn_w + gap)
            local on = K.cfg.theme == name
            K.rect(ass, bx, fy, btn_w, m.field_h, on and pal.button or pal.field, on and "00" or pal.field_alpha, clip)
            K.text(ass, bx + btn_w / 2, fy + m.field_h / 2, 5, m.label, on and pal.button_fg or pal.fg, name, "", clip)
            vishit(bx, fy, btn_w, m.field_h, function()
                K.cfg.theme = name
                publish(K)
            end)
        end
        fy = fy + m.field_h + gap

        K.text(ass, x + pad, fy, 7, m.label, pal.muted, "Chat color", "", clip)
        fy = fy + label_h
        for i = 1, #swatches do
            local sx = x + pad + (i - 1) * (swatch + math.floor(gap / 2))
            K.rect(ass, sx, fy, swatch, swatch, swatches[i], "00", clip)
            if K.cfg.chatColor == swatches[i] then
                K.rect(ass, sx, fy, swatch, swatch, pal.accent, "00", clip)
                local inset = math.max(2, math.floor(swatch * 0.12))
                K.rect(ass, sx + inset, fy + inset, swatch - inset * 2, swatch - inset * 2, swatches[i], "00", clip)
            end
            local color = swatches[i]
            vishit(sx, fy, swatch, swatch, function()
                K.cfg.chatColor = color
                publish(K)
            end)
        end
        fy = fy + swatch + gap

        K.text(ass, x + pad, fy, 7, m.label, pal.muted, "Chat size", "", clip)
        fy = fy + label_h
        stepper(fy, K.cfg.chatFontSize, function()
            K.cfg.chatFontSize = math.max(12, (tonumber(K.cfg.chatFontSize) or 18) - 2)
            publish(K)
        end, function()
            K.cfg.chatFontSize = math.min(48, (tonumber(K.cfg.chatFontSize) or 18) + 2)
            publish(K)
        end)
        fy = fy + m.field_h + gap

        K.text(ass, x + pad, fy, 7, m.label, pal.muted, "Interface", "", clip)
        fy = fy + label_h
        stepper(fy, K.cfg.uiFontSize, function()
            K.cfg.uiFontSize = math.max(12, (tonumber(K.cfg.uiFontSize) or 16) - 2)
            publish(K)
        end, function()
            K.cfg.uiFontSize = math.min(32, (tonumber(K.cfg.uiFontSize) or 16) + 2)
            publish(K)
        end)

        if max_scroll > 0 then
            local track_y = y + header
            local track_h = viewport - header
            local thumb_h = math.floor(track_h * track_h / (track_h + max_scroll))
            if thumb_h < gap * 2 then thumb_h = gap * 2 end
            if thumb_h > track_h then thumb_h = track_h end
            local thumb_y = track_y + math.floor((track_h - thumb_h) * scroll / max_scroll)
            local tw = math.max(2, math.floor(gap / 2))
            K.rect(ass, x + bw - math.floor(pad / 2) - tw, thumb_y, tw, thumb_h, pal.muted, "55")
        end
    end)
end
