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


# ------------------------------------------------------------
# Plot
# ------------------------------------------------------------


def plot_hue_faceted(csv_path: Path, out_png: Path):
    df = pd.read_csv(csv_path)

    palettes = sorted(df["palette"].unique())
    roles = [r for r in ROLE_ORDER if r in df["role"].unique()]

    n_rows = len(palettes)
    n_cols = len(roles)

    fig, axes = plt.subplots(
        n_rows,
        n_cols,
        subplot_kw={"projection": "polar"},
        figsize=(3.2 * n_cols, 3.2 * n_rows),
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

            theta = np.deg2rad(sub["hue_deg"].values)
            bins = np.linspace(0, 2 * np.pi, N_BINS + 1)

            ax.hist(
                theta,
                bins=bins,
                density=True,
                alpha=0.9,
            )

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

    fig.suptitle(
        "Hue Distributions by Accent Role and Palette",
        y=1.02,
        fontsize=14,
    )

    fig.tight_layout()
    fig.savefig(out_png, dpi=200, bbox_inches="tight")
    plt.close(fig)

    print(f"✓ Saved {out_png}")


if __name__ == "__main__":
    csv_path = Path(sys.argv[1])
    out_png = Path(sys.argv[2])

    plot_hue_faceted(csv_path, out_png)
