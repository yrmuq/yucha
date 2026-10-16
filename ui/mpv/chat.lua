-- Copyright (C) 2026 yrmuq
-- SPDX-License-Identifier: GPL-3.0-or-later
-- Right-side chat. Each line lives for five seconds, then drops off.
-- No panel behind the text: a shadow only, same idea as a stream chat.

local mp = require("mp")

local LIFE = 5
local lines = {}

return function(K)
    local function push(user, text, system)
        lines[#lines + 1] = {
            user = user or "",
            text = text or "",
            system = system and true or false,
            born = mp.get_time(),
        }
        if #lines > 30 then
            table.remove(lines, 1)
        end
    end

    K.on("chat", function(ev)
        push(ev.user, ev.text, false)
    end)

    K.on("chat-local", function(ev)
        push(ev.user, ev.text, true)
    end)

    K.on("conn", function(ev)
        if ev.state == "connected" then
            push("", "connected", true)
        end
    end)

    K.widget(function(ass, w, h)
        local now = mp.get_time()
        local alive = {}
        for i = 1, #lines do
            if now - lines[i].born < LIFE then
                alive[#alive + 1] = lines[i]
            end
        end
        lines = alive
        if #lines == 0 then
            return
        end
        local size = K.m.chat
        local step = size + math.max(4, K.m.gap)
        local total = #lines * step
        local bottom = h - (K.bar_cover or 0)
        local y = math.floor((bottom - total) / 2)
        if y < K.m.gap then y = K.m.gap end
        local x = w - (K.dock or 0) - K.m.margin
        local color = K.cfg.chatColor or "#F4F1EA"
        for i = 1, #lines do
            local line = lines[i]
            local label
            if line.system or line.user == "" then
                label = line.text
            else
                label = line.user .. ": " .. line.text
            end
            -- Shadow so the line stays readable on a bright frame.
            K.text(ass, x + 1, y + 1, 6, size, "#000000", label, "\\alpha&H60&")
            K.text(ass, x, y, 6, size, color, label, "")
            y = y + step
        end
    end)
end
