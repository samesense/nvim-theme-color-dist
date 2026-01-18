"""
Compute accent-to-background L* separation for Catppuccin palettes.

Learns the typical lightness separation between accent colors and the background,
grouped by accent role and palette polarity (dark vs light).

These thresholds replace hardcoded magic numbers like cool_min_deltal=24.0
and accent_min_deltal=18.0.
"""

from pathlib import Path

import click
import numpy as np
import pandas as pd

# ------------------------------------------------------------
# Role mapping
# ------------------------------------------------------------

ROLE_MAP = {
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

ACCENT_ROLES = ["accent_red", "accent_warm", "accent_cool", "accent_bridge"]

# Palette polarity
POLARITY = {
    "frappe": "dark",
    "latte": "light",
    "macchiato": "dark",
    "mocha": "dark",
}


def compute_accent_separation(lab_csv: Path) -> pd.DataFrame:
    """
    Compute L* separation between each accent color and the background (base).

    Returns DataFrame with columns:
        palette, polarity, element, role, accent_L, base_L, delta_L, abs_delta_L
    """
    df = pd.read_csv(lab_csv)

    if not {"palette", "element", "L"}.issubset(df.columns):
        raise ValueError("CSV must contain palette, element, L columns")

    rows = []

    for palette, sub in df.groupby("palette"):
        # Get base L
        base_row = sub[sub["element"] == "base"]
        if base_row.empty:
            continue
        base_L = float(base_row["L"].iloc[0])

        polarity = POLARITY.get(palette, "dark")

        # Process each accent element
        for _, row in sub.iterrows():
            elem = row["element"]
            if elem not in ROLE_MAP:
                continue

            role = ROLE_MAP[elem]
            accent_L = float(row["L"])

            # For dark themes: accent should be lighter than base (positive delta)
            # For light themes: accent should be darker than base (negative delta)
            delta_L = accent_L - base_L

            rows.append(
                {
                    "palette": palette,
                    "polarity": polarity,
                    "element": elem,
                    "role": role,
                    "accent_L": accent_L,
                    "base_L": base_L,
                    "delta_L": delta_L,
                    "abs_delta_L": abs(delta_L),
                }
            )

    return pd.DataFrame(rows)


def summarize_by_role_polarity(df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate separation statistics by (role, polarity).

    Groups by (polarity, role) and computes min, q10, q25, median, q75, q90, max.

    For minimum thresholds, use 'min' or 'q10' (most permissive).
    For strict thresholds, use 'q25'.
    """
    return (
        df.groupby(["polarity", "role"])
        .agg(
            n=("delta_L", "size"),
            delta_L_min=("delta_L", "min"),
            delta_L_q10=("delta_L", lambda x: np.percentile(x, 10)),
            delta_L_q25=("delta_L", lambda x: np.percentile(x, 25)),
            delta_L_median=("delta_L", "median"),
            delta_L_q75=("delta_L", lambda x: np.percentile(x, 75)),
            delta_L_q90=("delta_L", lambda x: np.percentile(x, 90)),
            delta_L_max=("delta_L", "max"),
            abs_delta_L_min=("abs_delta_L", "min"),
            abs_delta_L_q10=("abs_delta_L", lambda x: np.percentile(x, 10)),
            abs_delta_L_q25=("abs_delta_L", lambda x: np.percentile(x, 25)),
            abs_delta_L_median=("abs_delta_L", "median"),
        )
        .reset_index()
    )


def summarize_by_palette_role(df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate separation statistics by (palette, role).

    This is useful for palette-specific constraints.
    """
    return (
        df.groupby(["palette", "role"])
        .agg(
            n=("delta_L", "size"),
            delta_L_q10=("delta_L", lambda x: np.percentile(x, 10)),
            delta_L_q25=("delta_L", lambda x: np.percentile(x, 25)),
            delta_L_median=("delta_L", "median"),
            delta_L_q75=("delta_L", lambda x: np.percentile(x, 75)),
            delta_L_q90=("delta_L", lambda x: np.percentile(x, 90)),
        )
        .reset_index()
    )


@click.command()
@click.option(
    "--lab-csv",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
    help="Input CSV with Lab values (cap_colors.csv).",
)
@click.option(
    "--out-csv",
    type=click.Path(dir_okay=False, path_type=Path),
    required=True,
    help="Output CSV for per-element separation data.",
)
@click.option(
    "--summary-polarity-csv",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Optional output CSV for summary by (polarity, role).",
)
@click.option(
    "--summary-palette-csv",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Optional output CSV for summary by (palette, role).",
)
def main(
    lab_csv: Path,
    out_csv: Path,
    summary_polarity_csv: Path | None,
    summary_palette_csv: Path | None,
):
    """
    Compute L* separation between accent colors and background.
    """
    df = compute_accent_separation(lab_csv)
    df.to_csv(out_csv, index=False)
    click.echo(f"Wrote {len(df)} rows to {out_csv}")

    if summary_polarity_csv is not None:
        summary = summarize_by_role_polarity(df)
        summary.to_csv(summary_polarity_csv, index=False)
        click.echo(f"Wrote polarity summary to {summary_polarity_csv}")

    if summary_palette_csv is not None:
        summary = summarize_by_palette_role(df)
        summary.to_csv(summary_palette_csv, index=False)
        click.echo(f"Wrote palette summary to {summary_palette_csv}")


if __name__ == "__main__":
    main()
