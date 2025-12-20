import itertools

import click
import numpy as np
import pandas as pd

# ============================================================
# Catppuccin element definitions
# ============================================================

CATPPUCCIN_ELEMENTS = {
    "background": ["base", "mantle", "crust"],
    "surface": ["surface2", "surface1", "surface0"],
    "overlay": ["overlay2", "overlay1", "overlay0"],
    "text": ["text", "subtext1", "subtext0"],
    "accent_red": ["rosewater", "flamingo", "pink", "red", "maroon"],
    "accent_warm": ["peach", "yellow", "green"],
    "accent_cool": ["teal", "sky", "sapphire", "blue", "lavender"],
    "accent_bridge": ["mauve"],
}

ROLE_ORDER = [
    "accent_red",
    "accent_warm",
    "accent_cool",
    "accent_bridge",
    "text",
    "overlay",
    "surface",
    "background",
]


def lab(row):
    return np.array([row.L, row.a, row.b])


def delta_e(a, b):
    return np.linalg.norm(lab(a) - lab(b))


def build_catppuccin_element_distances(df):
    """
    {(elem1, elem2): ΔE}
    """
    dist = {}
    for _, r in df.iterrows():
        a, b = sorted([r.element1, r.element2])
        dist[(a, b)] = r.distance
    return dist


# ============================================================
# Element geometry inference (NEW)
# ============================================================


def infer_element_slots(cat_dist, elements):
    """
    Infer relative ordering of elements using Catppuccin geometry.
    Returns ordered list of elements from darkest → lightest.
    """
    if len(elements) == 1:
        return elements

    # Build pairwise distance matrix
    names = elements
    mat = np.zeros((len(names), len(names)))

    for i, a in enumerate(names):
        for j, b in enumerate(names):
            if i == j:
                continue
            mat[i, j] = cat_dist.get(tuple(sorted([a, b])), 0)

    # Use first principal axis as ordering proxy
    eigvals, eigvecs = np.linalg.eig(mat)
    axis = eigvecs[:, np.argmax(eigvals.real)].real

    order = np.argsort(axis)
    return [names[i] for i in order]


# ============================================================
# Assignment logic
# ============================================================


def assign_structural(role_df, slots):
    """
    Assign colors to structural slots preserving lightness order.
    """
    role_df = role_df.sort_values("L").reset_index(drop=True)

    if len(role_df) < len(slots):
        return None

    idxs = np.linspace(0, len(role_df) - 1, len(slots)).round().astype(int)
    return dict(zip(slots, role_df.iloc[idxs].itertuples()))


def assign_accents(role_df, slots):
    """
    Assign accents jointly by frequency + separation.
    """
    role_df = role_df.sort_values("frequency", ascending=False)

    # Prefilter: keep only the top-N most frequent candidates to avoid
    # combinatorial explosion when searching combinations.
    TOP_N_CANDIDATES = 40
    if len(role_df) > TOP_N_CANDIDATES:
        role_df = role_df.head(TOP_N_CANDIDATES)

    if len(role_df) < len(slots):
        return None

    best = None
    best_score = -np.inf

    for rows in itertools.combinations(role_df.itertuples(), len(slots)):
        score = 0
        for a, b in itertools.combinations(rows, 2):
            score += delta_e(a, b)
        if score > best_score:
            best_score = score
            best = rows

    return dict(zip(slots, best))


# ============================================================
# Global readability score
# ============================================================


def readability_score(assignments):
    """
    Higher = better
    """
    base = assignments["base"]
    text = assignments["text"]

    score = abs(text.L - base.L) * 2

    for a, b in [("base", "surface1"), ("surface1", "overlay1"), ("overlay1", "text")]:
        if a in assignments and b in assignments:
            score += abs(assignments[b].L - assignments[a].L)

    # Hard penalties
    if abs(text.L - base.L) < 35:
        score -= 100

    return score


@click.command()
@click.argument("image_colors_csv", type=click.Path(exists=True))
@click.argument("role_assignment_csv", type=click.Path(exists=True))
@click.argument("catppuccin_distances_csv", type=click.Path(exists=True))
@click.option("--out-lua", default="theme.lua")
@click.option("--theme-name", default="painting_light")
def assign_elements(
    image_colors_csv,
    role_assignment_csv,
    catppuccin_distances_csv,
    out_lua,
    theme_name,
):
    colors = pd.read_csv(image_colors_csv)
    roles = pd.read_csv(role_assignment_csv)
    cat = pd.read_csv(catppuccin_distances_csv)

    cat_dist = build_catppuccin_element_distances(cat)

    df = colors.merge(
        roles,
        left_on="role",
        right_on="image_role",
        how="inner",
    )

    best = None
    best_score = -np.inf

    assignments = {}

    for role, elements in CATPPUCCIN_ELEMENTS.items():
        print("here", role)
        role_df = df[df.assigned_catppuccin_role == role]
        slots = infer_element_slots(cat_dist, elements)

        if role in {"background", "surface", "overlay", "text"}:
            part = assign_structural(role_df, slots)
        else:
            part = assign_accents(role_df, slots)

        if part is None:
            continue

        assignments.update(part)

    score = readability_score(assignments)

    if score < 0:
        raise RuntimeError("Theme rejected: unreadable")

    # --------------------------------------------------------
    # Write Lua
    # --------------------------------------------------------

    with open(out_lua, "w") as f:
        f.write(f"local {theme_name} = {{\n")
        for role in ROLE_ORDER:
            for elem in CATPPUCCIN_ELEMENTS[role]:
                row = assignments.get(elem)
                if row is None:
                    continue
                f.write(
                    f"  {elem} = '#{int(row.R):02x}{int(row.G):02x}{int(row.B):02x}',\n"
                )
        f.write("}\n\n")


if __name__ == "__main__":
    assign_elements()
