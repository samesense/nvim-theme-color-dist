------------------------------------------------------------
-- Deterministic Neovim init for codeshot.nvim (headless)
-- Root is derived from this file's location, not CWD.
------------------------------------------------------------

-- Where is THIS init file?
local this = debug.getinfo(1, "S").source:sub(2)
local this_dir = vim.fn.fnamemodify(this, ":p:h")

-- Repo root: if init is in src/ or scripts/, root is one level up.
-- If you move it later, adjust this.
local root = vim.fn.fnamemodify(this_dir, ":p:h")

-- Put repo root on runtimepath so `lua/savitsky` is discoverable
vim.opt.runtimepath:prepend(root)

-- Vendored plugins (relative to repo root)
vim.opt.runtimepath:prepend(root .. "/vendor/catppuccin")
vim.opt.runtimepath:prepend(root .. "/vendor/codeshot.nvim")

-- Basic stable options
vim.opt.swapfile = false
vim.opt.undofile = false
vim.opt.shada = ""
vim.opt.termguicolors = true
vim.opt.number = true
vim.opt.relativenumber = false
vim.opt.cursorline = true
vim.opt.signcolumn = "yes"
vim.opt.wrap = false
vim.opt.showmode = false
vim.opt.laststatus = 2
vim.opt.cmdheight = 0
vim.opt.guifont = "Berkeley Mono:h14"

-- Load dependencies + your plugin
require("catppuccin")
require("savitsky").setup()

local codeshot = require("codeshot")
codeshot.setup({
	silent = true,
	use_current_theme = true,
	show_line_numbers = false,
	shadow = false,
	save_format = "png",
})

-- Buffer content to screenshot
vim.cmd("enew")
vim.bo.filetype = "lua"
vim.api.nvim_buf_set_lines(0, 0, -1, false, {
	"-- Theme preview",
	"",
	"local function hello(name)",
	"  if name == nil then",
	"    return 'world'",
	"  end",
	"  return 'hello ' .. name",
	"end",
	"",
	"print(hello('neovim'))",
})

-- Select whole buffer for codeshot.selected_lines()
vim.cmd("normal! ggVG")
vim.bo.modified = false

_G.__codeshot_capture = function(out_path)
	codeshot.setup({ output = out_path })
	codeshot.selected_lines()
end
