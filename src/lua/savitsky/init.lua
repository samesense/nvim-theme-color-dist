local M = {}

local registry = require("savitsky.registry")

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
	})

	vim.cmd.colorscheme("catppuccin-" .. theme.flavour)
	vim.cmd("redraw!")
	local theme = registry["industry"]
	assert(
		vim.g.colors_name == ("catppuccin-" .. theme.flavour),
		"colorscheme not active: " .. tostring(vim.g.colors_name)
	)
end

return M
