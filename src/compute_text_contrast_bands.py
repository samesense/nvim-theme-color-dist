from pathlib import Path

import click
import pandas as pd

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
}


@click.command()
@click.option(
    "--colors-csv",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
)
@click.option(
    "--out",
    default="text_contrast.csv",
    show_default=True,
    type=click.Path(dir_okay=False, path_type=Path),
)
def compute_text_contrast(colors_csv: Path, out: Path):
    df = pd.read_csv(colors_csv)

    if not {"palette", "element", "L"}.issubset(df.columns):
        raise click.ClickException("CSV must contain palette, element, L columns")

    df["role"] = df["element"].map(ROLE_MAP)
    df = df.dropna(subset=["role"])

    rows = []
    for palette, sub in df.groupby("palette"):
        base = sub[sub["element"] == "base"]
        if base.empty:
            continue
        base_L = float(base.iloc[0]["L"])
        for elem in ["text", "subtext1", "subtext0"]:
            row = sub[sub["element"] == elem]
            if row.empty:
                continue
            L = float(row.iloc[0]["L"])
            rows.append(
                {
                    "palette": palette,
                    "element": elem,
                    "abs_delta_L": abs(L - base_L),
                }
            )

    out.write_text(pd.DataFrame(rows).to_csv(index=False))
    click.echo(f"✓ Wrote {out} ({len(rows)} rows)")


if __name__ == "__main__":
    compute_text_contrast()
