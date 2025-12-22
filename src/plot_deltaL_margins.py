from pathlib import Path

import click
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns


@click.command()
@click.argument(
    "deltal_csv",
    type=click.Path(exists=True, path_type=Path),
)
@click.option(
    "--out",
    default="deltaL_margins.png",
    show_default=True,
    type=click.Path(path_type=Path),
)
def plot_deltaL(deltal_csv: Path, out: Path):
    """
    Plot ΔL* margin distributions by role pair.
    """
    df = pd.read_csv(deltal_csv)

    sns.set_theme(style="whitegrid")

    plt.figure(figsize=(8, 5))
    ax = sns.violinplot(
        data=df,
        x="pair",
        y="delta_L",
        inner="quartile",
        cut=0,
    )

    ax.set_ylabel("ΔL* (higher − lower)")
    ax.set_xlabel("")
    ax.set_title("Catppuccin ΔL* Margins by Semantic Role Pair")

    # Reference line at zero (ordering sanity)
    ax.axhline(0, color="black", linewidth=0.8, linestyle="--")

    plt.tight_layout()
    plt.savefig(out, dpi=200)
    plt.close()


if __name__ == "__main__":
    plot_deltaL()
