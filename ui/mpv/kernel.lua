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

function K.hit(x, y, w, h, fn)
    K.hits[#K.hits + 1] = {x = x, y = y, w = w, h = h, fn = fn}
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
    K.hits = {}
    local ass = assdraw.ass_new()
    for i = 1, #K.widgets do
        K.widgets[i](ass, w, h)
    end
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
        hit_fns[i] = hit.fn
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
                local fn = hit_fns[slot]
                if fn then
                    fn()
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

    mp.add_periodic_timer(0.05, function()
        K.poll_events()
        K.render()
    end)
end

return K
