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

STRUCTURAL_ROLES = ["background", "surface", "overlay", "text"]
ACCENT_ROLES = ["accent_red", "accent_warm", "accent_cool", "accent_bridge"]

# ============================================================
# Geometry helpers
# ============================================================


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


def infer_element_slots(cat_dist, elements):
    """
    Infer relative ordering of elements (dark → light)
    using Catppuccin ΔE geometry.
    """
    if len(elements) == 1:
        return elements

    names = elements
    mat = np.zeros((len(names), len(names)))

    for i, a in enumerate(names):
        for j, b in enumerate(names):
            if i == j:
                continue
            mat[i, j] = cat_dist.get(tuple(sorted([a, b])), 0.0)

    eigvals, eigvecs = np.linalg.eig(mat)
    axis = eigvecs[:, np.argmax(eigvals.real)].real
    order = np.argsort(axis)

    return [names[i] for i in order]


def readability_score(assignments):
    """
    Higher = better readability.
    Returns -inf if required elements are missing.
    """
    REQUIRED = ["base", "surface1", "overlay1", "text"]

    for k in REQUIRED:
        if k not in assignments:
            return -np.inf

    base = assignments["base"]
    text = assignments["text"]

    score = abs(text.L - base.L) * 2

    chain = [
        ("base", "surface1"),
        ("surface1", "overlay1"),
        ("overlay1", "text"),
    ]

    for a, b in chain:
        score += abs(assignments[b].L - assignments[a].L)

    delta = abs(text.L - base.L)
    # Soft penalty instead of rejection
    if delta < 35:
        score -= (35 - delta) * 4

    return score


def assign_structural_joint(df, cat_dist):
    """
    Jointly assign background, surface, overlay, text.
    """
    role_dfs = {
        r: df[df.assigned_catppuccin_role == r].sort_values("L").reset_index(drop=True)
        for r in STRUCTURAL_ROLES
    }

    slot_map = {
        r: infer_element_slots(cat_dist, CATPPUCCIN_ELEMENTS[r])
        for r in STRUCTURAL_ROLES
    }

    # Candidate indices (evenly spaced, small search)
    idxs = {}
    for r, rdf in role_dfs.items():
        if len(rdf) < len(slot_map[r]):
            return None
        idxs[r] = np.linspace(0, len(rdf) - 1, len(slot_map[r])).round().astype(int)

    best = None
    best_score = -np.inf

    for bg_idxs in itertools.product(idxs["background"], repeat=1):
        bg_rows = role_dfs["background"].iloc[list(bg_idxs)]

        for txt_idxs in itertools.product(idxs["text"], repeat=1):
            txt_rows = role_dfs["text"].iloc[list(txt_idxs)]

            # Early reject
            if abs(txt_rows.iloc[0].L - bg_rows.iloc[0].L) < 35:
                continue

            for surf_idxs in itertools.product(idxs["surface"], repeat=1):
                surf_rows = role_dfs["surface"].iloc[list(surf_idxs)]

                for ov_idxs in itertools.product(idxs["overlay"], repeat=1):
                    ov_rows = role_dfs["overlay"].iloc[list(ov_idxs)]

                    trial = {}

                    valid = True
                    for role, rows in [
                        ("background", bg_rows),
                        ("surface", surf_rows),
                        ("overlay", ov_rows),
                        ("text", txt_rows),
                    ]:
                        slots = slot_map[role]
                        if len(rows) < len(slots):
                            valid = False
                            break

                        trial.update(dict(zip(slots, rows.itertuples())))

                    if not valid:
                        continue

                    score = readability_score(trial)

                    if score > best_score:
                        best_score = score
                        best = trial

    return best


# ============================================================
# Accent assignment (AFTER structure)
# ============================================================


def assign_accents(df, cat_dist, assignments):
    for role in ACCENT_ROLES:
        role_df = df[df.assigned_catppuccin_role == role]
        if role_df.empty:
            continue

        slots = infer_element_slots(cat_dist, CATPPUCCIN_ELEMENTS[role])

        role_df = role_df.sort_values("frequency", ascending=False)
        role_df = role_df.head(40)

        if len(role_df) < len(slots):
            continue

        best = None
        best_score = -np.inf

        for rows in itertools.combinations(role_df.itertuples(), len(slots)):
            score = 0.0
            for a, b in itertools.combinations(rows, 2):
                score += delta_e(a, b)

            # Penalize accents close to text/background
            for r in rows:
                score -= 0.3 * delta_e(r, assignments["text"])
                score -= 0.2 * delta_e(r, assignments["base"])

            if score > best_score:
                best_score = score
                best = rows

        if best:
            assignments.update(dict(zip(slots, best)))

    return assignments


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

    assignments = assign_structural_joint(df, cat_dist)
    if assignments is None:
        best = assignments
        # raise RuntimeError("No readable structural theme found")

    assignments = assign_accents(df, cat_dist, assignments)

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
        f.write(f"return {theme_name}\n")


if __name__ == "__main__":
    assign_elements()
