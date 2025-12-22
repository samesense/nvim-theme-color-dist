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

ROLE_PAIRS = [
    ("background", "surface"),
    ("surface", "overlay"),
    ("overlay", "text"),
    ("background", "text"),
]


@click.command()
@click.argument(
    "catppuccin_colors_csv",
    type=click.Path(exists=True, path_type=Path),
)
@click.option(
    "--out",
    default="deltaL_margins.csv",
    show_default=True,
    type=click.Path(path_type=Path),
)
def compute_deltaL(catppuccin_colors_csv: Path, out: Path):
    """
    Compute ΔL* margins between semantic role pairs
    for Catppuccin palettes.
    """
    df = pd.read_csv(catppuccin_colors_csv)

    # Expect columns: palette, element, L, a, b
    if not {"palette", "element", "L"}.issubset(df.columns):
        raise click.ClickException("CSV must contain palette, element, L columns")

    # Map elements → roles
    df["role"] = df["element"].map(ROLE_MAP)
    df = df.dropna(subset=["role"])

    rows = []

    for palette, sub in df.groupby("palette"):
        for low, high in ROLE_PAIRS:
            L_low = sub[sub.role == low]["L"].mean()
            L_high = sub[sub.role == high]["L"].mean()

            rows.append(
                {
                    "palette": palette,
                    "low_role": low,
                    "high_role": high,
                    "pair": f"{low}→{high}",
                    "delta_L": L_high - L_low,
                }
            )

    out.write_text(pd.DataFrame(rows).to_csv(index=False))
    click.echo(f"✓ Wrote {out} ({len(rows)} rows)")


if __name__ == "__main__":
    compute_deltaL()
