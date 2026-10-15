-- Copyright (C) 2026 yrmuq
-- SPDX-License-Identifier: GPL-3.0-or-later
-- Slide-out room panel. Fields and the connect action live here.
-- The corner button only calls the "toggle-panel" action.

local OPEN_W = 340

local fields = {
    {id = "host", label = "Server"},
    {id = "port", label = "Port"},
    {id = "name", label = "Username"},
    {id = "password", label = "Password", secret = true},
    {id = "room", label = "Room"},
    {id = "message", label = "Message", chat = true},
}

local focus = nil
local shown = 0
local target = 0

local function clamp_text(value)
    if #value > 240 then
        return value:sub(1, 240)
    end
    return value
end

return function(K)
    local function display(field)
        local value = tostring(K.cfg[field.id] or "")
        if field.secret and value ~= "" then
            return string.rep("•", #value)
        end
        return value
    end

    local function set_focus(id)
        focus = id
        if id then
            K.focus(function(kind, payload)
                if kind == "char" then
                    K.cfg[id] = clamp_text(tostring(K.cfg[id] or "") .. payload)
                elseif kind == "backspace" then
                    local cur = tostring(K.cfg[id] or "")
                    local next_pos = 1
                    -- Drop the last UTF-8 character, not just one byte.
                    local i = 1
                    while i <= #cur do
                        next_pos = i
                        local b = cur:byte(i)
                        if b < 128 then i = i + 1
                        elseif b < 224 then i = i + 2
                        elseif b < 240 then i = i + 3
                        else i = i + 4 end
                    end
                    if next_pos > 1 or #cur > 0 then
                        K.cfg[id] = cur:sub(1, next_pos - 1)
                    end
                elseif kind == "tab" then
                    for i = 1, #fields do
                        if fields[i].id == id then
                            local nxt = fields[(i % #fields) + 1]
                            set_focus(nxt.id)
                            return
                        end
                    end
                elseif kind == "enter" then
                    local field
                    for i = 1, #fields do
                        if fields[i].id == id then field = fields[i] end
                    end
                    if field and field.chat then
                        K.do_("send-chat")
                    else
                        K.do_("connect")
                    end
                elseif kind == "esc" then
                    set_focus(nil)
                end
            end)
        else
            K.focus(nil)
        end
    end

    K.action("toggle-panel", function()
        target = target > 0.5 and 0 or 1
        if target == 0 then
            set_focus(nil)
        end
    end)
    K.action("open-panel", function()
        target = 1
    end)
    K.action("close-panel", function()
        target = 0
        set_focus(nil)
    end)
    K.action("connect", function()
        set_focus(nil)
        K.conn = "connecting"
        K.conn_text = "Connecting..."
        K.send({
            c = "connect",
            host = tostring(K.cfg.host or ""),
            port = tonumber(K.cfg.port) or 8999,
            name = tostring(K.cfg.name or ""),
            password = tostring(K.cfg.password or ""),
            room = tostring(K.cfg.room or ""),
        })
    end)
    K.action("send-chat", function()
        local text = tostring(K.cfg.message or "")
        if text == "" then
            return
        end
        K.send({c = "chat", text = text})
        K.cfg.message = ""
    end)

    K.on("boot", function(ev)
        local form = ev.form or {}
        K.cfg.host = tostring(form.host or K.cfg.host)
        K.cfg.port = tostring(form.port or K.cfg.port)
        K.cfg.name = tostring(form.name or "")
        K.cfg.password = tostring(form.password or "")
        K.cfg.room = tostring(form.room or "")
        if ev.appearance then
            K.cfg.theme = ev.appearance.theme or K.cfg.theme
            K.cfg.chatColor = ev.appearance.chatColor or K.cfg.chatColor
            K.cfg.chatFontSize = tonumber(ev.appearance.chatFontSize) or K.cfg.chatFontSize
        end
        target = ev.openPanel and 1 or 0
        shown = target
    end)

    K.widget(function(ass, w, h)
        shown = shown + (target - shown) * 0.35
        if math.abs(target - shown) < 0.01 then
            shown = target
        end
        if shown < 0.02 then
            return
        end
        local pal = K.palette()
        local margin = 18
        local button = 46
        local height = math.min(560, h - button - margin * 3)
        local y = h - margin - button - 12 - height
        if y < 12 then y = 12 end
        local x = math.floor(w - (OPEN_W * shown) - 12)
        K.rect(ass, x, y, OPEN_W, height, pal.bg, pal.bg_alpha)
        K.hit(x, y, OPEN_W, height, function()
            set_focus(nil)
        end)

        K.text(ass, x + 16, y + 14, 7, 20, pal.fg, "Room", "")
        local gear = 28
        local gx = x + OPEN_W - 16 - gear
        local gy = y + 12
        K.rect(ass, gx, gy, gear, gear, pal.field, pal.field_alpha)
        K.gear(ass, gx + 5, gy + 5, gear - 10, pal.fg, pal.bg)
        K.hit(gx, gy, gear, gear, function()
            K.do_("toggle-settings")
        end)

        local fy = y + 52
        for i = 1, #fields do
            local field = fields[i]
            K.text(ass, x + 16, fy, 7, 13, pal.muted, field.label, "")
            fy = fy + 18
            local fh = 28
            local fw = OPEN_W - 32
            local focused = focus == field.id
            K.rect(ass, x + 16, fy, fw, fh, focused and pal.accent or pal.field, pal.field_alpha)
            local value = display(field)
            if value == "" then
                K.text(ass, x + 24, fy + 6, 7, 15, pal.muted, "", "")
            else
                K.text(ass, x + 24, fy + 6, 7, 15, pal.fg, value, "")
            end
            local id = field.id
            K.hit(x + 16, fy, fw, fh, function()
                set_focus(id)
            end)
            fy = fy + fh + 8
            if field.chat then
                local sw, sh = 72, 28
                local sx = x + OPEN_W - 16 - sw
                K.rect(ass, sx, fy, sw, sh, pal.button, "00")
                K.text(ass, sx + sw / 2, fy + sh / 2, 5, 14, pal.button_fg, "Send", "")
                K.hit(sx, fy, sw, sh, function()
                    K.do_("send-chat")
                end)
                fy = fy + sh + 8
            end
        end

        if K.conn == "failed" and K.conn_text ~= "" then
            K.text(ass, x + 16, fy, 7, 13, "#E07474", K.conn_text, "")
            fy = fy + 22
        elseif K.conn == "connecting" then
            K.text(ass, x + 16, fy, 7, 13, pal.muted, "Connecting...", "")
            fy = fy + 22
        elseif K.conn == "connected" then
            K.text(ass, x + 16, fy, 7, 13, pal.accent, "connected", "")
            fy = fy + 22
        end

        local bw = OPEN_W - 32
        local bh = 34
        local by = math.min(fy, y + height - bh - 28)
        K.rect(ass, x + 16, by, bw, bh, pal.button, "00")
        K.text(ass, x + 16 + bw / 2, by + bh / 2, 5, 16, pal.button_fg, "Connect", "")
        K.hit(x + 16, by, bw, bh, function()
            K.do_("connect")
        end)
        K.text(ass, x + 16, y + height - 20, 7, 12, pal.muted, "Drop a video on this window.", "")
    end)
end
