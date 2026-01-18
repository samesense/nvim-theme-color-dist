from pathlib import Path

import click
import numpy as np
import pandas as pd

ROLE_MAP = {
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


def deltaE76(lab1: np.ndarray, lab2: np.ndarray) -> float:
    d = lab1 - lab2
    return float(np.sqrt(np.dot(d, d)))


@click.command()
@click.option(
    "--colors-csv",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
)
@click.option(
    "--out",
    default="accent_text_separation.csv",
    show_default=True,
    type=click.Path(dir_okay=False, path_type=Path),
)
def compute_accent_text_sep(colors_csv: Path, out: Path):
    df = pd.read_csv(colors_csv)

    if not {"palette", "element", "L", "a", "b"}.issubset(df.columns):
        raise click.ClickException(
            "CSV must contain palette, element, L, a, b columns"
        )

    rows = []
    for palette, sub in df.groupby("palette"):
        text = sub[sub["element"] == "text"]
        if text.empty:
            continue
        t = text.iloc[0]
        t_lab = np.array([float(t.L), float(t.a), float(t.b)], dtype=float)

        accents = sub[sub["element"].isin(ROLE_MAP.keys())].copy()
        for _, r in accents.iterrows():
            role = ROLE_MAP.get(r["element"])
            if role is None:
                continue
            a_lab = np.array([float(r.L), float(r.a), float(r.b)], dtype=float)
            rows.append(
                {
                    "palette": palette,
                    "role": role,
                    "element": r["element"],
                    "abs_delta_L": abs(float(r.L) - float(t.L)),
                    "delta_E": deltaE76(a_lab, t_lab),
                }
            )

    out.write_text(pd.DataFrame(rows).to_csv(index=False))
    click.echo(f"✓ Wrote {out} ({len(rows)} rows)")


if __name__ == "__main__":
    compute_accent_text_sep()
