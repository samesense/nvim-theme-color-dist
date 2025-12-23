import re
import sys
from pathlib import Path

import colour
import numpy as np
import pandas as pd

HEX_RE = re.compile(r'(\w+)\s*=\s*"(#(?:[0-9a-fA-F]{6}))"')

# ------------------------------------------------------------
# Parsing
# ------------------------------------------------------------


def load_catppuccin_palette(path: str | Path) -> dict[str, str]:
    """
    Load a Catppuccin palette Lua file into a dict:
    { element: "rrggbb" }
    """
    path = Path(path)
    text = path.read_text()

    colors = {}
    for name, hexval in HEX_RE.findall(text):
        colors[name] = hexval.lstrip("#").lower()

    if not colors:
        raise ValueError(f"No colors found in {path}")

    return colors


def hex_to_lab(hex_color: str) -> np.ndarray:
    """
    Convert hex color (rrggbb) to CIELAB (L*, a*, b*)
    """
    rgb = (
        np.array(
            [
                int(hex_color[0:2], 16),
                int(hex_color[2:4], 16),
                int(hex_color[4:6], 16),
            ],
            dtype=float,
        )
        / 255.0
    )

    xyz = colour.sRGB_to_XYZ(rgb)
    lab = colour.XYZ_to_Lab(xyz)
    return lab


def extract_palettes_to_lab(pal_dir: Path) -> pd.DataFrame:
    """
    Walk Catppuccin palette Lua files and return a tidy DataFrame:
    [palette, element, L, a, b]
    """
    rows = []

    for pal_file in sorted(pal_dir.glob("*.lua")):
        if "init" in pal_file.name:
            continue

        palette = pal_file.stem
        colors = load_catppuccin_palette(pal_file)

        for element, hex_color in colors.items():
            L, a, b = hex_to_lab(hex_color)
            rows.append(
                {
                    "palette": palette,
                    "element": element,
                    "L": L,
                    "a": a,
                    "b": b,
                }
            )

    return pd.DataFrame(rows)


if __name__ == "__main__":
    pal_dir = Path("../data/raw/nvim/lua/catppuccin/palettes/")
    out_csv = sys.argv[1]  # pal_dir / "catppuccin_lab.csv"

    df = extract_palettes_to_lab(pal_dir)
    df.to_csv(out_csv, index=False)
