-- Copyright (C) 2026 yrmuq
-- SPDX-License-Identifier: GPL-3.0-or-later
-- The only always-visible control: bottom-right, opens the room panel.

return function(K)
    K.widget(function(ass, w, h)
        local pal = K.palette()
        local m = K.m
        local size = m.corner
        local x = w - m.margin - size
        local y = h - m.margin - size
        K.rect(ass, x, y, size, size, pal.button, "00")
        local bar_w = math.floor(size * 0.48)
        local bar_h = math.max(2, math.floor(size * 0.045))
        local lx = x + math.floor((size - bar_w) / 2)
        local color = pal.button_fg
        K.rect(ass, lx, y + math.floor(size * 0.30), bar_w, bar_h, color, "00")
        K.rect(ass, lx, y + math.floor(size * 0.48), bar_w, bar_h, color, "00")
        K.rect(ass, lx, y + math.floor(size * 0.66), bar_w, bar_h, color, "00")
        K.hit(x, y, size, size, function()
            K.do_("toggle-panel")
        end)
    end)
end
