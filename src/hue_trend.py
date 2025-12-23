import sys
from pathlib import Path

import numpy as np
import pandas as pd

# ------------------------------------------------------------
# Role mapping (same semantics as before)
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
# LAB → Hue (LCh)
# ------------------------------------------------------------


def lab_to_hue(a: float, b: float) -> float:
    """
    Convert LAB a*, b* to hue angle in degrees [0, 360).
    """
    hue = np.degrees(np.arctan2(b, a))
    return hue % 360.0


# ------------------------------------------------------------
# Main computation
# ------------------------------------------------------------


def compute_hue_by_palette(lab_csv: Path) -> pd.DataFrame:
    """
    Input: catppuccin_lab.csv
    Output columns:
      palette, element, role, hue_deg
    """
    df = pd.read_csv(lab_csv)

    # Map semantic role
    df["role"] = df["element"].map(ROLE_MAP)
    df = df.dropna(subset=["role"])

    # Compute hue
    df["hue_deg"] = lab_to_hue(df["a"].values, df["b"].values)

    return df[["palette", "element", "role", "hue_deg"]]


# ------------------------------------------------------------
# Script entry
# ------------------------------------------------------------

if __name__ == "__main__":
    lab_csv = Path(sys.argv[1])
    out_csv = Path(sys.argv[2])

    df = compute_hue_by_palette(lab_csv)
    df.to_csv(out_csv, index=False)

    print(f"✓ Wrote {out_csv} ({len(df)} rows)")
