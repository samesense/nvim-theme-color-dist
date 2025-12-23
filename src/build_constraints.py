import json
from pathlib import Path

import click
import numpy as np
import pandas as pd

# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------


def hue_entropy(hues, bins=12):
    hist, _ = np.histogram(hues, bins=bins, range=(0, 360), density=True)
    hist = hist[hist > 0]
    return float(-(hist * np.log(hist)).sum())


def circular_mean_deg(deg):
    rad = np.deg2rad(deg)
    return float(
        np.rad2deg(np.arctan2(np.mean(np.sin(rad)), np.mean(np.cos(rad)))) % 360
    )


def circular_width_deg(deg, center, q=90):
    """
    Robust circular width: percentile of angular distance from center.
    """
    dists = np.abs((deg - center + 180) % 360 - 180)
    return float(np.percentile(dists, q) * 2)


# ------------------------------------------------------------
# CLI
# ------------------------------------------------------------


@click.command()
@click.option(
    "--cap-colors-csv",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
    help="Raw Catppuccin colors with Lab values (cap_colors.csv).",
)
@click.option(
    "--deltal-csv",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
)
@click.option(
    "--chroma-csv",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
)
@click.option(
    "--hue-csv",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
)
@click.option(
    "--out",
    type=click.Path(dir_okay=False, path_type=Path),
    default="palette_constraints.json",
    show_default=True,
)
def build_constraints(cap_colors_csv, deltal_csv, chroma_csv, hue_csv, out):
    """
    Build palette profiles + role constraints from Catppuccin analysis outputs.
    """

    # --------------------------------------------------------
    # Load inputs
    # --------------------------------------------------------

    cap = pd.read_csv(cap_colors_csv)
    deltaL = pd.read_csv(deltal_csv)
    chroma = pd.read_csv(chroma_csv)
    hue = pd.read_csv(hue_csv)

    # --------------------------------------------------------
    # 1. Palette PROFILES (absolute identity)
    # --------------------------------------------------------

    profiles = {}

    for palette, sub in cap.groupby("palette"):
        hues = np.degrees(np.arctan2(sub["b"], sub["a"])) % 360
        profiles[palette] = {
            "L_median": float(sub["L"].median()),
            "L_range": float(sub["L"].quantile(0.9) - sub["L"].quantile(0.1)),
            "chroma_median": float(np.sqrt(sub["a"] ** 2 + sub["b"] ** 2).median()),
            "hue_entropy": hue_entropy(hues),
        }

    # --------------------------------------------------------
    # 2. Polarity (derived, palette-scoped)
    # --------------------------------------------------------

    polarity = {}
    for palette, sub in deltaL.groupby("palette"):
        bg_text = sub[sub["pair"] == "background→text"]["delta_L"].median()
        polarity[palette] = "dark" if bg_text > 0 else "light"

    # --------------------------------------------------------
    # 3. ΔL* constraints (palette + role pair)
    # --------------------------------------------------------

    deltaL_constraints = {}
    deltaL["abs_delta_L"] = deltaL["delta_L"].abs()

    for (palette, pair), sub in deltaL.groupby(["palette", "pair"]):
        deltaL_constraints.setdefault(palette, {})[pair] = {
            "q25": float(sub["abs_delta_L"].quantile(0.25)),
            "median": float(sub["abs_delta_L"].median()),
            "q75": float(sub["abs_delta_L"].quantile(0.75)),
        }

    # --------------------------------------------------------
    # 4. Chroma constraints (palette + role)
    # --------------------------------------------------------

    chroma_constraints = {}

    for (palette, role), sub in chroma.groupby(["palette", "role"]):
        chroma_constraints.setdefault(palette, {})[role] = {
            "q25": float(sub["chroma"].quantile(0.25)),
            "median": float(sub["chroma"].median()),
            "q75": float(sub["chroma"].quantile(0.75)),
        }

    # --------------------------------------------------------
    # 5. Hue constraints (palette + role, circular)
    # --------------------------------------------------------

    hue_constraints = {}

    for (palette, role), sub in hue.groupby(["palette", "role"]):
        center = circular_mean_deg(sub["hue_deg"].values)
        width = circular_width_deg(sub["hue_deg"].values, center)

        hue_constraints.setdefault(palette, {})[role] = {
            "center": center,
            "width": width,
        }

    # --------------------------------------------------------
    # Final JSON
    # --------------------------------------------------------

    out_data = {
        "profiles": profiles,
        "polarity": polarity,
        "constraints": {
            "deltaL": deltaL_constraints,
            "chroma": chroma_constraints,
            "hue": hue_constraints,
        },
    }

    out.write_text(json.dumps(out_data, indent=2))
    click.echo(f"✓ Wrote {out}")
    click.echo(f"✓ Palettes: {', '.join(sorted(profiles))}")


if __name__ == "__main__":
    build_constraints()
