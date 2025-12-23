from pathlib import Path

import click
import matplotlib.pyplot as plt
import pandas as pd

# ------------------------------------------------------------
# Configuration
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

ROLE_LABELS = {
    "background": "Background",
    "surface": "Surface",
    "overlay": "Overlay",
    "text": "Text",
    "accent_red": "Accent Red",
    "accent_warm": "Accent Warm",
    "accent_cool": "Accent Cool",
    "accent_bridge": "Accent Bridge",
}

DEFAULT_PALETTE_ORDER = ["latte", "frappe", "macchiato", "mocha"]

# ------------------------------------------------------------
# Plot
# ------------------------------------------------------------


def plot_chroma_by_role_palette(
    csv_path: Path,
    out_png: Path,
    palette_order: list[str],
):
    df = pd.read_csv(csv_path)

    # Ensure ordering
    df["role"] = pd.Categorical(df["role"], categories=ROLE_ORDER, ordered=True)
    df["palette"] = pd.Categorical(
        df["palette"], categories=palette_order, ordered=True
    )

    palettes = [p for p in palette_order if p in df["palette"].unique()]

    fig, axes = plt.subplots(
        nrows=len(palettes),
        ncols=1,
        figsize=(12, 3.2 * len(palettes)),
        sharex=True,
        sharey=True,
    )

    if len(palettes) == 1:
        axes = [axes]

    for ax, palette in zip(axes, palettes):
        sub = df[df["palette"] == palette]

        data = [
            sub.loc[sub["role"] == role, "chroma"].values
            for role in ROLE_ORDER
            if role in sub["role"].values
        ]

        labels = [ROLE_LABELS[r] for r in ROLE_ORDER if r in sub["role"].values]

        parts = ax.violinplot(
            data,
            showmeans=False,
            showmedians=True,
            showextrema=False,
        )

        for pc in parts["bodies"]:
            pc.set_facecolor("#4C72B0")
            pc.set_edgecolor("black")
            pc.set_alpha(0.85)

        parts["cmedians"].set_color("black")
        parts["cmedians"].set_linewidth(1.5)

        ax.set_title(palette.capitalize(), loc="left", fontsize=12, pad=6)
        ax.grid(axis="y", linestyle="--", alpha=0.4)

    axes[-1].set_xticks(range(1, len(labels) + 1))
    axes[-1].set_xticklabels(labels, rotation=30, ha="right")

    fig.supylabel("Colorfulness (chroma)")
    fig.suptitle(
        "Catppuccin Colorfulness by Semantic Role and Palette",
        y=0.98,
    )

    plt.tight_layout(rect=[0, 0, 1, 0.96])
    plt.savefig(out_png, dpi=200)
    plt.close()

    click.echo(f"Wrote {out_png}")


# ------------------------------------------------------------
# CLI
# ------------------------------------------------------------


@click.command()
@click.option(
    "--csv",
    "csv_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
    help="Input CSV with columns: palette, role, chroma.",
)
@click.option(
    "--out",
    "out_png",
    type=click.Path(dir_okay=False, path_type=Path),
    required=True,
    help="Output PNG path.",
)
@click.option(
    "--palette-order",
    default=",".join(DEFAULT_PALETTE_ORDER),
    help="Comma-separated palette order (default: latte,frappe,macchiato,mocha).",
)
def main(csv_path: Path, out_png: Path, palette_order: str):
    """
    Plot chroma distributions by semantic role, faceted by palette.
    """
    order = [p.strip() for p in palette_order.split(",") if p.strip()]
    plot_chroma_by_role_palette(csv_path, out_png, order)


if __name__ == "__main__":
    main()
