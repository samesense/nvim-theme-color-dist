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
# Role mapping (Catppuccin semantics)
# ------------------------------------------------------------


ROLE_MAP = {
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
    "--text-contrast-csv",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="Base-to-text/subtext contrast bands.",
)
@click.option(
    "--accent-text-sep-csv",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="Accent-to-text separation (L* and dE).",
)
@click.option(
    "--ui-hue-coherence-csv",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="UI hue coherence (background/surface/overlay/text).",
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
    text_contrast_csv,
    accent_text_sep_csv,
    ui_hue_coherence_csv,
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
    # 4. Lightness constraints (palette + role)
    # --------------------------------------------------------

    cap_role = cap.copy()
    cap_role["role"] = cap_role["element"].map(ROLE_MAP)
    cap_role = cap_role.dropna(subset=["role"])

    lightness_constraints = {}
    for (palette, role), sub in cap_role.groupby(["palette", "role"]):
        q10 = float(sub["L"].quantile(0.10))
        q25 = float(sub["L"].quantile(0.25))
        q75 = float(sub["L"].quantile(0.75))
        q90 = float(sub["L"].quantile(0.90))
        relax_delta = (q90 - q10) / 2

        lightness_constraints.setdefault(palette, {})[role] = {
            "q10": q10,
            "q25": q25,
            "median": float(sub["L"].median()),
            "q75": q75,
            "q90": q90,
            "relax_delta": relax_delta,
        }

    # --------------------------------------------------------
    # 5. Background hue spread (palette scoped)
    # --------------------------------------------------------

    background_hue = {}
    bg_roles = cap_role[cap_role["role"] == "background"].copy()
    for palette, sub in bg_roles.groupby("palette"):
        hues = np.degrees(np.arctan2(sub["b"], sub["a"])) % 360
        center = circular_mean_deg(hues)
        width = circular_width_deg(hues, center)
        background_hue[palette] = {
            "center": float(center),
            "width": float(width),
        }

    # --------------------------------------------------------
    # 6. Chroma constraints (palette + role)
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
    # 7. Hue constraints (palette + role, circular)
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
    # 8. Element offsets (palette + role + offset_name)
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
    # 9. Accent separation (polarity + role)
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
    # 10. Text contrast bands (palette + element)
    # --------------------------------------------------------

    text_contrast_constraints = {}
    if text_contrast_csv is not None:
        tc_df = pd.read_csv(text_contrast_csv)
        for (palette, element), sub in tc_df.groupby(["palette", "element"]):
            text_contrast_constraints.setdefault(palette, {})[element] = {
                "q25": float(sub["abs_delta_L"].quantile(0.25)),
                "median": float(sub["abs_delta_L"].median()),
                "q75": float(sub["abs_delta_L"].quantile(0.75)),
            }

    # --------------------------------------------------------
    # 11. Accent-text separation (palette + role)
    # --------------------------------------------------------

    accent_text_constraints = {}
    if accent_text_sep_csv is not None:
        at_df = pd.read_csv(accent_text_sep_csv)
        for (palette, role), sub in at_df.groupby(["palette", "role"]):
            accent_text_constraints.setdefault(palette, {})[role] = {
                "deltaE_q10": float(sub["delta_E"].quantile(0.10)),
                "deltaE_q25": float(sub["delta_E"].quantile(0.25)),
                "deltaL_q10": float(sub["abs_delta_L"].quantile(0.10)),
                "deltaL_q25": float(sub["abs_delta_L"].quantile(0.25)),
            }

    # --------------------------------------------------------
    # 12. UI hue coherence (palette)
    # --------------------------------------------------------

    ui_hue_constraints = {}
    if ui_hue_coherence_csv is not None:
        uh_df = pd.read_csv(ui_hue_coherence_csv)
        for _, row in uh_df.iterrows():
            ui_hue_constraints[str(row["palette"])] = {
                "max_dist": float(row["max_dist"]),
                "mean_dist": float(row["mean_dist"]),
            }

    # --------------------------------------------------------
    # Final JSON
    # --------------------------------------------------------

    out_data = {
        "profiles": profiles,
        "polarity": polarity,
        "constraints": {
            "deltaL": deltaL_constraints,
            "lightness": lightness_constraints,
            "background_hue": background_hue,
            "chroma": chroma_constraints,
            "hue": hue_constraints,
            "element_offsets": element_offset_constraints,
            "accent_separation": accent_sep_constraints,
            "text_contrast": text_contrast_constraints,
            "accent_text_separation": accent_text_constraints,
            "ui_hue_coherence": ui_hue_constraints,
        },
    }

    out.write_text(json.dumps(out_data, indent=2))
    click.echo(f"✓ Wrote {out}")
    click.echo(f"✓ Palettes: {', '.join(sorted(profiles))}")


if __name__ == "__main__":
    build_constraints()
