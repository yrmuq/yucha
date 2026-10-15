-- Copyright (C) 2026 yrmuq
-- SPDX-License-Identifier: GPL-3.0-or-later
-- Small UI kernel: theme, actions, hit targets, and the event file.
-- Feature modules register widgets and actions. They do not own input.

local mp = require("mp")
local utils = require("mp.utils")
local assdraw = require("mp.assdraw")

local K = {
    listeners = {},
    actions = {},
    widgets = {},
    hits = {},
    themes = {},
    cfg = {
        theme = "dark",
        chatColor = "#F4F1EA",
        chatFontSize = 18,
        uiFontSize = 16,
        host = "syncplay.pl",
        port = "8999",
        name = "",
        password = "",
        room = "",
    },
    conn = "offline",
    conn_text = "",
    text_handler = nil,
    wants_esc = false,
    runtime = "",
    event_pos = 0,
    screen_scale = 1,
    m = nil,
}

local MAX_HITS = 32
local hit_fns = {}

function K.on(name, fn)
    local list = K.listeners[name]
    if not list then
        list = {}
        K.listeners[name] = list
    end
    list[#list + 1] = fn
end

function K.emit(name, ...)
    local list = K.listeners[name]
    if not list then
        return
    end
    for i = 1, #list do
        list[i](...)
    end
end

function K.action(name, fn)
    K.actions[name] = fn
end

function K.do_(name, ...)
    local fn = K.actions[name]
    if fn then
        return fn(...)
    end
end

function K.widget(draw)
    K.widgets[#K.widgets + 1] = draw
end

function K.hit(x, y, w, h, fn, wheel)
    K.hits[#K.hits + 1] = {x = x, y = y, w = w, h = h, fn = fn, wheel = wheel}
end

function K.palette()
    return K.themes[K.cfg.theme] or K.themes.dark
end

function K.send(obj)
    if K.runtime == "" then
        return
    end
    local handle = io.open(K.runtime .. "/commands.jsonl", "a")
    if not handle then
        return
    end
    handle:write(utils.format_json(obj) .. "\n")
    handle:flush()
    handle:close()
end

function K.size()
    local dim = mp.get_property_native("osd-dimensions")
    local w = (dim and dim.w) or 0
    local h = (dim and dim.h) or 0
    if w < 2 then w = 1280 end
    if h < 2 then h = 720 end
    return w, h
end

-- Sizes are the 1080p design, multiplied by the screen scale and the
-- interface size. The window size is not part of this.
function K.refresh_metrics()
    local scale = K.screen_scale or 1
    if scale < 1 then scale = 1 end
    if scale > 4 then scale = 4 end
    local font = tonumber(K.cfg.uiFontSize) or 16
    if font < 12 then font = 12 end
    if font > 32 then font = 32 end
    local function dp(n)
        return math.max(1, math.floor(n * font / 16 * scale + 0.5))
    end
    local chat = tonumber(K.cfg.chatFontSize) or 18
    K.m = {
        scale = scale,
        ui = font,
        font = dp(15),
        label = dp(13),
        title = dp(20),
        hint = dp(12),
        button_font = dp(16),
        chat = math.max(1, math.floor(chat * scale + 0.5)),
        pad = dp(16),
        gap = dp(8),
        field_h = dp(28),
        btn_h = dp(34),
        panel_w = dp(340),
        corner = dp(46),
        margin = dp(18),
        gear = dp(28),
        send_w = dp(72),
    }
end

function K.focus(handler)
    K.text_handler = handler
    if handler then
        if not K.text_bound then
            mp.add_forced_key_binding("any_unicode", "yucha-unicode", function(info)
                if not K.text_handler or not info or not info.key_text then
                    return
                end
                if info.event ~= "press" and info.event ~= "down" and info.event ~= "repeat" then
                    return
                end
                local text = info.key_text
                if text ~= "\n" and text ~= "\r" and text ~= "\027" then
                    K.text_handler("char", text)
                end
            end, {repeatable = true, complex = true})
            K.text_bound = true
        end
    elseif K.text_bound then
        mp.remove_key_binding("yucha-unicode")
        K.text_bound = false
    end
    K.sync_keys()
end

function K.sync_keys()
    if K.text_handler or K.wants_esc then
        mp.enable_key_bindings("yucha-text")
    else
        mp.disable_key_bindings("yucha-text")
    end
end

local function take_events(data, previous)
    local last_nl = nil
    for i = 1, #data do
        if data:sub(i, i) == "\n" then
            last_nl = i
        end
    end
    if not last_nl then
        return nil, previous
    end
    return data:sub(1, last_nl), previous + last_nl
end

function K.poll_events()
    if K.runtime == "" then
        return
    end
    local handle = io.open(K.runtime .. "/events.jsonl", "r")
    if not handle then
        return
    end
    local size = handle:seek("end")
    if size < K.event_pos then
        K.event_pos = 0
    end
    handle:seek("set", K.event_pos)
    local data = handle:read("*a") or ""
    handle:close()
    if data == "" then
        return
    end
    local chunk, pos = take_events(data, K.event_pos)
    if not chunk then
        return
    end
    K.event_pos = pos
    for line in chunk:gmatch("[^\n]+") do
        local obj = utils.parse_json(line)
        if obj and obj.e then
            K.emit(obj.e, obj)
        end
    end
end

function K.render()
    local w, h = K.size()
    K.refresh_metrics()
    K.hits = {}
    local ass = assdraw.ass_new()
    for i = 1, #K.widgets do
        K.widgets[i](ass, w, h)
    end
    -- Default canvas is 720px tall. These coordinates are window pixels,
    -- so the canvas must match the window or the UI slides off it.
    K.overlay.res_x = w
    K.overlay.res_y = h
    K.overlay.data = ass.text
    K.overlay.z = 20
    K.overlay:update()
    -- One input section per hit, not one box around all of them.
    -- A click on the picture, outside every control, still reaches mpv.
    local n = #K.hits
    if n > MAX_HITS then
        n = MAX_HITS
    end
    for i = 1, n do
        local hit = K.hits[i]
        hit_fns[i] = hit
        local section = "yucha-hit-" .. i
        mp.set_mouse_area(hit.x, hit.y, hit.x + hit.w, hit.y + hit.h, section)
        mp.enable_key_bindings(section)
    end
    for i = n + 1, MAX_HITS do
        if hit_fns[i] ~= nil then
            hit_fns[i] = nil
            mp.disable_key_bindings("yucha-hit-" .. i)
        end
    end
end

function K.start()
    K.overlay = mp.create_osd_overlay("ass-events")
    for i = 1, MAX_HITS do
        local slot = i
        mp.set_key_bindings({
            {"mbtn_left", function()
                local hit = hit_fns[slot]
                if hit and hit.fn then
                    hit.fn()
                end
            end},
            {"wheel_up", function()
                local hit = hit_fns[slot]
                if hit and hit.wheel then
                    hit.wheel(-1)
                end
            end},
            {"wheel_down", function()
                local hit = hit_fns[slot]
                if hit and hit.wheel then
                    hit.wheel(1)
                end
            end},
        }, "yucha-hit-" .. i, "force")
        mp.disable_key_bindings("yucha-hit-" .. i)
    end

    mp.set_key_bindings({
        {"bs", function() if K.text_handler then K.text_handler("backspace") end end},
        {"enter", function() if K.text_handler then K.text_handler("enter") end end},
        {"kp_enter", function() if K.text_handler then K.text_handler("enter") end end},
        {"tab", function() if K.text_handler then K.text_handler("tab") end end},
        {"esc", function()
            if K.text_handler then
                K.text_handler("esc")
            elseif K.wants_esc then
                K.emit("escape")
            end
        end},
    }, "yucha-text", "force")
    mp.disable_key_bindings("yucha-text")

    mp.observe_property("display-hidpi-scale", "number", function(_, value)
        if type(value) == "number" and value >= 1 then
            K.screen_scale = value
        end
    end)

    mp.add_periodic_timer(0.05, function()
        K.poll_events()
        K.render()
    end)
end

return K
