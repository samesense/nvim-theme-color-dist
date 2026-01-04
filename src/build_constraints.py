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


def compute_hue_relax_mult(deg, center, q_strict=90, q_relaxed=99):
    """
    Compute hue relaxation multiplier from width ratio.

    Returns width_q_relaxed / width_q_strict, clamped to reasonable bounds.
    This replaces hardcoded 1.3 multiplier.
    """
    dists = np.abs((deg - center + 180) % 360 - 180)
    w_strict = np.percentile(dists, q_strict) * 2
    w_relaxed = np.percentile(dists, q_relaxed) * 2

    if w_strict < 1e-6:  # avoid division by zero for single-element roles
        return 1.0

    mult = w_relaxed / w_strict
    # Clamp to reasonable bounds (1.0 to 2.0)
    return float(max(1.0, min(2.0, mult)))


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
    "--element-offsets-csv",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="Element L* offsets within roles (compute_element_offsets.py output).",
)
@click.option(
    "--accent-separation-csv",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="Accent-to-background separation (compute_accent_separation.py output).",
)
@click.option(
    "--out",
    type=click.Path(dir_okay=False, path_type=Path),
    default="palette_constraints.json",
    show_default=True,
)
def build_constraints(
    cap_colors_csv,
    deltal_csv,
    chroma_csv,
    hue_csv,
    element_offsets_csv,
    accent_separation_csv,
    out,
):
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
        q10 = float(sub["chroma"].quantile(0.10))
        q25 = float(sub["chroma"].quantile(0.25))
        q75 = float(sub["chroma"].quantile(0.75))
        q90 = float(sub["chroma"].quantile(0.90))
        # Relaxation delta: half of the q10-q90 spread
        relax_delta = (q90 - q10) / 2

        chroma_constraints.setdefault(palette, {})[role] = {
            "q10": q10,
            "q25": q25,
            "median": float(sub["chroma"].median()),
            "q75": q75,
            "q90": q90,
            "relax_delta": relax_delta,
        }

    # --------------------------------------------------------
    # 5. Hue constraints (palette + role, circular)
    # --------------------------------------------------------

    hue_constraints = {}

    for (palette, role), sub in hue.groupby(["palette", "role"]):
        center = circular_mean_deg(sub["hue_deg"].values)
        width = circular_width_deg(sub["hue_deg"].values, center)
        relax_mult = compute_hue_relax_mult(sub["hue_deg"].values, center)

        hue_constraints.setdefault(palette, {})[role] = {
            "center": center,
            "width": width,
            "relax_mult": relax_mult,
        }

    # --------------------------------------------------------
    # 6. Element offsets (palette + role + offset_name)
    # --------------------------------------------------------

    element_offset_constraints = {}

    if element_offsets_csv is not None:
        offsets_df = pd.read_csv(element_offsets_csv)

        for (palette, offset_name), sub in offsets_df.groupby(
            ["palette", "offset_name"]
        ):
            element_offset_constraints.setdefault(palette, {})[offset_name] = {
                "value": float(sub["delta_L"].iloc[0]),
            }

    # --------------------------------------------------------
    # 7. Accent separation (polarity + role)
    # --------------------------------------------------------

    accent_sep_constraints = {}

    if accent_separation_csv is not None:
        sep_df = pd.read_csv(accent_separation_csv)

        # Group by polarity and role to get min threshold
        for (polarity_val, role), sub in sep_df.groupby(["polarity", "role"]):
            accent_sep_constraints.setdefault(polarity_val, {})[role] = {
                "min": float(sub["delta_L"].min()),
                "q10": float(sub["delta_L"].quantile(0.10)),
                "q25": float(sub["delta_L"].quantile(0.25)),
                "median": float(sub["delta_L"].median()),
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
            "element_offsets": element_offset_constraints,
            "accent_separation": accent_sep_constraints,
        },
    }

    out.write_text(json.dumps(out_data, indent=2))
    click.echo(f"✓ Wrote {out}")
    click.echo(f"✓ Palettes: {', '.join(sorted(profiles))}")


if __name__ == "__main__":
    build_constraints()
