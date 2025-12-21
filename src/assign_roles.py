import itertools

import click
import numpy as np
import pandas as pd
from rich.console import Console
from rich.style import Style
from rich.table import Table
from rich.text import Text

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

ROLE_LIGHTNESS_RANK = {
    "background": 0,
    "surface": 1,
    "overlay": 2,
    "text": 3,
}

# Higher = more permissive
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


def confidence_from_scores(best, second):
    return 1.0 if second <= 0 else max(0.0, 1.0 - best / second)


# ============================================================
# Color pruning (NEW)
# ============================================================


def prune_colors_by_role(df):
    """
    Prune conservatively, but NEVER below what assign_elements needs.
    Keeps extremes for structural roles, and enough colors per accent bucket.
    """
    # How many elements assign_elements.py wants per role bucket
    NEED = {
        "background": 3,  # base/mantle/crust
        "surface": 3,  # surface0/1/2
        "overlay": 3,  # overlay0/1/2
        "text": 3,  # text/subtext0/1
        "accent_red": 5,  # rosewater/flamingo/pink/red/maroon
        "accent_warm": 3,  # peach/yellow/green
        "accent_cool": 5,  # teal/sky/sapphire/blue/lavender
        "accent_bridge": 1,  # mauve
    }

    kept = []

    for role, sub in df.groupby("assigned_catppuccin_role", sort=False):
        sub = sub.copy()

        need = NEED.get(role, 10)
        if len(sub) <= need:
            kept.append(sub)
            continue

        # Structural roles: keep useful extremes by L* (not mid-quantiles)
        if role == "background":
            # keep the darkest tail + a little buffer
            k = max(need, min(60, len(sub)))
            kept.append(
                sub.sort_values(["L", "frequency"], ascending=[True, False]).head(k)
            )

        elif role == "text":
            # keep the lightest tail + a little buffer
            k = max(need, min(60, len(sub)))
            kept.append(
                sub.sort_values(["L", "frequency"], ascending=[False, False]).head(k)
            )

        elif role in {"surface", "overlay"}:
            # keep a broad middle band, but guarantee enough remain
            lo_q, hi_q = (0.10, 0.90) if role == "surface" else (0.15, 0.95)
            lo, hi = sub.L.quantile([lo_q, hi_q])
            mid = sub[(sub.L >= lo) & (sub.L <= hi)]

            # If mid band got too small, fall back to "closest to median L*"
            if len(mid) < need:
                med = float(sub.L.median())
                sub2 = sub.copy()
                sub2["abs_med"] = (sub2.L - med).abs()
                mid = sub2.sort_values(
                    ["abs_med", "frequency"], ascending=[True, False]
                ).drop(columns="abs_med")

            k = max(need, min(80, len(mid)))
            kept.append(mid.sort_values("frequency", ascending=False).head(k))

        else:
            # Accents: keep frequent + L-diverse so combinations exist
            k = max(need * 8, min(120, len(sub)))  # plenty of combinatorics headroom
            sub2 = sub.sort_values("frequency", ascending=False).head(k).copy()

            # ensure L* spread: take top-N, then add farthest-by-L items if needed
            if len(sub2) < need:
                sub2 = sub

            kept.append(sub2)

    out = pd.concat(kept, ignore_index=True)

    # Final safety: enforce minimum per role by topping up from original df if needed
    for role, need in NEED.items():
        have = (out.assigned_catppuccin_role == role).sum()
        if have >= need:
            continue
        pool = df[df.assigned_catppuccin_role == role].copy()
        if pool.empty:
            continue
        add_n = min(need - have, len(pool))
        # Prefer extremes for background/text, otherwise frequency
        if role == "background":
            extra = pool.sort_values("L", ascending=True).head(add_n)
        elif role == "text":
            extra = pool.sort_values("L", ascending=False).head(add_n)
        else:
            extra = pool.sort_values("frequency", ascending=False).head(add_n)

        out = pd.concat([out, extra], ignore_index=True).drop_duplicates(
            subset=[
                "R",
                "G",
                "B",
                "L",
                "a",
                "b",
                "assigned_catppuccin_role",
                "role",
                "frequency",
            ],
            keep="first",
        )

    return out


# ============================================================
# Rich visualization
# ============================================================


def render_role_strips(df, title):
    console = Console()
    table = Table(title=title, show_header=True, header_style="bold")

    table.add_column("Role", style="cyan", no_wrap=True)
    table.add_column("Count", justify="right")
    table.add_column("Colors")

    role_order = df.groupby("assigned_catppuccin_role")["L"].mean().sort_values().index

    for role in role_order:
        sub = df[df.assigned_catppuccin_role == role].sort_values("L")
        strip = Text()

        for _, r in sub.iterrows():
            hex_color = f"#{int(r.R):02x}{int(r.G):02x}{int(r.B):02x}"
            w = min(40, max(1, int(r.frequency * 300)))
            strip.append(" " * w, style=Style(bgcolor=hex_color))

        table.add_row(role, str(len(sub)), strip)

    console.print(table)


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

    # image role distances
    img_rows = []
    for r1, r2 in itertools.combinations(image_roles, 2):
        v1 = np.array(list(centroids[r1].values()))
        v2 = np.array(list(centroids[r2].values()))
        img_rows.append({"role1": r1, "role2": r2, "distance": np.linalg.norm(v1 - v2)})
    img_mat = build_role_distance_matrix(pd.DataFrame(img_rows))

    # catppuccin role distances
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

    results = []
    for perm in itertools.permutations(CATPPUCCIN_ROLES, len(image_roles)):
        mapping = dict(zip(image_roles, perm))

        if ordering_penalty(image_rank, mapping) > 2:
            continue

        score = (
            matrix_mismatch(img_mat, cat_mat, mapping)
            + ordering_penalty(image_rank, mapping)
            + flexibility_penalty(image_rank, mapping)
        )
        results.append((mapping, score))

    best_map, best_score = sorted(results, key=lambda x: x[1])[0]
    second = sorted(results, key=lambda x: x[1])[1][1]
    confidence = confidence_from_scores(best_score, second)

    assigned = img.copy()
    assigned["assigned_catppuccin_role"] = assigned.role.map(best_map)

    render_role_strips(assigned, "Assigned roles (raw)")

    pruned = prune_colors_by_role(assigned)

    render_role_strips(pruned, "Assigned roles (pruned)")

    pruned.to_csv(out_csv, index=False)

    print(f"\nConfidence: {confidence:.3f}")


if __name__ == "__main__":
    assign_roles()
