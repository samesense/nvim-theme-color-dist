import sys
from pathlib import Path

import numpy as np
import pandas as pd

# ------------------------------------------------------------
# Role mapping (Catppuccin semantics)
# ------------------------------------------------------------

ROLE_MAP = {
    # Core UI
    "base": "background",
    "mantle": "background",
    "crust": "background",
    "surface0": "surface",
    "surface1": "surface",
    "surface2": "surface",
    "overlay0": "overlay",
    "overlay1": "overlay",
    "overlay2": "overlay",
    "text": "text",
    "subtext0": "text",
    "subtext1": "text",
    # Accents
    "rosewater": "accent_red",
    "flamingo": "accent_red",
    "pink": "accent_red",
    "red": "accent_red",
    "maroon": "accent_red",
    "peach": "accent_warm",
    "yellow": "accent_warm",
    "green": "accent_warm",
    "teal": "accent_cool",
    "sky": "accent_cool",
    "sapphire": "accent_cool",
    "blue": "accent_cool",
    "lavender": "accent_cool",
    "mauve": "accent_bridge",
}

# ------------------------------------------------------------
# Main computation
# ------------------------------------------------------------


def compute_chroma_by_role(lab_csv: Path) -> pd.DataFrame:
    """
    Input: catppuccin_lab.csv
    Output columns:
      palette, element, role, chroma
    """
    df = pd.read_csv(lab_csv)

    # Map semantic role
    df["role"] = df["element"].map(ROLE_MAP)
    df = df.dropna(subset=["role"])

    # Compute chroma C* = sqrt(a^2 + b^2)
    df["chroma"] = np.sqrt(df["a"] ** 2 + df["b"] ** 2)

    return df[["palette", "element", "role", "chroma"]]


if __name__ == "__main__":
    lab_csv = sys.argv[1]
    out_csv = sys.argv[2]

    df = compute_chroma_by_role(lab_csv)
    df.to_csv(out_csv, index=False)
