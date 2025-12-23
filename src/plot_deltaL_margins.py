from pathlib import Path

import click
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns


@click.command()
@click.argument(
    "deltal_csv",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
@click.option(
    "--out",
    default="deltaL_margins_by_palette.png",
    show_default=True,
    type=click.Path(dir_okay=False, path_type=Path),
)
def plot_deltaL(deltal_csv: Path, out: Path):
    """
    Plot ΔL* margin distributions by semantic role pair,
    faceted by Catppuccin palette.
    """
    df = pd.read_csv(deltal_csv)

    required = {"palette", "pair", "delta_L"}
    if not required.issubset(df.columns):
        missing = ", ".join(sorted(required - set(df.columns)))
        raise click.ClickException(f"Missing required columns: {missing}")

    sns.set_theme(style="whitegrid")

    # Ensure consistent ordering of role pairs
    pair_order = [
        "background→surface",
        "surface→overlay",
        "overlay→text",
        "background→text",
    ]
    df["pair"] = pd.Categorical(df["pair"], categories=pair_order, ordered=True)

    g = sns.catplot(
        data=df,
        x="pair",
        y="delta_L",
        row="palette",
        kind="violin",
        inner="quartile",
        cut=0,
        sharey=True,
        height=2.2,
        aspect=3.0,
    )

    g.set_axis_labels("", "ΔL* (higher − lower)")
    g.set_titles("{row_name}")

    # Add reference line at zero in each facet
    for ax in g.axes.flat:
        ax.axhline(0, color="black", linewidth=0.8, linestyle="--")

    g.fig.suptitle(
        "Catppuccin ΔL* Margins by Semantic Role Pair and Palette",
        y=1.02,
    )

    plt.tight_layout()
    plt.savefig(out, dpi=200, bbox_inches="tight")
    plt.close()


if __name__ == "__main__":
    plot_deltaL()
