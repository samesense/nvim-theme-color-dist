-- Central highlight intent for all themes
-- Palette-independent: only references semantic colors via `c`

return function(c)
	return {
		------------------------------------------------------------------
		-- CORE SYNTAX
		------------------------------------------------------------------
		Comment = { fg = c.overlay0, italic = true },
		Keyword = { fg = c.blue, bold = true },
		Conditional = { fg = c.blue, bold = true },
		Repeat = { fg = c.blue, bold = true },

		Function = { fg = c.peach },
		Identifier = { fg = c.text },
		String = { fg = c.flamingo },
		Number = { fg = c.yellow },
		Operator = { fg = c.sky },

		------------------------------------------------------------------
		-- LINE NUMBERS
		------------------------------------------------------------------
		LineNr = { fg = c.overlay1 },
		CursorLineNr = { fg = c.peach, bold = true },

		------------------------------------------------------------------
		-- CURSOR LINE / COLUMN (readability fix)
		------------------------------------------------------------------
		CursorLine = { bg = c.mantle },
		CursorColumn = { bg = c.mantle },

		------------------------------------------------------------------
		-- VISUAL SELECTION
		------------------------------------------------------------------
		Visual = { bg = c.surface1 },

		------------------------------------------------------------------
		-- FLOATING WINDOWS
		------------------------------------------------------------------
		NormalFloat = { fg = c.text, bg = c.base },
		FloatBorder = { fg = c.sapphire, bg = c.base },

		------------------------------------------------------------------
		-- STATUSLINE (avoid unreadable blocks)
		------------------------------------------------------------------
		StatusLine = { fg = c.text, bg = c.crust },
		StatusLineNC = { fg = c.overlay1, bg = c.crust },
		StatusLineTerm = { fg = c.text, bg = c.crust },
		StatusLineTermNC = { fg = c.overlay1, bg = c.crust },

		------------------------------------------------------------------
		-- MINI.STATUSLINE (mode-aware accents)
		------------------------------------------------------------------
		MiniStatuslineModeNormal = { fg = c.base, bg = c.blue, bold = true },
		MiniStatuslineModeInsert = { fg = c.base, bg = c.green, bold = true },
		MiniStatuslineModeVisual = { fg = c.base, bg = c.peach, bold = true },
		MiniStatuslineModeReplace = { fg = c.base, bg = c.red, bold = true },
		MiniStatuslineModeCommand = { fg = c.base, bg = c.sapphire, bold = true },

		MiniStatuslineFilename = { fg = c.text, bg = c.mantle },
		MiniStatuslineDevinfo = { fg = c.text, bg = c.mantle },
		MiniStatuslineInactive = { fg = c.overlay1, bg = c.crust },

		------------------------------------------------------------------
		-- TABLINE
		------------------------------------------------------------------
		TabLine = { fg = c.overlay1, bg = c.crust },
		TabLineSel = { fg = c.text, bg = c.blue },
		TabLineFill = { fg = c.overlay0, bg = c.crust },
	}
end
