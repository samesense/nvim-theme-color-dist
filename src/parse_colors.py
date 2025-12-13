import re
from pathlib import Path

import colour
import numpy as np
import pandas as pd

HEX_RE = re.compile(r'(\w+)\s*=\s*"(#(?:[0-9a-fA-F]{6}))"')


def load_catppuccin_palette(path: str | Path) -> dict[str, str]:
    """
    Load a Catppuccin palette Lua file into a dict:
    { color_name: "#rrggbb" }
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
    Convert hex color to CIELAB
    """
    rgb = (
        np.array(
            [
                int(hex_color[0:2], 16),
                int(hex_color[2:4], 16),
                int(hex_color[4:6], 16),
            ]
        )
        / 255.0
    )

    xyz = colour.sRGB_to_XYZ(rgb)
    lab = colour.XYZ_to_Lab(xyz)
    return lab


def compute_palette_distances(colors: dict[str, str]) -> pd.DataFrame:
    """
    Compute pairwise CIELAB distances between all colors
    Returns tidy DataFrame with columns:
    [element1, element2, distance]
    """
    labs = {k: hex_to_lab(v) for k, v in colors.items()}

    rows = []
    names = list(labs.keys())

    for i, a in enumerate(names):
        for j, b in enumerate(names):
            if j <= i:
                continue  # skip self + duplicate pairs

            dist = np.linalg.norm(labs[a] - labs[b])
            rows.append(
                {
                    "element1": a,
                    "element2": b,
                    "distance": dist,
                }
            )

    return pd.DataFrame(rows)


pal_dir = Path("../data/raw/nvim/lua/catppuccin/palettes/")
for pal_file in pal_dir.glob("*.lua"):
    if not "init" in pal_file.name:
        colors = load_catppuccin_palette(pal_file)
        distances = compute_palette_distances(colors)
        distances["palette"] = pal_file.stem
        out_file = pal_file.with_suffix(".csv")
        distances.to_csv(out_file, index=False)
