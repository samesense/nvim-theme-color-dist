# nvim-theme-color-dist

A small pipeline for extracting color palettes from images and mapping them into
Catppuccin-style Neovim themes.

The goal is not to design themes by hand, but to **derive coherent, usable editor
themes from visual sources** (paintings, photos, textures) using perceptual color
spaces and structural constraints.

---

## 🌈 Theme Gallery

**View all generated themes here:**

👉 **https://samesense.github.io/nvim-theme-color-dist/**

The gallery shows:
- Core UI colors (background, surface, overlay, text)
- Accent groups (warm / cool / red / bridge)
- Real color swatches rendered with CSS (no Markdown hacks)

This is the canonical visual reference for the project.

---

## 🖼️ Source material

Many of the themes in this repository are derived from **photographs of paintings**
from the **Savitsky Museum of Art (Nukus, Uzbekistan)** — formally known as the
State Museum of Arts of the Republic of Karakalpakstan.

The Savitsky Museum houses one of the world’s most significant collections of
20th-century Soviet avant-garde and Central Asian art.

Reference:
https://visitworldheritage.com/en/eu/nukus-museum-of-art/61754607-39ca-49bf-88c1-80076d837d33

These paintings provide rich, non-digital color compositions that translate
surprisingly well into editor UI palettes.

---

## 🧠 How it works (high level)

1. **Color extraction**
   - Sample and quantize colors from an input image
   - Convert to CIELAB for perceptual distance calculations

2. **Role clustering**
   - Cluster extracted colors into semantic roles
   - Compare role distances against Catppuccin palette geometry

3. **Structural assignment**
   - Enforce contrast and ordering constraints
   - Select background / surface / overlay / text candidates
   - Place accents relative to text and UI layers

4. **Theme generation**
   - Emit Neovim-compatible Lua theme files
   - Export a structured JSON representation for visualization

---

## 📁 Repository layout

```text
├─ src/                 # Python scripts
│  ├─ role_clusters.py
│  ├─ assign_roles.py
│  ├─ assign_elements.py
│  └─ export_themes_json.py
├─ data/
│  ├─ raw/              # Input images, Catppuccin palettes
│  ├─ interim/
│  └─ processed/        # Generated *_theme.lua files
├─ docs/                # GitHub Pages
│  ├─ index.html
│  └─ themes.json
└─ README.md

## Todo
### not yet modeling:
* contrast ratios (WCAG)
* spatial adjacency (UI context)
* perceptual salience interactions (future)
