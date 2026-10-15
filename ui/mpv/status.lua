-- Copyright (C) 2026 yrmuq
-- SPDX-License-Identifier: GPL-3.0-or-later
-- "connected", bottom-right, over the picture. Stays until the link drops.

return function(K)
    K.on("conn", function(ev)
        K.conn = ev.state or K.conn
        K.conn_text = ev.text or ""
        if ev.openPanel then
            K.do_("open-panel")
        end
    end)

    K.widget(function(ass, w, h)
        if K.conn ~= "connected" then
            return
        end
        local m = K.m
        local x = w - m.margin - m.corner - m.gap
        local y = h - m.margin - math.floor(m.corner / 2)
        K.text(ass, x + 1, y + 1, 6, m.button_font, "#000000", "connected", "\\alpha&H50&")
        K.text(ass, x, y, 6, m.button_font, K.palette().accent, "connected", "")
    end)
end
