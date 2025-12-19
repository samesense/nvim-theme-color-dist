import itertools

import click
import numpy as np
import pandas as pd

# ============================================================
# Catppuccin role definitions
# ============================================================

CATPPUCCIN_ROLES = [
    "background",
    "surface",
    "overlay",
    "text",
    "accent_cool",
    "accent_warm",
    "accent_red",
    "accent_bridge",
]

# Expected relative lightness ordering (lower = darker)
# Accents are intentionally unconstrained
ROLE_LIGHTNESS_RANK = {
    "background": 0,
    "surface": 1,
    "overlay": 2,
    "text": 3,
}


# ============================================================
# Utilities
# ============================================================


def build_role_distance_matrix(df):
    """
    Build {(role1, role2): distance} symmetric matrix
    """
    mat = {}
    for _, r in df.iterrows():
        a, b = sorted([r.role1, r.role2])
        mat[(a, b)] = r.distance
    return mat


def image_role_centroids(img_df):
    """
    Compute CIELAB centroid per image role
    """
    return img_df.groupby("role")[["L", "a", "b"]].mean().to_dict("index")


def image_lightness_rank(centroids):
    """
    Rank image roles by increasing lightness (darkest = 0)
    """
    Ls = {r: v["L"] for r, v in centroids.items()}
    ordered = sorted(Ls, key=Ls.get)
    return {r: i for i, r in enumerate(ordered)}


def matrix_mismatch(image_mat, cat_mat, mapping):
    """
    Mean absolute ΔE mismatch under a proposed mapping
    """
    err = 0.0
    n = 0

    for (i1, i2), d_img in image_mat.items():
        c1 = mapping[i1]
        c2 = mapping[i2]
        key = tuple(sorted([c1, c2]))

        if key not in cat_mat:
            continue

        err += abs(d_img - cat_mat[key])
        n += 1

    return err / max(n, 1)


def extreme_dark_penalty(image_rank, mapping):
    """
    Penalize mapping the *absolute* darkest image role to background
    """
    darkest = min(image_rank, key=image_rank.get)
    if mapping[darkest] == "background":
        return 2.0
    return 0.0


def ordering_penalty(image_rank, mapping):
    """
    Penalize violations of relative lightness ordering
    """
    penalty = 0.0

    for r1, r2 in itertools.combinations(image_rank.keys(), 2):
        img_order = image_rank[r1] - image_rank[r2]

        c1 = mapping[r1]
        c2 = mapping[r2]

        if c1 in ROLE_LIGHTNESS_RANK and c2 in ROLE_LIGHTNESS_RANK:
            cat_order = ROLE_LIGHTNESS_RANK[c1] - ROLE_LIGHTNESS_RANK[c2]

            # Sign disagreement = ordering violation
            if img_order * cat_order < 0:
                penalty += 1.0

    return penalty


def confidence_from_scores(best, second):
    """
    Interpretable confidence ∈ [0, 1]
    """
    if second <= 0:
        return 1.0
    return max(0.0, 1.0 - best / second)


# ============================================================
# Main script
# ============================================================


@click.command()
@click.argument("image_colors_csv", type=click.Path(exists=True))
@click.argument("catppuccin_distances_csv", type=click.Path(exists=True))
@click.argument("out_csv", type=click.Path(exists=False))
@click.option("--palette", default="mocha", help="Catppuccin palette name")
def assign_roles(image_colors_csv, catppuccin_distances_csv, out_csv, palette):
    """
    Assign perceptual image roles to Catppuccin roles
    using semantic constraints + ΔE geometry.
    """

    # --------------------------------------------------------
    # Load image role centroids
    # --------------------------------------------------------
    img = pd.read_csv(image_colors_csv)
    centroids = image_role_centroids(img)
    image_roles = sorted(centroids.keys())

    image_rank = image_lightness_rank(centroids)

    # Dark cluster logic: background = median of darkest K
    DARK_CLUSTER_SIZE = 3
    dark_roles = sorted(image_rank, key=image_rank.get)[:DARK_CLUSTER_SIZE]
    background_candidate = dark_roles[DARK_CLUSTER_SIZE // 2]

    # Compute image role–role distances
    img_rows = []
    for r1, r2 in itertools.combinations(image_roles, 2):
        v1 = np.array(list(centroids[r1].values()))
        v2 = np.array(list(centroids[r2].values()))
        d = np.linalg.norm(v1 - v2)
        img_rows.append({"role1": r1, "role2": r2, "distance": d})

    img_mat = build_role_distance_matrix(pd.DataFrame(img_rows))

    # --------------------------------------------------------
    # Load Catppuccin role distances
    # --------------------------------------------------------
    cat = pd.read_csv(catppuccin_distances_csv)
    cat = cat[cat.palette == palette]

    # Map elements → roles
    CATPPUCCIN_ROLE_MAP = {
        "crust": "background",
        "mantle": "background",
        "base": "background",
        "surface0": "surface",
        "surface1": "surface",
        "surface2": "surface",
        "overlay0": "overlay",
        "overlay1": "overlay",
        "overlay2": "overlay",
        "text": "text",
        "subtext0": "text",
        "subtext1": "text",
        "blue": "accent_cool",
        "sky": "accent_cool",
        "sapphire": "accent_cool",
        "lavender": "accent_cool",
        "peach": "accent_warm",
        "yellow": "accent_warm",
        "green": "accent_warm",
        "red": "accent_red",
        "maroon": "accent_red",
        "pink": "accent_red",
        "rosewater": "accent_red",
        "flamingo": "accent_red",
        "mauve": "accent_bridge",
    }

    cat["role1"] = cat.element1.map(CATPPUCCIN_ROLE_MAP)
    cat["role2"] = cat.element2.map(CATPPUCCIN_ROLE_MAP)
    cat = cat.dropna(subset=["role1", "role2"])

    cat_role_dists = cat.groupby(["role1", "role2"]).distance.mean().reset_index()

    cat_mat = build_role_distance_matrix(cat_role_dists)

    # --------------------------------------------------------
    # Search assignments
    # --------------------------------------------------------
    results = []

    for perm in itertools.permutations(CATPPUCCIN_ROLES, len(image_roles)):
        mapping = dict(zip(image_roles, perm))

        # HARD constraint: background must be median dark role
        if mapping[background_candidate] != "background":
            continue

        geom = matrix_mismatch(img_mat, cat_mat, mapping)
        order_pen = ordering_penalty(image_rank, mapping)
        extreme_pen = extreme_dark_penalty(image_rank, mapping)

        score = geom + 1.5 * order_pen + 0.5 * extreme_pen
        results.append((mapping, score))

    results.sort(key=lambda x: x[1])

    if not results:
        raise RuntimeError("No valid role assignments found.")

    best_map, best_score = results[0]
    second_score = results[1][1] if len(results) > 1 else best_score

    confidence = confidence_from_scores(best_score, second_score)

    # --------------------------------------------------------
    # Output
    # --------------------------------------------------------
    out = pd.DataFrame(
        [
            {
                "image_role": k,
                "assigned_catppuccin_role": v,
                "confidence": confidence,
            }
            for k, v in best_map.items()
        ]
    ).sort_values("image_role")

    out.to_csv(out_csv, index=False)

    print("\nBest role assignment:\n")
    print(out)
    print(f"\nMean score: {best_score:.2f}")
    print(f"Confidence: {confidence:.3f}")


if __name__ == "__main__":
    assign_roles()
