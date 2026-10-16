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
        local x = w - (K.dock or 0) - m.margin
        local y = h - (K.bar_cover or 0) - m.gap
        K.text(ass, x + 1, y + 1, 9, m.label, "#000000", "connected", "\\alpha&H50&")
        K.text(ass, x, y, 9, m.label, K.palette().accent, "connected", "")
    end)
end
