import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# ------------------------------------------------------------
# Configuration
# ------------------------------------------------------------

ROLE_ORDER = [
    "accent_red",
    "accent_warm",
    "accent_bridge",
    "accent_cool",
]

ROLE_LABELS = {
    "accent_red": "Red",
    "accent_warm": "Warm",
    "accent_bridge": "Bridge",
    "accent_cool": "Cool",
}

N_BINS = 24  # 15° bins


def circular_mean(deg):
    rad = np.deg2rad(deg)
    return np.rad2deg(np.arctan2(np.mean(np.sin(rad)), np.mean(np.cos(rad)))) % 360


def circular_quantile(deg, q):
    """
    Approximate circular quantile by unwrapping around circular mean.
    Good enough for tight hue clusters (which we have).
    """
    mean = circular_mean(deg)
    shifted = (deg - mean + 180) % 360 - 180
    return (np.percentile(shifted, q * 100) + mean) % 360


def compute_hue_windows(df):
    """
    Returns:
      role -> dict(median, q25, q75)
    """
    windows = {}

    for role, sub in df.groupby("role"):
        hues = sub["hue_deg"].values
        windows[role] = {
            "median": circular_mean(hues),
            "q25": circular_quantile(hues, 0.25),
            "q75": circular_quantile(hues, 0.75),
        }

    return windows


def plot_hue_faceted(csv_path: Path, out_png: Path):
    df = pd.read_csv(csv_path)

    palettes = sorted(df["palette"].unique())
    roles = [r for r in ROLE_ORDER if r in df["role"].unique()]

    hue_windows = compute_hue_windows(df)

    fig, axes = plt.subplots(
        len(palettes),
        len(roles),
        subplot_kw={"projection": "polar"},
        figsize=(3.2 * len(roles), 3.2 * len(palettes)),
        squeeze=False,
    )

    for i, palette in enumerate(palettes):
        df_pal = df[df["palette"] == palette]

        for j, role in enumerate(roles):
            ax = axes[i, j]
            sub = df_pal[df_pal["role"] == role]

            if sub.empty:
                ax.axis("off")
                continue

            # histogram
            theta = np.deg2rad(sub["hue_deg"].values)
            bins = np.linspace(0, 2 * np.pi, N_BINS + 1)

            ax.hist(theta, bins=bins, density=True, alpha=0.9)

            # overlay hue window
            w = hue_windows[role]
            q25 = np.deg2rad(w["q25"])
            q75 = np.deg2rad(w["q75"])
            med = np.deg2rad(w["median"])

            ax.bar(
                x=(q25 + q75) / 2,
                height=ax.get_ylim()[1],
                width=(q75 - q25) % (2 * np.pi),
                bottom=0,
                color="black",
                alpha=0.08,
                align="center",
            )

            ax.plot([med, med], [0, ax.get_ylim()[1]], color="black", lw=1.5)

            ax.set_theta_zero_location("E")
            ax.set_theta_direction(-1)
            ax.set_yticks([])

            if i == 0:
                ax.set_title(ROLE_LABELS[role], pad=10)

            if j == 0:
                ax.text(
                    -0.45,
                    0.5,
                    palette,
                    transform=ax.transAxes,
                    rotation=90,
                    va="center",
                    ha="center",
                    fontsize=11,
                    fontweight="bold",
                )

    fig.suptitle("Hue Distributions with Learned Hue Windows", y=1.02)
    fig.tight_layout()
    fig.savefig(out_png, dpi=200, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    csv_path = Path(sys.argv[1])
    out_png = Path(sys.argv[2])

    plot_hue_faceted(csv_path, out_png)
