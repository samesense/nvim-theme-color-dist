local M = {}

local registry = require("savitsky.registry")
local highlights = require("savitsky.highlights.default") -- shared highlight function

function M.setup()
	-- optional: nothing required here, but keep for API symmetry
end

function M.load(name)
	local theme = registry[name]
	if not theme then
		error("Unknown theme: " .. name)
	end

	local cp = require("catppuccin")

	-- IMPORTANT: override ONLY the selected theme for its flavour
	cp.setup({
		flavour = theme.flavour,
		color_overrides = {
			[theme.flavour] = theme.palette,
		},
		highlight_overrides = {
			[theme.flavour] = highlights,
		},
	})

	vim.cmd.colorscheme("catppuccin-" .. theme.flavour)
end

return M
