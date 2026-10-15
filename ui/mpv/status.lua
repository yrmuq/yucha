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
        local margin = 18
        local button = 46
        local x = w - margin - button - 12
        local y = h - margin - math.floor(button / 2)
        K.text(ass, x + 1, y + 1, 6, 16, "#000000", "connected", "\\alpha&H50&")
        K.text(ass, x, y, 6, 16, K.palette().accent, "connected", "")
    end)
end
