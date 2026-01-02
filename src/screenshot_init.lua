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

local uv = vim.loop

_G.__codeshot_capture = function(out_path)
	-- Ensure output directory exists
	local out_dir = vim.fn.fnamemodify(out_path, ":p:h")
	vim.fn.mkdir(out_dir, "p")

	-- Verify sss_code exists (required)  [oai_citation:2‡GitHub](https://github.com/SergioRibera/codeshot.nvim)
	if vim.fn.executable("sss_code") ~= 1 then
		error("codeshot: required binary 'sss_code' not found in PATH")
	end

	-- Write current buffer to a temp file (codeshot.take expects a file path)  [oai_citation:3‡GitHub](https://github.com/SergioRibera/codeshot.nvim)
	local tmp = vim.fn.tempname() .. ".lua"
	local buf_lines = vim.api.nvim_buf_get_lines(0, 0, -1, false)
	vim.fn.writefile(buf_lines, tmp)

	-- Full range "1..N"  [oai_citation:4‡GitHub](https://github.com/SergioRibera/codeshot.nvim)
	local n = #buf_lines
	local lines = ("1..%d"):format(n)

	-- Configure output image path, then take screenshot of temp file
	codeshot.setup({
		bin_path = "sss_code", -- default is sss_code  [oai_citation:5‡GitHub](https://github.com/SergioRibera/codeshot.nvim)
		output = out_path, -- absolute path OK  [oai_citation:6‡GitHub](https://github.com/SergioRibera/codeshot.nvim)
		silent = false, -- show errors while debugging  [oai_citation:7‡GitHub](https://github.com/SergioRibera/codeshot.nvim)
		use_current_theme = true, -- match Neovim theme  [oai_citation:8‡GitHub](https://github.com/SergioRibera/codeshot.nvim)
		show_line_numbers = true,
		shadow = false,
		save_format = "png",
	})

	codeshot.take(tmp, "lua", lines, nil) -- file=tmp, lines="start..end"  [oai_citation:9‡GitHub](https://github.com/SergioRibera/codeshot.nvim)

	-- Wait for async renderer to finish writing output
	local ok = vim.wait(15000, function()
		return uv.fs_stat(out_path) ~= nil
	end, 50)

	if not ok then
		error("codeshot: timed out waiting for output file: " .. out_path)
	end
end
