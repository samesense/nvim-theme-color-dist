"""
Compute intra-role L* offsets between Catppuccin element variants.

Learns the spacing patterns within each semantic role:
  - background: base→mantle, base→crust
  - surface: surface1→surface0, surface1→surface2
  - overlay: overlay1→overlay0, overlay1→overlay2
  - text: text→subtext1, text→subtext0

These offsets replace hardcoded magic numbers like +4, -4, +6, -6, -12.
"""

from pathlib import Path

import click
import numpy as np
import pandas as pd

# ------------------------------------------------------------
# Element offset definitions
# ------------------------------------------------------------

# (anchor, target) pairs within each role
OFFSET_PAIRS = {
    "background": [
        ("base", "mantle"),
        ("base", "crust"),
    ],
    "surface": [
        ("surface1", "surface0"),
        ("surface1", "surface2"),
    ],
    "overlay": [
        ("overlay1", "overlay0"),
        ("overlay1", "overlay2"),
    ],
    "text": [
        ("text", "subtext1"),
        ("text", "subtext0"),
    ],
}


def compute_element_offsets(lab_csv: Path) -> pd.DataFrame:
    """
    Compute L* offsets between element pairs within each role.

    Returns DataFrame with columns:
        palette, role, anchor, target, offset_name, delta_L
    """
    df = pd.read_csv(lab_csv)

    if not {"palette", "element", "L"}.issubset(df.columns):
        raise ValueError("CSV must contain palette, element, L columns")

    rows = []

    for palette, sub in df.groupby("palette"):
        # Build lookup: element -> L
        elem_L = dict(zip(sub["element"], sub["L"]))

        for role, pairs in OFFSET_PAIRS.items():
            for anchor, target in pairs:
                if anchor not in elem_L or target not in elem_L:
                    continue

                delta = elem_L[target] - elem_L[anchor]
                offset_name = f"{target}_from_{anchor}"

                rows.append(
                    {
                        "palette": palette,
                        "role": role,
                        "anchor": anchor,
                        "target": target,
                        "offset_name": offset_name,
                        "delta_L": delta,
                    }
                )

    return pd.DataFrame(rows)


def summarize_offsets(df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate offset statistics across palettes.

    Groups by (role, offset_name) and computes q10, q25, median, q75, q90.
    """
    return (
        df.groupby(["role", "offset_name"])
        .agg(
            n=("delta_L", "size"),
            q10=("delta_L", lambda x: np.percentile(x, 10)),
            q25=("delta_L", lambda x: np.percentile(x, 25)),
            median=("delta_L", "median"),
            q75=("delta_L", lambda x: np.percentile(x, 75)),
            q90=("delta_L", lambda x: np.percentile(x, 90)),
        )
        .reset_index()
    )


def summarize_offsets_by_palette(df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate offset statistics per palette.

    Groups by (palette, role, offset_name).
    """
    return (
        df.groupby(["palette", "role", "offset_name"])
        .agg(
            delta_L=("delta_L", "first"),  # single value per palette
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
    help="Output CSV for per-palette offset data.",
)
@click.option(
    "--summary-csv",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Optional output CSV for cross-palette offset summary.",
)
def main(lab_csv: Path, out_csv: Path, summary_csv: Path | None):
    """
    Compute L* offsets between element variants within semantic roles.
    """
    df = compute_element_offsets(lab_csv)
    df.to_csv(out_csv, index=False)
    click.echo(f"Wrote {len(df)} rows to {out_csv}")

    if summary_csv is not None:
        summary = summarize_offsets(df)
        summary.to_csv(summary_csv, index=False)
        click.echo(f"Wrote summary to {summary_csv}")


if __name__ == "__main__":
    main()
