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


def add_ranks(df):
    df = df.copy()
    df["L_rank"] = df.groupby("role")["L"].rank(pct=True, method="average")
    df["chroma_rank"] = df.groupby("role")["chroma"].rank(pct=True, method="average")
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

    L = row.L
    chroma = row.chroma
    hue = row.hue

    # Core UI roles (lightness-driven)
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
def extract_color_pool(
    image_path, constraints_json, palette, max_pixels, quant, out_csv
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

    constraints = constraints_all["constraints"]
    polarity = constraints_all["polarity"][palette]

    # --------------------------------------------------------
    # Role eligibility + scoring
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

    render_role_pool(pool)

    if pool.empty:
        raise click.ClickException("No colors matched constraints")

    # Add metadata
    pool = pool.reset_index(drop=True)
    pool["color_id"] = pool.index
    pool["hex"] = pool.apply(lambda r: rgb_to_hex((r.R, r.G, r.B)), axis=1)
    pool["palette"] = palette

    # Add ranks for selector
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
    ]

    pool[cols].to_csv(out_csv, index=False)


if __name__ == "__main__":
    extract_color_pool()
