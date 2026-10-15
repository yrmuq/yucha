-- Copyright (C) 2026 yrmuq
-- SPDX-License-Identifier: GPL-3.0-or-later
-- The only always-visible control: bottom-right, opens the room panel.

return function(K)
    K.widget(function(ass, w, h)
        local pal = K.palette()
        local size = 46
        local margin = 18
        local x = w - margin - size
        local y = h - margin - size
        K.rect(ass, x, y, size, size, pal.button, "00")
        local lx = x + 12
        local color = pal.button_fg
        K.rect(ass, lx, y + 14, 22, 2, color, "00")
        K.rect(ass, lx, y + 22, 22, 2, color, "00")
        K.rect(ass, lx, y + 30, 22, 2, color, "00")
        K.hit(x, y, size, size, function()
            K.do_("toggle-panel")
        end)
    end)
end
