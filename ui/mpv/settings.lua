-- Copyright (C) 2026 yrmuq
-- SPDX-License-Identifier: GPL-3.0-or-later
-- Appearance only: theme, chat color, chat size. Opened by "toggle-settings".

local open = false

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
        local pal = K.palette()
        local bw, bh = 380, 250
        local x = math.floor((w - bw) / 2)
        local y = math.floor((h - bh) / 2)
        K.rect(ass, x, y, bw, bh, pal.bg, "10")
        K.hit(x, y, bw, bh, function() end)
        K.text(ass, x + 18, y + 14, 7, 20, pal.fg, "Settings", "")

        local cx = x + bw - 18 - 28
        K.rect(ass, cx, y + 12, 28, 28, pal.field, pal.field_alpha)
        K.text(ass, cx + 14, y + 26, 5, 14, pal.fg, "x", "")
        K.hit(cx, y + 12, 28, 28, function()
            K.do_("close-settings")
        end)

        K.text(ass, x + 18, y + 58, 7, 14, pal.muted, "Theme", "")
        local labels = {"dark", "light"}
        for i = 1, #labels do
            local name = labels[i]
            local bx = x + 18 + (i - 1) * 110
            local by = y + 80
            local on = K.cfg.theme == name
            K.rect(ass, bx, by, 100, 30, on and pal.button or pal.field, on and "00" or pal.field_alpha)
            K.text(ass, bx + 50, by + 15, 5, 14, on and pal.button_fg or pal.fg, name, "")
            K.hit(bx, by, 100, 30, function()
                K.cfg.theme = name
                publish(K)
            end)
        end

        K.text(ass, x + 18, y + 124, 7, 14, pal.muted, "Chat color", "")
        for i = 1, #swatches do
            local sx = x + 18 + (i - 1) * 36
            local sy = y + 148
            K.rect(ass, sx, sy, 28, 28, swatches[i], "00")
            if K.cfg.chatColor == swatches[i] then
                K.rect(ass, sx - 2, sy - 2, 32, 32, pal.accent, "00")
                K.rect(ass, sx, sy, 28, 28, swatches[i], "00")
            end
            local color = swatches[i]
            K.hit(sx, sy, 28, 28, function()
                K.cfg.chatColor = color
                publish(K)
            end)
        end

        K.text(ass, x + 18, y + 190, 7, 14, pal.muted, "Chat size", "")
        local minus = x + 110
        local sy = y + 184
        K.rect(ass, minus, sy, 28, 28, pal.field, pal.field_alpha)
        K.text(ass, minus + 14, sy + 14, 5, 16, pal.fg, "-", "")
        K.hit(minus, sy, 28, 28, function()
            K.cfg.chatFontSize = math.max(12, (tonumber(K.cfg.chatFontSize) or 18) - 2)
            publish(K)
        end)
        K.text(ass, minus + 46, sy + 14, 4, 16, pal.fg, tostring(K.cfg.chatFontSize), "")
        local plus = minus + 70
        K.rect(ass, plus, sy, 28, 28, pal.field, pal.field_alpha)
        K.text(ass, plus + 14, sy + 14, 5, 16, pal.fg, "+", "")
        K.hit(plus, sy, 28, 28, function()
            K.cfg.chatFontSize = math.min(48, (tonumber(K.cfg.chatFontSize) or 18) + 2)
            publish(K)
        end)
    end)
end
