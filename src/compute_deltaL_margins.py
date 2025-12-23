from pathlib import Path

import click
import pandas as pd

# ------------------------------------------------------------
# Role ordering (lower → higher)
# ------------------------------------------------------------

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
@click.option(
    "--colors-csv",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
)
@click.option(
    "--out",
    default="deltaL_margins.csv",
    show_default=True,
    type=click.Path(dir_okay=False, path_type=Path),
)
def compute_deltaL(colors_csv: Path, out: Path):
    """
    Compute per-color ΔL* distributions between semantic role pairs.
    """
    df = pd.read_csv(colors_csv)

    if not {"palette", "element", "L"}.issubset(df.columns):
        raise click.ClickException("CSV must contain palette, element, L columns")

    df["role"] = df["element"].map(ROLE_MAP)
    df = df.dropna(subset=["role"])

    rows = []

    for palette, sub in df.groupby("palette"):
        for low, high in ROLE_PAIRS:
            low_colors = sub[sub.role == low]
            high_colors = sub[sub.role == high]

            for _, lo in low_colors.iterrows():
                for _, hi in high_colors.iterrows():
                    rows.append(
                        {
                            "palette": palette,
                            "pair": f"{low}→{high}",
                            "low_element": lo.element,
                            "high_element": hi.element,
                            "delta_L": hi.L - lo.L,
                        }
                    )

    out.write_text(pd.DataFrame(rows).to_csv(index=False))
    click.echo(f"✓ Wrote {out} ({len(rows)} rows)")


if __name__ == "__main__":
    compute_deltaL()
