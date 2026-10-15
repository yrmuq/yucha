-- Copyright (C) 2026 yrmuq
-- SPDX-License-Identifier: GPL-3.0-or-later
-- Two palettes. Modules ask K.palette() and never hard-code a theme.

return function(K)
    K.themes.dark = {
        bg = "#12141A",
        bg_alpha = "28",
        fg = "#F3EFE6",
        muted = "#9A958C",
        accent = "#E0A045",
        field = "#1C1E26",
        field_alpha = "18",
        border = "#34363F",
        button = "#E0A045",
        button_fg = "#1A1408",
        shadow = "#000000",
    }
    K.themes.light = {
        bg = "#F7F4EE",
        bg_alpha = "18",
        fg = "#1A1A1A",
        muted = "#5C584F",
        accent = "#8A5A12",
        field = "#FFFCF7",
        field_alpha = "10",
        border = "#D9D3C7",
        button = "#1A1A1A",
        button_fg = "#F7F4EE",
        shadow = "#FFFFFF",
    }
end
