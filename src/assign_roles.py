import itertools

import click
import numpy as np
import pandas as pd

# ---- CONFIG: Catppuccin element → role mapping ----
CATPPUCCIN_ROLE_MAP = {
    # background
    "crust": "background",
    "mantle": "background",
    "base": "background",
    # surfaces
    "surface0": "surface",
    "surface1": "surface",
    "surface2": "surface",
    # overlays
    "overlay0": "overlay",
    "overlay1": "overlay",
    "overlay2": "overlay",
    # text
    "text": "text",
    "subtext0": "text",
    "subtext1": "text",
    # accents
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


# ---- utilities ----


def build_role_distance_matrix(df, role_col1="role1", role_col2="role2"):
    """
    Returns a dict {(role1, role2): distance}
    Symmetric, role1 < role2
    """
    mat = {}
    for _, r in df.iterrows():
        a, b = sorted([r[role_col1], r[role_col2]])
        mat[(a, b)] = r.distance
    return mat


def matrix_mismatch(image_mat, cat_mat, mapping):
    """
    Sum of absolute differences between role–role distances
    under a proposed mapping.
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


def confidence_from_errors(best, second):
    """
    Simple, interpretable confidence score ∈ [0, 1]
    """
    if second == 0:
        return 1.0
    return max(0.0, 1.0 - best / second)


# ---- main script ----


@click.command()
@click.argument("image_colors_csv", type=click.Path(exists=True))
@click.argument("catppuccin_distances_csv", type=click.Path(exists=True))
@click.argument("out_csv", type=click.Path(exists=False))
@click.option("--palette", default="mocha", help="Catppuccin palette name")
def assign_roles(image_colors_csv, catppuccin_distances_csv, out_csv, palette):
    """
    Assign perceptual image roles to Catppuccin roles using ΔE role geometry.
    """

    # ---------- load image role centroids ----------
    img = pd.read_csv(image_colors_csv)

    centroids = img.groupby("role")[["L", "a", "b"]].mean().to_dict("index")

    image_roles = sorted(centroids.keys())

    # compute image role–role distances
    img_rows = []
    for r1, r2 in itertools.combinations(image_roles, 2):
        v1 = np.array(list(centroids[r1].values()))
        v2 = np.array(list(centroids[r2].values()))
        d = np.linalg.norm(v1 - v2)
        img_rows.append({"role1": r1, "role2": r2, "distance": d})

    img_mat = build_role_distance_matrix(pd.DataFrame(img_rows))

    # ---------- load catppuccin distances ----------
    cat_raw = pd.read_csv(catppuccin_distances_csv)
    cat_raw = cat_raw[cat_raw.palette == palette]

    cat_raw["role1"] = cat_raw.element1.map(CATPPUCCIN_ROLE_MAP)
    cat_raw["role2"] = cat_raw.element2.map(CATPPUCCIN_ROLE_MAP)
    cat_raw = cat_raw.dropna(subset=["role1", "role2"])

    cat_role_dists = cat_raw.groupby(["role1", "role2"]).distance.mean().reset_index()

    cat_roles = sorted(set(cat_role_dists.role1) | set(cat_role_dists.role2))
    cat_mat = build_role_distance_matrix(cat_role_dists)

    # ---------- search assignments ----------
    results = []

    for perm in itertools.permutations(cat_roles, len(image_roles)):
        mapping = dict(zip(image_roles, perm))
        err = matrix_mismatch(img_mat, cat_mat, mapping)
        results.append((mapping, err))

    results.sort(key=lambda x: x[1])
    best_map, best_err = results[0]
    second_err = results[1][1] if len(results) > 1 else best_err

    confidence = confidence_from_errors(best_err, second_err)

    # ---------- output ----------
    out = pd.DataFrame(
        [
            {
                "image_role": k,
                "assigned_catppuccin_role": v,
                "confidence": confidence,
            }
            for k, v in best_map.items()
        ]
    )

    out = out.sort_values("image_role")
    out.to_csv(out_csv, index=False)

    print("\nBest role assignment:\n")
    print(out)
    print(f"\nGlobal confidence: {confidence:.3f}")
    print(f"Mean ΔE mismatch: {best_err:.2f}")


if __name__ == "__main__":
    assign_roles()
