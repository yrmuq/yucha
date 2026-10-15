-- Copyright (C) 2026 yrmuq
-- SPDX-License-Identifier: GPL-3.0-or-later
-- Loads the UI modules and Syncplay's own mpv script (pause/seek bridge).
-- Syncplay's window is not used. This script is the window UI.

local mp = require("mp")
local opt = require("mp.options")

local src = debug.getinfo(1, "S").source
local dir = src:match("^@(.+)/[^/]+$")
if not dir then
    mp.msg.error("yucha: cannot find its script directory")
    return
end
dir = dir .. "/"

local K = dofile(dir .. "kernel.lua")
local options = {syncplayintf = "", runtime = ""}
opt.read_options(options, "yucha")
K.runtime = options.runtime or ""
mp.msg.info("yucha runtime=" .. K.runtime)

if options.syncplayintf ~= "" then
    mp.commandv("load-script", options.syncplayintf)
    mp.msg.info("yucha loaded syncplayintf")
end

local modules = {
    "theme.lua",
    "draw.lua",
    "chat.lua",
    "status.lua",
    "panel.lua",
    "settings.lua",
    "corner.lua",
}
for i = 1, #modules do
    dofile(dir .. modules[i])(K)
end

K.start()
