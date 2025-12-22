import sys
from pathlib import Path

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

# ------------------------------------------------------------
# Plot
# ------------------------------------------------------------


def plot_chroma_by_role(csv_path: Path, out_png: Path):
    df = pd.read_csv(csv_path)

    # Ensure consistent ordering
    df["role"] = pd.Categorical(df["role"], categories=ROLE_ORDER, ordered=True)
    df = df.sort_values("role")

    data = [
        df.loc[df["role"] == role, "chroma"].values
        for role in ROLE_ORDER
        if role in df["role"].values
    ]

    labels = [ROLE_LABELS[r] for r in ROLE_ORDER if r in df["role"].values]

    plt.figure(figsize=(11, 6))

    parts = plt.violinplot(
        data,
        showmeans=False,
        showmedians=True,
        showextrema=False,
    )

    # Style violins
    for pc in parts["bodies"]:
        pc.set_facecolor("#4C72B0")
        pc.set_edgecolor("black")
        pc.set_alpha(0.85)

    parts["cmedians"].set_color("black")
    parts["cmedians"].set_linewidth(1.5)

    plt.xticks(range(1, len(labels) + 1), labels, rotation=30, ha="right")
    plt.ylabel("Chroma (C*)")
    plt.title("Catppuccin Chroma Distribution by Semantic Role")

    plt.grid(axis="y", linestyle="--", alpha=0.4)
    plt.tight_layout()

    plt.savefig(out_png, dpi=200)
    plt.close()


if __name__ == "__main__":
    csv_path = sys.argv[1]
    out_png = sys.argv[2]

    plot_chroma_by_role(csv_path, out_png)
