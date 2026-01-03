------------------------------------------------------------
-- Minimal headless highlight probe
------------------------------------------------------------

-- Resolve repo root
local this = debug.getinfo(1, "S").source:sub(2)
local this_dir = vim.fn.fnamemodify(this, ":p:h")
local root = vim.fn.fnamemodify(this_dir, ":p:h")

-- Put repo root on runtimepath so `lua/savitsky` is discoverable
vim.opt.runtimepath:prepend(this_dir)

-- Vendored plugins (relative to repo root)
vim.opt.runtimepath:prepend(root .. "/vendor/catppuccin")
vim.opt.runtimepath:prepend(root .. "/vendor/codeshot.nvim")

-- Apply theme
require("savitsky").load("industry")

local function hex(n)
	if not n then
		return nil
	end
	return string.format("#%06x", n)
end

local function dump(group)
	local ok, hl = pcall(vim.api.nvim_get_hl, 0, { name = group, link = false })
	if not ok then
		return { error = "missing" }
	end
	return {
		fg = hex(hl.fg),
		bg = hex(hl.bg),
		bold = hl.bold or false,
		italic = hl.italic or false,
		underline = hl.underline or false,
	}
end

local report = {
	colors_name = vim.g.colors_name,
	background = vim.o.background,
	Normal = dump("Normal"),
	Comment = dump("Comment"),
	Keyword = dump("Keyword"),
	String = dump("String"),
	LineNr = dump("LineNr"),
	CursorLine = dump("CursorLine"),
}

vim.fn.writefile({ vim.json.encode(report) }, root .. "/.debug_hl.json")
local cp = require("catppuccin.palettes").get_palette("mocha")
vim.fn.writefile(
	{
		vim.inspect({
			blue = cp.blue,
			sapphire = cp.sapphire,
			sky = cp.sky,
			lavender = cp.lavender,
			mauve = cp.mauve,
			text = cp.text,
			base = cp.base,
		}),
	},
	root .. "/.debug_palette_roles.txt"
)

vim.cmd("qa!")
