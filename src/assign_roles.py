import itertools

import click
import numpy as np
import pandas as pd

# ============================================================
# Constants
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

STRUCTURAL_ROLES = ["background", "surface", "overlay", "text"]
ACCENT_ROLES = ["accent_cool", "accent_warm", "accent_red", "accent_bridge"]

ROLE_LIGHTNESS_RANK = {
    "background": 0,
    "surface": 1,
    "overlay": 2,
    "text": 3,
}

ROLE_FLEXIBILITY = {
    "background": 0.0,
    "surface": 0.2,
    "overlay": 0.4,
    "text": 0.6,
    "accent_bridge": 0.8,
    "accent_red": 1.0,
    "accent_warm": 1.0,
    "accent_cool": 1.0,
}

# Early-exit / speed controls
MAX_STRUCTURAL_TRIES = 50
MAX_TOTAL_EVALS = 5000
GOOD_ENOUGH_SCORE = 8.0

# Structural readability thresholds
MIN_TEXT_BG_DELTA = 35.0
MIN_UI_BG_DELTA = 25.0
MIN_SURFACE_BG_DELTA = 15.0
MIN_OVERLAY_SURFACE_DELTA = 10.0
MIN_TEXT_OVERLAY_DELTA = 20.0


# ============================================================
# Utilities
# ============================================================


def build_role_distance_matrix(df):
    mat = {}
    for _, r in df.iterrows():
        a, b = sorted([r.role1, r.role2])
        mat[(a, b)] = r.distance
    return mat


def image_role_centroids(img_df):
    return img_df.groupby("role")[["L", "a", "b"]].mean().to_dict("index")


def image_lightness_rank(centroids):
    ordered = sorted(centroids, key=lambda r: centroids[r]["L"])
    return {r: i for i, r in enumerate(ordered)}


def matrix_mismatch(image_mat, cat_mat, mapping):
    err, n = 0.0, 0
    for (i1, i2), d_img in image_mat.items():
        c1, c2 = mapping[i1], mapping[i2]
        key = tuple(sorted([c1, c2]))
        if key in cat_mat:
            err += abs(d_img - cat_mat[key])
            n += 1
    return err / max(n, 1)


def ordering_penalty(image_rank, mapping):
    p = 0.0
    for r1, r2 in itertools.combinations(image_rank, 2):
        if mapping[r1] in ROLE_LIGHTNESS_RANK and mapping[r2] in ROLE_LIGHTNESS_RANK:
            img = image_rank[r1] - image_rank[r2]
            cat = ROLE_LIGHTNESS_RANK[mapping[r1]] - ROLE_LIGHTNESS_RANK[mapping[r2]]
            if img * cat < 0:
                p += 1
    return p


def flexibility_penalty(image_rank, mapping):
    return sum(
        (1.0 - ROLE_FLEXIBILITY[mapping[r]]) * image_rank[r] for r in mapping
    ) / len(mapping)


# ============================================================
# Structural feasibility
# ============================================================


def has_valid_structural_configuration(df):
    try:
        bg = df[df.assigned_catppuccin_role == "background"]["L"].min()
        surface = df[df.assigned_catppuccin_role == "surface"]["L"].median()
        overlay = df[df.assigned_catppuccin_role == "overlay"]["L"].median()
        text = df[df.assigned_catppuccin_role == "text"]["L"].max()
    except Exception:
        return False, 0.0

    deltas = [
        surface - bg,
        overlay - bg,
        overlay - surface,
        text - overlay,
        text - bg,
    ]

    ok = (
        surface - bg >= MIN_SURFACE_BG_DELTA
        and overlay - bg >= MIN_UI_BG_DELTA
        and overlay - surface >= MIN_OVERLAY_SURFACE_DELTA
        and text - overlay >= MIN_TEXT_OVERLAY_DELTA
        and text - bg >= MIN_TEXT_BG_DELTA
    )

    return ok, min(deltas)


# ============================================================
# Re-tinting (STRUCTURAL ONLY)
# ============================================================


def retint_structural_roles(df):
    """
    Expand L* span for structural roles without touching hue (a/b).
    Deterministic and minimal.
    """
    out = df.copy()

    for role, target_L in [
        ("background", 12.0),
        ("surface", 28.0),
        ("overlay", 42.0),
        ("text", 72.0),
    ]:
        mask = out.assigned_catppuccin_role == role
        if not mask.any():
            continue
        out.loc[mask, "L"] = out.loc[mask, "L"].clip(
            lower=target_L - 5, upper=target_L + 5
        )

    return out


# ============================================================
# Pruning (AFTER feasibility only)
# ============================================================


def prune_colors_by_role(df):
    kept = []
    for role, sub in df.groupby("assigned_catppuccin_role"):
        if role in STRUCTURAL_ROLES:
            lo, hi = sub.L.quantile([0.15, 0.85])
            kept.append(sub[(sub.L >= lo) & (sub.L <= hi)])
        else:
            kept.append(sub.sort_values("frequency", ascending=False).head(40))
    return pd.concat(kept, ignore_index=True)


# ============================================================
# Main
# ============================================================


@click.command()
@click.argument("image_colors_csv", type=click.Path(exists=True))
@click.argument("catppuccin_distances_csv", type=click.Path(exists=True))
@click.argument("out_csv", type=click.Path())
@click.option("--palette", default="mocha")
def assign_roles(image_colors_csv, catppuccin_distances_csv, out_csv, palette):
    img = pd.read_csv(image_colors_csv)

    centroids = image_role_centroids(img)
    image_roles = sorted(centroids)
    image_rank = image_lightness_rank(centroids)

    # image distances
    img_rows = []
    for r1, r2 in itertools.combinations(image_roles, 2):
        v1 = np.array(list(centroids[r1].values()))
        v2 = np.array(list(centroids[r2].values()))
        img_rows.append({"role1": r1, "role2": r2, "distance": np.linalg.norm(v1 - v2)})
    img_mat = build_role_distance_matrix(pd.DataFrame(img_rows))

    # catppuccin distances
    cat = pd.read_csv(catppuccin_distances_csv)
    cat = cat[cat.palette == palette]

    ROLE_MAP = {
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

    cat["role1"] = cat.element1.map(ROLE_MAP)
    cat["role2"] = cat.element2.map(ROLE_MAP)
    cat = cat.dropna(subset=["role1", "role2"])

    cat_mat = build_role_distance_matrix(
        cat.groupby(["role1", "role2"]).distance.mean().reset_index()
    )

    # ========================================================
    # STAGE 1: structural feasibility (with retint)
    # ========================================================

    viable_structural = []

    for clusters in itertools.permutations(image_roles, 4):
        struct_map = dict(zip(clusters, STRUCTURAL_ROLES))

        assigned = img.copy()
        assigned["assigned_catppuccin_role"] = assigned.role.map(
            lambda r: struct_map.get(r, "accent_cool")
        )

        ok, margin = has_valid_structural_configuration(assigned)

        if not ok:
            assigned = retint_structural_roles(assigned)
            ok, margin = has_valid_structural_configuration(assigned)
            if not ok:
                continue

        viable_structural.append((struct_map, margin))
        if len(viable_structural) >= MAX_STRUCTURAL_TRIES:
            break

    if not viable_structural:
        raise RuntimeError(
            "Rejected palette: no readable structural configuration found"
        )

    viable_structural.sort(key=lambda x: x[1], reverse=True)

    # ========================================================
    # STAGE 2: full mapping
    # ========================================================

    best_map = None
    best_score = float("inf")
    total = 0

    for struct_map, margin in viable_structural:
        remaining = [r for r in image_roles if r not in struct_map]

        for perm in itertools.permutations(ACCENT_ROLES, len(remaining)):
            mapping = struct_map | dict(zip(remaining, perm))

            score = (
                matrix_mismatch(img_mat, cat_mat, mapping)
                + ordering_penalty(image_rank, mapping)
                + flexibility_penalty(image_rank, mapping)
                - margin
            )

            total += 1
            if score < best_score:
                best_score = score
                best_map = mapping
                if score <= GOOD_ENOUGH_SCORE:
                    break

            if total >= MAX_TOTAL_EVALS:
                break

        if best_score <= GOOD_ENOUGH_SCORE or total >= MAX_TOTAL_EVALS:
            break

    if best_map is None:
        raise RuntimeError("No acceptable role assignment found")

    out = img.copy()
    out["assigned_catppuccin_role"] = out.role.map(best_map)
    out.to_csv(out_csv, index=False)


if __name__ == "__main__":
    assign_roles()
