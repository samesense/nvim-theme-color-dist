from pathlib import Path

import click
import numpy as np
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


def circular_mean_deg(deg):
    rad = np.deg2rad(deg)
    return float(
        np.rad2deg(np.arctan2(np.mean(np.sin(rad)), np.mean(np.cos(rad)))) % 360
    )


def circ_dist(a, b):
    d = abs(a - b) % 360
    return min(d, 360 - d)


@click.command()
@click.option(
    "--colors-csv",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
)
@click.option(
    "--out",
    default="ui_hue_coherence.csv",
    show_default=True,
    type=click.Path(dir_okay=False, path_type=Path),
)
def compute_ui_hue_coherence(colors_csv: Path, out: Path):
    df = pd.read_csv(colors_csv)

    if not {"palette", "element", "a", "b"}.issubset(df.columns):
        raise click.ClickException("CSV must contain palette, element, a, b columns")

    df["role"] = df["element"].map(ROLE_MAP)
    df = df.dropna(subset=["role"])

    rows = []
    for palette, sub in df.groupby("palette"):
        role_hues = {}
        for role, rsub in sub.groupby("role"):
            if role not in ["background", "surface", "overlay", "text"]:
                continue
            hues = np.degrees(np.arctan2(rsub["b"], rsub["a"])) % 360
            role_hues[role] = circular_mean_deg(hues)

        roles = list(role_hues.keys())
        if len(roles) < 2:
            continue

        dists = []
        for i in range(len(roles)):
            for j in range(i + 1, len(roles)):
                dists.append(circ_dist(role_hues[roles[i]], role_hues[roles[j]]))

        rows.append(
            {
                "palette": palette,
                "max_dist": float(max(dists)),
                "mean_dist": float(np.mean(dists)),
            }
        )

    out.write_text(pd.DataFrame(rows).to_csv(index=False))
    click.echo(f"✓ Wrote {out} ({len(rows)} rows)")


if __name__ == "__main__":
    compute_ui_hue_coherence()
