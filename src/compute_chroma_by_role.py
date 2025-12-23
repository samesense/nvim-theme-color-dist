from pathlib import Path

import click
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
# Core computation
# ------------------------------------------------------------


def compute_chroma_by_role_palette(lab_csv: Path) -> pd.DataFrame:
    """
    Input: catppuccin_lab.csv

    Output columns:
      palette, element, role, chroma
    """
    df = pd.read_csv(lab_csv)

    df["role"] = df["element"].map(ROLE_MAP)
    df = df.dropna(subset=["role"])

    # Chroma C* = sqrt(a^2 + b^2)
    df["chroma"] = np.sqrt(df["a"] ** 2 + df["b"] ** 2)

    return df[["palette", "element", "role", "chroma"]]


def summarize_chroma_by_role_palette(df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate chroma statistics per (palette, role)
    """
    return (
        df.groupby(["palette", "role"])
        .agg(
            n=("chroma", "size"),
            chroma_mean=("chroma", "mean"),
            chroma_median=("chroma", "median"),
            chroma_q25=("chroma", lambda x: np.percentile(x, 25)),
            chroma_q75=("chroma", lambda x: np.percentile(x, 75)),
        )
        .reset_index()
    )


# ------------------------------------------------------------
# CLI
# ------------------------------------------------------------


@click.command()
@click.option(
    "--lab-csv",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
    help="Input CSV with Lab values (must include palette, element, a, b).",
)
@click.option(
    "--out-csv",
    type=click.Path(dir_okay=False, path_type=Path),
    required=True,
    help="Output CSV for per-color chroma data.",
)
@click.option(
    "--summary-csv",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Optional output CSV for palette-aware chroma summary.",
)
def main(lab_csv: Path, out_csv: Path, summary_csv: Path | None):
    """
    Compute chroma (C*) per color, grouped by semantic role and palette.
    """
    df = compute_chroma_by_role_palette(lab_csv)
    df.to_csv(out_csv, index=False)

    if summary_csv is not None:
        summary = summarize_chroma_by_role_palette(df)
        summary.to_csv(summary_csv, index=False)

    click.echo(f"Wrote {len(df)} rows to {out_csv}")
    if summary_csv is not None:
        click.echo(f"Wrote summary to {summary_csv}")


if __name__ == "__main__":
    main()
