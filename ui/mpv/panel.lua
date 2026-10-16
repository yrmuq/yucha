-- Copyright (C) 2026 yrmuq
-- SPDX-License-Identifier: GPL-3.0-or-later
-- Full-height room column. The video moves aside while it opens.
-- Fields keep their text inside the box. Ctrl+V pastes.

local mp = require("mp")

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
                elseif kind == "paste" then
                    K.cfg[id] = clamp_text(tostring(K.cfg[id] or "") .. tostring(payload or ""))
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
    end)

    local function column_width(w)
        local want = K.m.panel_w
        local limit = w - math.max(96, K.m.bar * 2)
        if limit < 1 then
            limit = math.max(1, math.floor(w * 0.5))
        end
        if want > limit then
            want = limit
        end
        return want
    end

    local function utf_chars(value)
        local chars = {}
        local i = 1
        while i <= #value do
            local b = value:byte(i)
            local n = 1
            if b >= 240 then n = 4
            elseif b >= 224 then n = 3
            elseif b >= 128 then n = 2
            end
            chars[#chars + 1] = value:sub(i, i + n - 1)
            i = i + n
        end
        return chars
    end

    local function text_px(value, font)
        return math.floor(#utf_chars(value) * font * 0.55)
    end

    local function fit_tail(value, font, max_px)
        if text_px(value, font) <= max_px then
            return value
        end
        local chars = utf_chars(value)
        local out = ""
        for i = #chars, 1, -1 do
            local trial = chars[i] .. out
            if text_px(trial, font) > max_px then
                break
            end
            out = trial
        end
        return out
    end

    K.layout(function(w, h)
        shown = shown + (target - shown) * 0.22
        if math.abs(target - shown) < 0.004 then
            shown = target
        end
        local full = column_width(w)
        K.panel_full = full
        local vis = 0
        if shown > 0 then
            vis = math.floor(full * shown + 0.5)
        end
        K.dock = vis
        local ratio = 0
        if w > 0 then
            ratio = vis / w
        end
        if math.abs(ratio - (K._margin or -1)) > 0.0004 then
            pcall(mp.set_property_number, "video-margin-ratio-right", ratio)
            K._margin = ratio
        end
    end)

    K.widget(function(ass, w, h)
        local vis = K.dock or 0
        if vis < 2 then
            return
        end
        local m = K.m
        local pal = K.palette()
        local full = K.panel_full or column_width(w)
        local pad = m.pad
        local gap = m.gap
        local x = w - full
        local view = {w - vis, 0, w, h}

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
        local max_scroll = math.max(0, header + body - h)
        if scroll < 0 then scroll = 0 end
        if scroll > max_scroll then scroll = max_scroll end

        local function wheel(dir)
            scroll = scroll + dir * (m.field_h + gap)
            if scroll < 0 then scroll = 0 end
            if scroll > max_scroll then scroll = max_scroll end
        end

        K.rect(ass, w - vis, 0, vis, h, pal.bg, "00")
        K.rect(ass, w - vis, 0, math.max(1, math.floor(m.scale)), h, pal.border, "00")
        K.hit(w - vis, 0, vis, h, function()
            set_focus(nil)
        end, wheel)

        local function clip_of(box)
            local x0 = math.max(box[1], view[1])
            local y0 = math.max(box[2], view[2])
            local x1 = math.min(box[3], view[3])
            local y1 = math.min(box[4], view[4])
            if x1 - x0 < 2 or y1 - y0 < 2 then
                return nil
            end
            return {x0, y0, x1, y1}
        end

        local function vishit(hx, hy, hw, hh, fn)
            local box = clip_of({hx, hy, hx + hw, hy + hh})
            if box then
                K.hit(box[1], box[2], box[3] - box[1], box[4] - box[2], fn, wheel)
            end
        end

        K.text(ass, x + pad, pad - scroll, 7, m.title, pal.fg, "Room", "", view)
        local gear = m.gear
        local gx = x + full - pad - gear
        local gy = math.floor((header - gear) / 2) - scroll
        if gx >= w - vis then
            K.rect(ass, gx, gy, gear, gear, pal.field, "00", view)
            local tooth = math.max(2, math.floor(gear * 0.18))
            K.gear(ass, gx + tooth, gy + tooth, gear - tooth * 2, pal.fg, pal.bg)
            vishit(gx, gy, gear, gear, function()
                K.do_("toggle-settings")
            end)
        end

        local fy = header - scroll
        for i = 1, #fields do
            local field = fields[i]
            local label_clip = clip_of({x + pad, fy, x + full - pad, fy + m.label})
            if label_clip then
                K.text(ass, x + pad, fy, 7, m.label, pal.muted, field.label, "", label_clip)
            end
            fy = fy + m.label + row_gap()
            local fh = m.field_h
            local fw = full - pad * 2
            local fx = x + pad
            local focused = focus == field.id
            local box = clip_of({fx, fy, fx + fw, fy + fh})
            if box then
                local edge = math.max(1, math.floor(m.scale))
                K.rect(ass, fx, fy, fw, fh, focused and pal.accent or pal.border, "00", box)
                K.rect(ass, fx + edge, fy + edge, fw - edge * 2, fh - edge * 2, pal.field, "00", box)
                local inner_pad = math.floor(pad / 2)
                local inner = clip_of({
                    fx + inner_pad, fy + edge,
                    fx + fw - inner_pad, fy + fh - edge,
                })
                local value = display(field)
                local shown_text = ""
                if value ~= "" and inner then
                    shown_text = fit_tail(value, m.font, inner[3] - inner[1] - math.max(2, edge))
                    K.text(ass, inner[1], fy + fh / 2, 4, m.font, pal.fg, shown_text, "", inner)
                end
                if focused and inner and math.floor(mp.get_time() * 2) % 2 == 0 then
                    local cx = inner[1] + text_px(shown_text, m.font) + edge
                    if cx > inner[3] - edge then
                        cx = inner[3] - edge
                    end
                    local ch = math.floor(m.font * 0.9)
                    K.rect(ass, cx, fy + (fh - ch) / 2, math.max(1, edge), ch, pal.accent, "00", inner)
                end
            end
            local id = field.id
            vishit(fx, fy, fw, fh, function()
                set_focus(id)
            end)
            fy = fy + fh + gap
            if field.chat then
                local sw, sh = m.send_w, m.field_h
                local sx = x + full - pad - sw
                local send_box = clip_of({sx, fy, sx + sw, fy + sh})
                if send_box then
                    K.rect(ass, sx, fy, sw, sh, pal.button, "00", send_box)
                    K.text(ass, sx + sw / 2, fy + sh / 2, 5, m.label, pal.button_fg, "Send", "", send_box)
                end
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
            local status_clip = clip_of({x + pad, fy, x + full - pad, fy + m.label})
            if status_clip then
                K.text(ass, x + pad, fy, 7, m.label, color, text, "", status_clip)
            end
            fy = fy + m.label + gap
        end

        local bw = full - pad * 2
        local bh = m.btn_h
        local connect_box = clip_of({x + pad, fy, x + pad + bw, fy + bh})
        if connect_box then
            K.rect(ass, x + pad, fy, bw, bh, pal.button, "00", connect_box)
            K.text(ass, x + pad + bw / 2, fy + bh / 2, 5, m.button_font, pal.button_fg, "Connect", "", connect_box)
        end
        vishit(x + pad, fy, bw, bh, function()
            K.do_("connect")
        end)
        fy = fy + bh + gap
        local hint_clip = clip_of({x + pad, fy, x + full - pad, fy + m.hint + 4})
        if hint_clip then
            K.text(ass, x + pad, fy, 7, m.hint, pal.muted, "Drop a video on this window.", "", hint_clip)
        end

        if max_scroll > 0 then
            local track_h = h - header
            local thumb_h = math.floor(track_h * h / (header + body))
            if thumb_h < gap * 2 then thumb_h = gap * 2 end
            if thumb_h > track_h then thumb_h = track_h end
            local thumb_y = header + math.floor((track_h - thumb_h) * scroll / max_scroll)
            local tw = math.max(2, math.floor(gap / 2))
            K.rect(ass, w - pad / 2 - tw, thumb_y, tw, thumb_h, pal.muted, "55", view)
        end
    end)
end

