# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A pipeline for extracting color palettes from images (paintings, photos) and mapping them into Catppuccin-style Neovim themes. The goal is to derive coherent editor themes from visual sources using perceptual color spaces (CIELAB/LCh) and structural constraints.

## Build Commands

All Python scripts run from `src/` directory using a local venv with uv:

```bash
cd src
source .venv/bin/activate  # or use uv run

# Run the full pipeline via Snakemake
snakemake -s Snakefile.py -j1

# Run a single step (example: extract colors from an image)
python extract_colors.py data/raw/photos/industry.png \
    --constraints-json data/interim/constraints/palette_constraints.json \
    --out-csv data/interim/tmp/industry_colors.csv \
    --palette mocha

# Assign elements to extracted colors
python assign_elements.py data/interim/tmp/industry_colors.csv \
    --constraints-json data/interim/constraints/palette_constraints.json \
    --theme-name industry_theme \
    --out-json data/interim/assign/industry.json

# Fill gaps and generate final Lua theme
python fill_gaps.py \
    --assignments-json data/interim/assign/industry.json \
    --color-pool-csv data/interim/tmp/industry_colors.csv \
    --constraints-json data/interim/constraints/palette_constraints.json \
    --out-lua data/processed/industry_theme.lua \
    --theme-name industry_theme
```

Generated Lua files need formatting with `stylua`.

## Architecture

### Pipeline Steps (Snakemake)

1. **extract_colors.py** - Quantizes colors from input PNG, converts to CIELAB, clusters into semantic roles (background, surface, overlay, text, accent_*)
2. **assign_elements.py** - Maps role clusters to Catppuccin element names (base, mantle, surface0, text, blue, etc.)
3. **fill_gaps.py** - Fills missing elements by interpolating in LCh space, enforces contrast constraints, outputs Lua palette

### Directory Layout

- `src/` - Python scripts and Snakemake files
- `src/vendor/` - Git submodules (catppuccin, savitsky.nvim, codeshot.nvim)
- `data/raw/photos/` - Source images (PNG)
- `data/interim/` - Intermediate outputs (color CSVs, constraint JSON, assignments)
- `data/processed/` - Final `*_theme.lua` files
- `docs/` - GitHub Pages gallery (index.html, themes.json)

### Snakefile Structure

- `Snakefile.py` - Main entry, includes other Snakefiles
- `Snakefile_const.py` - Path constants (RAW, INT, END, SRC, DOCS)
- `Snakefile_theme.py` - Theme generation rules
- `Snakefile_trends.py` - Analysis/visualization rules

### Color Roles → Catppuccin Elements

```
background  → base, mantle, crust
surface     → surface0, surface1, surface2
overlay     → overlay0, overlay1, overlay2
text        → text, subtext0, subtext1
accent_red  → rosewater, flamingo, pink, red, maroon
accent_warm → peach, yellow, green
accent_cool → teal, sky, sapphire, blue, lavender
accent_bridge → mauve
```

### Key Dependencies

- colour-science, scikit-image - Color space conversions
- snakemake - Pipeline orchestration
- click - CLI interfaces
- rich - Terminal output formatting
