import json
from pathlib import Path

import click
import numpy as np
import pandas as pd


@click.command()
@click.option(
    "--deltal-csv", type=click.Path(exists=True, path_type=Path), required=True
)
@click.option(
    "--chroma-csv", type=click.Path(exists=True, path_type=Path), required=True
)
@click.option("--hue-csv", type=click.Path(exists=True, path_type=Path), required=True)
@click.option(
    "--out", type=click.Path(path_type=Path), default="palette_constraints.json"
)
def build_constraints(deltal_csv, chroma_csv, hue_csv, out):
    """
    Build palette constraints from Catppuccin analysis outputs.
    """

    deltaL = pd.read_csv(deltal_csv)
    chroma = pd.read_csv(chroma_csv)
    hue = pd.read_csv(hue_csv)

    constraints = {}

    # ------------------------------------------------------------
    # Polarity (per palette)
    # ------------------------------------------------------------
    polarity = {}
    for palette, sub in deltaL.groupby("palette"):
        bg_text = sub[sub.pair == "background→text"]["delta_L"].median()
        polarity[palette] = "dark" if bg_text > 0 else "light"

    constraints["polarity"] = polarity

    # ------------------------------------------------------------
    # Lightness spacing (absolute ΔL*)
    # ------------------------------------------------------------
    lightness = {}
    deltaL["abs_delta_L"] = deltaL["delta_L"].abs()

    for pair, sub in deltaL.groupby("pair"):
        lightness[pair] = {
            "min": float(sub.abs_delta_L.quantile(0.05)),
            "median": float(sub.abs_delta_L.median()),
            "max": float(sub.abs_delta_L.quantile(0.95)),
        }

    constraints["lightness"] = lightness

    # ------------------------------------------------------------
    # Chroma constraints
    # ------------------------------------------------------------
    chroma_constraints = {}
    for role, sub in chroma.groupby("role"):
        chroma_constraints[role] = {
            "q25": float(sub.chroma.quantile(0.25)),
            "q75": float(sub.chroma.quantile(0.75)),
        }

    constraints["chroma"] = chroma_constraints

    # ------------------------------------------------------------
    # Hue windows (circular mean + spread)
    # ------------------------------------------------------------
    hue_constraints = {}
    for role, sub in hue.groupby("role"):
        angles = np.deg2rad(sub.hue_deg.values)
        mean_angle = np.arctan2(np.mean(np.sin(angles)), np.mean(np.cos(angles)))
        mean_deg = np.degrees(mean_angle) % 360

        # circular spread (simple, robust)
        spread = np.percentile(sub.hue_deg, 90) - np.percentile(sub.hue_deg, 10)

        hue_constraints[role] = {
            "center": float(mean_deg),
            "width": float(spread),
        }

    constraints["hue"] = hue_constraints

    out.write_text(json.dumps(constraints, indent=2))


if __name__ == "__main__":
    build_constraints()
