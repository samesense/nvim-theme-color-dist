from pathlib import Path

import click
import pandas as pd

# ------------------------------------------------------------
# Role ordering (lower → higher)
# ------------------------------------------------------------

ROLE_ORDER = [
    "background",
    "surface",
    "overlay",
    "text",
]

ROLE_MAP = {
    "crust": "background",
    "mantle": "background",
    "base": "background",
    "surface0": "surface",
    "surface1": "surface",
    "surface2": "surface",
    "overlay0": "overlay",
    "overlay1": "overlay",
    "overlay2": "overlay",
    "text": "text",
    "subtext0": "text",
    "subtext1": "text",
}

# Structurally meaningful margins only
ROLE_PAIRS = [
    ("background", "surface"),
    ("surface", "overlay"),
    ("overlay", "text"),
    ("background", "text"),
]


@click.command()
@click.option(
    "--colors-csv",
    "catppuccin_colors_csv",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
    help="Input CSV with columns: palette, element, L",
)
@click.option(
    "--out",
    type=click.Path(dir_okay=False, path_type=Path),
    default="deltaL_margins_by_palette.csv",
    show_default=True,
    help="Output CSV of ΔL* margins by palette",
)
def compute_deltaL(catppuccin_colors_csv: Path, out: Path):
    """
    Compute ΔL* margins between semantic role pairs,
    split by Catppuccin palette.
    """
    df = pd.read_csv(catppuccin_colors_csv)

    required = {"palette", "element", "L"}
    if not required.issubset(df.columns):
        missing = ", ".join(sorted(required - set(df.columns)))
        raise click.ClickException(f"Missing required columns: {missing}")

    # Map elements → roles
    df["role"] = df["element"].map(ROLE_MAP)
    df = df.dropna(subset=["role"])

    rows = []

    for palette, sub in df.groupby("palette", sort=True):
        # Mean L* per role (palette-local)
        role_means = sub.groupby("role")["L"].mean().reindex(ROLE_ORDER)

        for low, high in ROLE_PAIRS:
            if pd.isna(role_means[low]) or pd.isna(role_means[high]):
                continue  # skip incomplete palettes safely

            rows.append(
                {
                    "palette": palette,
                    "low_role": low,
                    "high_role": high,
                    "pair": f"{low}→{high}",
                    "delta_L": role_means[high] - role_means[low],
                }
            )

    out_df = pd.DataFrame(rows).sort_values(["palette", "pair"])
    out_df.to_csv(out, index=False)

    click.echo(f"✓ Wrote {out} ({len(out_df)} rows)")


if __name__ == "__main__":
    compute_deltaL()
