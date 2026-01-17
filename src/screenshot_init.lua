------------------------------------------------------------
-- /Users/perry/projects/nvim-theme-color-dist/src/screenshot_init.lua
-- Deterministic Neovide init for fully-automated screenshots (no clicking)
--
-- Requirements:
--   - Neovide installed
--   - macOS: Screen Recording permission granted to your terminal (and/or Neovide)
--   - uv env includes: pyobjc-framework-Quartz
--       uv add pyobjc-framework-Quartz
--
-- Helper file (same directory as this init):
--   /Users/perry/projects/nvim-theme-color-dist/src/get_neovide_cgwindowid.py
--   (script prints Neovide CGWindowID)
--
-- Usage:
--   neovide -- \
--     -u "/Users/perry/projects/nvim-theme-color-dist/src/screenshot_init.lua" \
--     +'lua run_screenshot([[industry]], [[/Users/perry/projects/nvim-theme-color-dist/src/extract_colors.py]], 82, [[/Users/perry/projects/nvim-theme-color-dist/docs/demo/savitsky/industry.png]])'
------------------------------------------------------------

-- Root = directory containing this init file (src/)
local this = debug.getinfo(1, "S").source:sub(2)
local root = vim.fn.fnamemodify(this, ":p:h")

-- Make local ./lua/savitsky discoverable
vim.opt.runtimepath:prepend(root)

-- Vendored catppuccin
vim.opt.runtimepath:prepend(root .. "/vendor/catppuccin")

-- Stable options (safe in Neovide)
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
vim.opt.cmdheight = 1

local function log(msg)
	vim.api.nvim_err_writeln("[screenshot-init] " .. msg)
end

local function trim(s)
	return (s or ""):gsub("%s+$", ""):gsub("^%s+", "")
end

-- Load deps + your local savitsky module
require("catppuccin")
require("savitsky").setup()

-- ------------------------------------------------------------
-- Filesystem helpers
-- ------------------------------------------------------------

local function wait_for_file(path, timeout_ms)
	local uv = vim.loop
	local start = uv.now()
	while (uv.now() - start) < timeout_ms do
		if uv.fs_stat(path) ~= nil then
			return true
		end
		vim.wait(80)
	end
	return false
end

-- ------------------------------------------------------------
-- macOS capture helpers (NO CLICKING)
-- ------------------------------------------------------------
--
local function activate_neovide()
	vim.fn.system({
		"osascript",
		"-e",
		[[
      tell application "Neovide"
        activate
      end tell
      delay 0.2
      tell application "System Events"
        tell process "Neovide"
          if (count of windows) > 0 then
            set frontmost to true
            set value of attribute "AXMain" of window 1 to true
          end if
        end tell
      end tell
    ]],
	})
end

local function get_neovide_cgwindowid()
	-- Use your uv environment so Quartz import works.
	-- Expects: root/get_neovide_window_id.py
	local script = root .. "/get_neovide_window_id.py"
	if vim.fn.filereadable(script) ~= 1 then
		error("Missing helper script: " .. script)
	end

	-- Run from src/ dir where .venv lives, capture stdout+stderr
	local out = vim.fn.system({ "uv", "run", "--directory", root, "python", script })
	local exit_code = vim.v.shell_error
	-- Log full output for debugging
	if trim(out) ~= "" then
		log("get_neovide_window_id.py output: " .. trim(out))
	end
	if exit_code ~= 0 then
		log("get_neovide_window_id.py failed (exit " .. exit_code .. ")")
		return nil
	end
	-- Find a line that is purely digits (the window ID), ignoring uv's extra output
	for line in out:gmatch("[^\r\n]+") do
		local id = trim(line):match("^(%d+)$")
		if id then
			return id
		end
	end
	return nil
end

local function screencap_cgwindowid(cg_id, out_path)
	-- -x: no UI sounds/flash
	-- -l <CGWindowID>: capture specific window (no interaction)
	local cmd = string.format([[screencapture -w -x -l %s %q]], cg_id, out_path)
	local ok = os.execute(cmd)
	return ok == true or ok == 0
end

local function set_filetype_from_ext(file_path)
	local ext = vim.fn.fnamemodify(file_path, ":e")
	if ext == "py" then
		vim.bo.filetype = "python"
	elseif ext ~= "" then
		vim.bo.filetype = ext
	end
end

-- ------------------------------------------------------------
-- Public entrypoint:
--   run_screenshot(theme_name, file_path, start_line, out_path)
-- ------------------------------------------------------------

_G.run_screenshot = function(theme_name, file_path, start_line, out_path)
	assert(type(theme_name) == "string" and theme_name ~= "", "theme_name must be a non-empty string")
	assert(type(file_path) == "string" and file_path ~= "", "file_path must be a non-empty string")
	assert(type(start_line) == "number" and start_line >= 1, "start_line must be a number >= 1")
	assert(type(out_path) == "string" and out_path ~= "", "out_path must be a non-empty string")

	-- Ensure output directory exists
	local out_dir = vim.fn.fnamemodify(out_path, ":p:h")
	vim.fn.mkdir(out_dir, "p")

	-- Validate input file exists
	if vim.fn.filereadable(file_path) ~= 1 then
		error("Cannot read file: " .. file_path)
	end

	-- Load theme (catppuccin override happens here)
	require("savitsky").load(theme_name)

	-- Open file
	vim.cmd("silent! edit " .. vim.fn.fnameescape(file_path))
	vim.bo.swapfile = false
	set_filetype_from_ext(file_path)

	-- Go to line, center view, redraw
	vim.cmd(("normal! %dG"):format(start_line))
	vim.cmd("normal! zz")
	vim.cmd("redraw!")

	-- Delay to allow Neovide to fully render themed highlights
	vim.defer_fn(function()
		activate_neovide()
		vim.wait(1200)

		local cg_id
		for _ = 1, 5 do
			cg_id = get_neovide_cgwindowid()
			if cg_id then
				break
			end
			vim.wait(400)
		end

		if not cg_id then
			error("Could not find Neovide CGWindowID (Quartz). Check Screen Recording permission.")
		end

		log("Capturing Neovide CGWindowID=" .. cg_id)

		local ok = screencap_cgwindowid(cg_id, out_path)
		if not ok then
			error("screencapture failed (check Screen Recording permission for your terminal/Neovide)")
		end

		if not wait_for_file(out_path, 7000) then
			error("Timed out waiting for screenshot: " .. out_path)
		end

		vim.cmd("qa!")
	end, 900)
end

log("loaded; call: lua run_screenshot([[theme]], [[file]], line, [[out.png]])")
