import sys

import click
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from PIL import Image
from scipy.cluster.hierarchy import dendrogram, fcluster, linkage
from scipy.spatial.distance import pdist
from skimage.color import rgb2lab


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

    click.echo("✅ Phase 1 complete.")
    click.echo(
        "Next steps: role summaries, distance constraints, representative selection."
    )


if __name__ == "__main__":
    extract_theme()
