import json
import math
from pathlib import Path

import click
import numpy as np
import pandas as pd
from PIL import Image
from rich.console import Console
from rich.style import Style
from rich.table import Table
from rich.text import Text
from skimage.color import rgb2lab

# ------------------------------------------------------------
# Role ordering & display order
# ------------------------------------------------------------

ROLE_ORDER = [
    "background",
    "surface",
    "overlay",
    "text",
    "accent_red",
    "accent_warm",
    "accent_cool",
    "accent_bridge",
]


def add_ranks(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["L_rank"] = df.groupby("role")["L"].rank(pct=True, method="average")
    df["chroma_rank"] = df.groupby("role")["chroma"].rank(pct=True, method="average")

    # New: ranks for foreground usability vs background anchor
    # (higher = more separated, typically more readable as fg)
    if "deltaE_bg" in df.columns:
        df["deltaE_bg_rank"] = df.groupby("role")["deltaE_bg"].rank(
            pct=True, method="average"
        )
    else:
        df["deltaE_bg_rank"] = np.nan

    if "abs_deltaL_bg" in df.columns:
        df["abs_deltaL_bg_rank"] = df.groupby("role")["abs_deltaL_bg"].rank(
            pct=True, method="average"
        )
    else:
        df["abs_deltaL_bg_rank"] = np.nan

    return df


# ------------------------------------------------------------
# Color helpers
# ------------------------------------------------------------


def rgb_to_hex(rgb):
    r, g, b = map(int, rgb)
    return f"#{r:02x}{g:02x}{b:02x}"


def lab_to_chroma(a, b):
    return math.sqrt(a * a + b * b)


def lab_to_hue(a, b):
    return math.degrees(math.atan2(b, a)) % 360.0


def circular_distance(a, b):
    d = abs(a - b) % 360
    return min(d, 360 - d)


def deltaE76(lab1: np.ndarray, lab2: np.ndarray) -> float:
    d = lab1 - lab2
    return float(np.sqrt(np.dot(d, d)))


# ------------------------------------------------------------
# Image sampling
# ------------------------------------------------------------


def load_image_colors(path: Path, max_pixels: int | None):
    img = Image.open(path).convert("RGB")
    rgb = np.asarray(img).reshape(-1, 3)

    if max_pixels and len(rgb) > max_pixels:
        idx = np.random.choice(len(rgb), max_pixels, replace=False)
        rgb = rgb[idx]

    return rgb


# ------------------------------------------------------------
# Palette inference
# ------------------------------------------------------------


def infer_palette(photo_stats, palette_profiles):
    # Hard polarity gate
    if photo_stats["L_median"] > 50:
        candidates = ["latte"]
    else:
        candidates = [p for p in palette_profiles if p != "latte"]

    best = None
    best_score = float("inf")

    for palette in candidates:
        prof = palette_profiles[palette]

        score = (
            abs(photo_stats["L_median"] - prof["L_median"])
            + 0.5 * abs(photo_stats["L_range"] - prof["L_range"])
            + 0.5 * abs(photo_stats["chroma_median"] - prof["chroma_median"])
            + 0.2 * abs(photo_stats["hue_entropy"] - prof["hue_entropy"])
        )

        if score < best_score:
            best_score = score
            best = palette

    return best


# ------------------------------------------------------------
# Role eligibility + scoring
# ------------------------------------------------------------


def eligible_roles(row, constraints):
    roles = []

    chroma = row.chroma
    hue = row.hue

    # Core UI roles (lightness-driven via chroma constraints only)
    for role in ["background", "surface", "overlay", "text"]:
        if role not in constraints["chroma"]:
            continue
        c = constraints["chroma"][role]
        if c["q25"] <= chroma <= c["q75"]:
            roles.append(role)

    # Accent roles (chroma + hue)
    for role in ["accent_red", "accent_warm", "accent_cool", "accent_bridge"]:
        if role not in constraints["hue"]:
            continue

        c = constraints["chroma"][role]
        h = constraints["hue"][role]

        if chroma < c["q25"]:
            continue

        if circular_distance(hue, h["center"]) <= h["width"] / 2:
            roles.append(role)

    return roles


def score_color(row, role, constraints):
    score = row.frequency * 5.0

    if role in constraints["chroma"]:
        c = constraints["chroma"][role]
        score -= abs(row.chroma - ((c["q25"] + c["q75"]) / 2))

    if role in constraints["hue"]:
        h = constraints["hue"][role]
        score -= circular_distance(row.hue, h["center"]) * 0.1

    return score


def pick_anchor(pool: pd.DataFrame, role: str) -> pd.Series | None:
    sub = pool[pool.role == role].sort_values("score", ascending=False)
    if sub.empty:
        return None
    return sub.iloc[0]


# ------------------------------------------------------------
# Rich display
# ------------------------------------------------------------


def render_role_pool(df):
    console = Console()
    table = Table(show_header=True, header_style="bold")

    table.add_column("Role", style="cyan", no_wrap=True)
    table.add_column("Colors")

    for role in ROLE_ORDER:
        sub = df[df.role == role].sort_values("score", ascending=False)
        if sub.empty:
            continue

        strip = Text()
        for _, r in sub.iterrows():
            w = min(30, max(1, int(r.frequency * 300)))
            strip.append(" " * w, style=Style(bgcolor=rgb_to_hex((r.R, r.G, r.B))))

        table.add_row(f"{role} ({len(sub)})", strip)

    console.print(table)


# ------------------------------------------------------------
# CLI
# ------------------------------------------------------------


@click.command()
@click.argument("image_path", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--constraints-json",
    type=click.Path(exists=True, path_type=Path),
    required=True,
)
@click.option(
    "--palette",
    type=click.Choice(
        ["auto", "latte", "frappe", "macchiato", "mocha"], case_sensitive=False
    ),
    default="auto",
    show_default=True,
)
@click.option("--max-pixels", default=100_000, show_default=True)
@click.option("--quant", default=8, show_default=True)
@click.option(
    "--out-csv",
    default="color_pool.csv",
    show_default=True,
    type=click.Path(path_type=Path),
)
@click.option(
    "--cool-min-deltae",
    default=25.0,
    show_default=True,
    type=float,
    help="Minimum Lab deltaE from background for accent_cool (foreground safety).",
)
@click.option(
    "--cool-min-abs-deltal",
    default=12.0,
    show_default=True,
    type=float,
    help="Minimum absolute deltaL from background for accent_cool (foreground safety).",
)
@click.option(
    "--cool-soft-min-deltal",
    default=18.0,
    show_default=True,
    type=float,
    help="Soft penalty threshold: accent_cool below bg_L + this gets penalized.",
)
def extract_color_pool(
    image_path,
    constraints_json,
    palette,
    max_pixels,
    quant,
    out_csv,
    cool_min_deltae,
    cool_min_abs_deltal,
    cool_soft_min_deltal,
):
    """
    Build a role-aware color pool from a photo using learned palette constraints.
    """

    constraints_all = json.loads(constraints_json.read_text())
    palette_profiles = constraints_all["profiles"]

    # --------------------------------------------------------
    # Sample image
    # --------------------------------------------------------

    rgb = load_image_colors(image_path, max_pixels)
    rgb = (rgb // quant) * quant
    rgb = rgb.astype(np.uint8)

    uniq, counts = np.unique(rgb, axis=0, return_counts=True)
    freq = counts / counts.sum()

    lab = rgb2lab(uniq[np.newaxis, :, :] / 255.0)[0]

    df = pd.DataFrame(
        {
            "R": uniq[:, 0],
            "G": uniq[:, 1],
            "B": uniq[:, 2],
            "L": lab[:, 0],
            "a": lab[:, 1],
            "b": lab[:, 2],
            "frequency": freq,
        }
    )

    df["chroma"] = np.sqrt(df.a**2 + df.b**2)
    df["hue"] = np.degrees(np.arctan2(df.b, df.a)) % 360.0

    # --------------------------------------------------------
    # Photo stats → palette choice
    # --------------------------------------------------------

    photo_stats = {
        "L_median": df.L.median(),
        "L_range": df.L.quantile(0.9) - df.L.quantile(0.1),
        "chroma_median": df.chroma.median(),
        "hue_entropy": np.histogram(df.hue, bins=12, density=True)[0].var(),
    }

    if palette == "auto":
        palette = infer_palette(photo_stats, palette_profiles)

    console = Console()
    console.print(f"\n🎨 Selected palette constraints: [bold]{palette}[/bold]\n")

    constraints = {
        "chroma": constraints_all["constraints"]["chroma"][palette],
        "hue": constraints_all["constraints"]["hue"][palette],
        "deltaL": constraints_all["constraints"]["deltaL"][palette],
    }

    # --------------------------------------------------------
    # Initial role eligibility + scoring
    # --------------------------------------------------------

    rows = []
    for _, r in df.iterrows():
        roles = eligible_roles(r, constraints)
        for role in roles:
            rows.append(
                {
                    **r.to_dict(),
                    "role": role,
                    "score": score_color(r, role, constraints),
                }
            )

    pool = pd.DataFrame(rows)
    if pool.empty:
        raise click.ClickException("No colors matched constraints")

    # --------------------------------------------------------
    # Background anchor + fg-safety metrics
    # --------------------------------------------------------

    bg = pick_anchor(pool, "background")
    if bg is None:
        raise click.ClickException("No background matched constraints")

    bg_lab = np.array([bg.L, bg.a, bg.b], dtype=float)
    bg_L = float(bg.L)

    # Compute separation from background for all rows
    pool["deltaE_bg"] = pool.apply(
        lambda r: deltaE76(np.array([r.L, r.a, r.b], dtype=float), bg_lab),
        axis=1,
    )
    pool["deltaL_bg"] = pool["L"] - bg_L
    pool["abs_deltaL_bg"] = pool["deltaL_bg"].abs()

    # --------------------------------------------------------
    # Improve accent_cool pool for later syntax usage
    #   - hard gate: deltaE + abs(deltaL)
    #   - rescore: reward separation, penalize too-dark cools
    # --------------------------------------------------------

    cool_mask = pool["role"] == "accent_cool"
    if cool_mask.any():
        cool = pool[cool_mask].copy()

        # Hard gates (foreground safety)
        cool = cool[
            (cool["deltaE_bg"] >= cool_min_deltae)
            & (cool["abs_deltaL_bg"] >= cool_min_abs_deltal)
        ]

        if not cool.empty:
            # Rescore: boost separation; keep it bounded
            # (Additive to original score so we still prefer frequent + on-hue candidates.)
            cool["score"] = (
                cool["score"]
                + np.minimum(cool["deltaE_bg"], 60.0) * 0.5
                + np.minimum(cool["abs_deltaL_bg"], 40.0) * 0.6
            )

            # Soft penalty: discourage cool accents that are too close to bg in lightness on the dark side
            # This specifically prevents "almost-base teal" foregrounds.
            too_dark = cool["L"] < (bg_L + cool_soft_min_deltal)
            cool.loc[too_dark, "score"] -= (
                bg_L + cool_soft_min_deltal - cool.loc[too_dark, "L"]
            ) * 2.0

            # Replace old accent_cool rows with improved set
            pool = pd.concat([pool[~cool_mask], cool], ignore_index=True)
        else:
            # If we eliminated all cool accents, drop them (caller can tune thresholds)
            pool = pool[~cool_mask].copy()

    # --------------------------------------------------------
    # Display
    # --------------------------------------------------------

    render_role_pool(pool)

    # --------------------------------------------------------
    # Add metadata + ranks
    # --------------------------------------------------------

    pool = pool.reset_index(drop=True)
    pool["color_id"] = pool.index
    pool["hex"] = pool.apply(lambda r: rgb_to_hex((r.R, r.G, r.B)), axis=1)
    pool["palette"] = palette

    pool = add_ranks(pool)

    # Column order (authoritative)
    cols = [
        "color_id",
        "palette",
        "role",
        "hex",
        "R",
        "G",
        "B",
        "L",
        "a",
        "b",
        "chroma",
        "hue",
        "frequency",
        "score",
        "L_rank",
        "chroma_rank",
        "deltaE_bg",
        "deltaL_bg",
        "abs_deltaL_bg",
        "deltaE_bg_rank",
        "abs_deltaL_bg_rank",
    ]

    pool[cols].to_csv(out_csv, index=False)


if __name__ == "__main__":
    extract_color_pool()
