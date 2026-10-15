-- Copyright (C) 2026 yrmuq
-- SPDX-License-Identifier: GPL-3.0-or-later
-- Slide-out room panel. Fields and the connect action live here.
-- The corner button only calls the "toggle-panel" action.

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
local scroll = 0

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
            K.cfg.uiFontSize = tonumber(ev.appearance.uiFontSize) or K.cfg.uiFontSize
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
        local m = K.m
        local pal = K.palette()
        local pad = m.pad
        local gap = m.gap
        local width = m.panel_w
        local max_w = w - m.margin * 2
        if max_w > m.field_h * 4 and width > max_w then
            width = max_w
        end

        local function row_gap()
            return math.max(2, math.floor(gap / 2))
        end

        local body = 0
        for i = 1, #fields do
            body = body + m.label + row_gap() + m.field_h + gap
            if fields[i].chat then
                body = body + m.field_h + gap
            end
        end
        local has_status = (K.conn == "failed" and K.conn_text ~= "")
            or K.conn == "connecting" or K.conn == "connected"
        if has_status then
            body = body + m.label + gap
        end
        body = body + m.btn_h + gap + m.hint + pad

        local header = pad + math.max(m.title, m.gear) + gap
        local avail = h - m.margin * 2 - m.corner - gap
        if avail < header + m.field_h then
            avail = header + m.field_h
        end
        local viewport = math.min(header + body, avail)
        local max_scroll = math.max(0, body - (viewport - header))
        if scroll < 0 then scroll = 0 end
        if scroll > max_scroll then scroll = max_scroll end

        local function wheel(dir)
            scroll = scroll + dir * (m.field_h + gap)
            if scroll < 0 then scroll = 0 end
            if scroll > max_scroll then scroll = max_scroll end
        end

        local y = math.floor(h - m.margin - m.corner - gap - viewport)
        if y < m.margin then y = m.margin end
        local x = math.floor(w - m.margin - width * shown)

        K.rect(ass, x, y, width, viewport, pal.bg, pal.bg_alpha)
        K.hit(x, y, width, viewport, function()
            set_focus(nil)
        end, wheel)

        K.text(ass, x + pad, y + pad, 7, m.title, pal.fg, "Room", "")
        local gear = m.gear
        local gx = x + width - pad - gear
        local gy = y + math.floor((header - gear) / 2)
        K.rect(ass, gx, gy, gear, gear, pal.field, pal.field_alpha)
        local tooth = math.max(2, math.floor(gear * 0.18))
        K.gear(ass, gx + tooth, gy + tooth, gear - tooth * 2, pal.fg, pal.bg)
        K.hit(gx, gy, gear, gear, function()
            K.do_("toggle-settings")
        end, wheel)

        local clip = {x, y + header, x + width, y + viewport}

        local function vishit(hx, hy, hw, hh, fn)
            local x0 = math.max(hx, clip[1])
            local y0 = math.max(hy, clip[2])
            local x1 = math.min(hx + hw, clip[3])
            local y1 = math.min(hy + hh, clip[4])
            if x1 - x0 >= 2 and y1 - y0 >= 2 then
                K.hit(x0, y0, x1 - x0, y1 - y0, fn, wheel)
            end
        end

        local fy = y + header - scroll
        for i = 1, #fields do
            local field = fields[i]
            K.text(ass, x + pad, fy, 7, m.label, pal.muted, field.label, "", clip)
            fy = fy + m.label + row_gap()
            local fh = m.field_h
            local fw = width - pad * 2
            local focused = focus == field.id
            K.rect(ass, x + pad, fy, fw, fh, focused and pal.accent or pal.field, pal.field_alpha, clip)
            local value = display(field)
            if value ~= "" then
                local ty = fy + math.floor((fh - m.font) / 2)
                K.text(ass, x + pad + math.floor(pad / 2), ty, 7, m.font, pal.fg, value, "", clip)
            end
            local id = field.id
            vishit(x + pad, fy, fw, fh, function()
                set_focus(id)
            end)
            fy = fy + fh + gap
            if field.chat then
                local sw, sh = m.send_w, m.field_h
                local sx = x + width - pad - sw
                K.rect(ass, sx, fy, sw, sh, pal.button, "00", clip)
                K.text(ass, sx + sw / 2, fy + sh / 2, 5, m.label, pal.button_fg, "Send", "", clip)
                vishit(sx, fy, sw, sh, function()
                    K.do_("send-chat")
                end)
                fy = fy + sh + gap
            end
        end

        if has_status then
            local text, color = "", pal.muted
            if K.conn == "failed" then
                text, color = K.conn_text, "#E07474"
            elseif K.conn == "connecting" then
                text = "Connecting..."
            else
                text, color = "connected", pal.accent
            end
            K.text(ass, x + pad, fy, 7, m.label, color, text, "", clip)
            fy = fy + m.label + gap
        end

        local bw = width - pad * 2
        local bh = m.btn_h
        K.rect(ass, x + pad, fy, bw, bh, pal.button, "00", clip)
        K.text(ass, x + pad + bw / 2, fy + bh / 2, 5, m.button_font, pal.button_fg, "Connect", "", clip)
        vishit(x + pad, fy, bw, bh, function()
            K.do_("connect")
        end)
        fy = fy + bh + gap
        K.text(ass, x + pad, fy, 7, m.hint, pal.muted, "Drop a video on this window.", "", clip)

        if max_scroll > 0 then
            local track_y = y + header
            local track_h = viewport - header
            local thumb_h = math.floor(track_h * track_h / (track_h + max_scroll))
            if thumb_h < gap * 2 then thumb_h = gap * 2 end
            if thumb_h > track_h then thumb_h = track_h end
            local travel = track_h - thumb_h
            local thumb_y = track_y + math.floor(travel * scroll / max_scroll)
            local tw = math.max(2, math.floor(gap / 2))
            K.rect(ass, x + width - math.floor(pad / 2) - tw, thumb_y, tw, thumb_h, pal.muted, "55")
        end
    end)
end
