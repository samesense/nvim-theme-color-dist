return function(c)
	return {
		-- CORE SYNTAX
		Comment = { fg = c.overlay0, italic = true },
		Keyword = { fg = c.mauve, bold = true },
		Conditional = { fg = c.mauve, bold = true },
		Repeat = { fg = c.mauve, bold = true },

		Function = { fg = c.peach },
		Identifier = { fg = c.text },
		String = { fg = c.flamingo },
		Number = { fg = c.yellow },
		Operator = { fg = c.lavender }, -- was c.sky

		-- LINE NUMBERS
		LineNr = { fg = c.overlay1 },
		CursorLineNr = { fg = c.peach, bold = true },

		-- CURSOR LINE
		CursorLine = { bg = c.mantle },
		CursorColumn = { bg = c.mantle },

		-- VISUAL
		Visual = { bg = c.surface1 },

		-- FLOATS
		NormalFloat = { fg = c.text, bg = c.base },
		FloatBorder = { fg = c.lavender, bg = c.base }, -- was c.sapphire

		-- STATUSLINE
		StatusLine = { fg = c.text, bg = c.crust },
		StatusLineNC = { fg = c.overlay1, bg = c.crust },
		StatusLineTerm = { fg = c.text, bg = c.crust },
		StatusLineTermNC = { fg = c.overlay1, bg = c.crust },

		-- MINI.STATUSLINE
		MiniStatuslineModeNormal = { fg = c.base, bg = c.mauve, bold = true }, -- was c.blue
		MiniStatuslineModeInsert = { fg = c.base, bg = c.green, bold = true },
		MiniStatuslineModeVisual = { fg = c.base, bg = c.peach, bold = true },
		MiniStatuslineModeReplace = { fg = c.base, bg = c.red, bold = true },
		MiniStatuslineModeCommand = { fg = c.base, bg = c.lavender, bold = true }, -- was c.sapphire

		MiniStatuslineFilename = { fg = c.text, bg = c.mantle },
		MiniStatuslineDevinfo = { fg = c.text, bg = c.mantle },
		MiniStatuslineInactive = { fg = c.overlay1, bg = c.crust },

		-- TABLINE
		TabLine = { fg = c.overlay1, bg = c.crust },
		TabLineSel = { fg = c.text, bg = c.mauve }, -- was c.blue
		TabLineFill = { fg = c.overlay0, bg = c.crust },
	}
end
