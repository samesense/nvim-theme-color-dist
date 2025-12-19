import sys

import click
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from PIL import Image
from rich.console import Console
from rich.style import Style
from rich.table import Table
from rich.text import Text
from scipy.cluster.hierarchy import dendrogram, fcluster, linkage
from scipy.spatial.distance import pdist
from skimage.color import rgb2lab


def rgb_to_hex(rgb):
    r, g, b = map(int, rgb)
    return "#{:02x}{:02x}{:02x}".format(r, g, b)


def render_role_strips(df, sort_by="frequency"):
    """
    df must contain:
      R, G, B, L, role
    """
    N = 80

    console = Console()
    table = Table(show_header=True, header_style="bold")

    table.add_column("Role", justify="right", style="cyan", no_wrap=True)
    table.add_column("Colors", justify="left")

    for role_id in sorted(df["role"].unique()):
        sub = df[df["role"] == role_id]

        # sort colors inside role
        if sort_by == "L":
            sub = sub.sort_values("L")
        elif sort_by == "frequency" and "frequency" in sub.columns:
            sub = sub.sort_values("frequency", ascending=False)

        strip = Text()
        for _, row in sub.iterrows():
            hex_color = rgb_to_hex((row.R, row.G, row.B))
            w = max(1, int(row.frequency * 300))
            strip.append("  " * w, style=Style(bgcolor=hex_color))

        table.add_row(f"Role {role_id}", strip)

    console.print(table)


def load_image_colors(path, max_pixels=100_000):
    img = Image.open(path).convert("RGB")
    arr = np.asarray(img).reshape(-1, 3)

    if len(arr) > max_pixels:
        idx = np.random.choice(len(arr), max_pixels, replace=False)
        arr = arr[idx]

    return arr


@click.command()
@click.argument("image_path", type=click.Path(exists=True))
@click.option("-k", "--roles", default=6, help="Number of color roles")
@click.option("--max-pixels", default=100_000, help="Max pixels to sample")
@click.option("--out-prefix", default="theme", help="Output prefix")
def extract_theme(image_path, roles, max_pixels, out_prefix):
    """
    Extract color roles from a painting and visualize them as a dendrogram.
    """

    rgb = load_image_colors(image_path, max_pixels=max_pixels)
    q = 8  # try 4, 8, 16
    rgb = (rgb // q) * q
    rgb = rgb.astype(np.uint8)

    # filter to colors that comprise >5% of sampled pixels
    total_pixels = len(rgb)
    uniques, counts = np.unique(rgb, axis=0, return_counts=True)
    freqs = counts / total_pixels
    mask = freqs > 0.0001
    if np.any(mask):
        rgb_use = uniques[mask]
        counts_use = counts[mask]
        freqs_use = freqs[mask]
        click.echo(
            f"🔢 Using {len(rgb_use)} colors (each >1% of pixels) for clustering..."
        )
    else:
        rgb_use = rgb
        click.echo(
            "⚠️ No single color exceeds 1% — using all sampled pixels for clustering..."
        )
        sys.exit(1)

    click.echo("🔬 Converting RGB → CIELAB...")
    lab = rgb2lab(rgb_use[np.newaxis, :, :] / 255.0)[0]

    click.echo("🌳 Computing hierarchical clustering...")
    dists = pdist(lab, metric="euclidean")
    Z = linkage(dists, method="average")

    click.echo("✂️ Cutting dendrogram into roles...")
    labels = fcluster(Z, t=roles, criterion="maxclust")

    # Save clustered colors
    df = pd.DataFrame(
        {
            "R": rgb_use[:, 0],
            "G": rgb_use[:, 1],
            "B": rgb_use[:, 2],
            "L": rgb_use[:, 0],
            "a": rgb_use[:, 1],
            "b": rgb_use[:, 2],
            "role": labels,
            "frequency": freqs_use,
        }
    )

    csv_path = f"{out_prefix}_colors.csv"
    df.to_csv(csv_path, index=False)
    click.echo(f"💾 Saved clustered colors → {csv_path}")

    # Plot dendrogram (milestone artifact)
    click.echo("🖼️ Rendering dendrogram...")
    plt.figure(figsize=(14, 6))
    dendrogram(Z, truncate_mode="lastp", p=roles * 3, show_leaf_counts=True)
    plt.title("Color Role Dendrogram (CIELAB space)")
    plt.xlabel("Cluster")
    plt.ylabel("ΔE distance")

    dendro_path = f"{out_prefix}_dendrogram.png"
    plt.tight_layout()
    plt.savefig(dendro_path, dpi=200)
    plt.close()

    click.echo(f"🌈 Dendrogram saved → {dendro_path}")

    df = pd.DataFrame(
        {
            "R": rgb_use[:, 0],
            "G": rgb_use[:, 1],
            "B": rgb_use[:, 2],
            "L": lab[:, 0],  # ✅ correct
            "a": lab[:, 1],
            "b": lab[:, 2],
            "role": labels,
            "frequency": freqs_use,
        }
    )

    render_role_strips(df, sort_by="L")


if __name__ == "__main__":
    extract_theme()
