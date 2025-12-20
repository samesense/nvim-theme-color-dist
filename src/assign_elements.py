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

MIN_TEXT_BG_DELTA = 35.0


# ============================================================
# Geometry helpers
# ============================================================


def lab(row):
    return np.array([row["L"], row["a"], row["b"]])


def delta_e(a, b):
    return np.linalg.norm(lab(a) - lab(b))


def build_catppuccin_element_distances(df):
    dist = {}
    for _, r in df.iterrows():
        a, b = sorted([r.element1, r.element2])
        dist[(a, b)] = r.distance
    return dist


def infer_element_slots(cat_dist, elements):
    if len(elements) == 1:
        return elements

    n = len(elements)
    mat = np.zeros((n, n))

    for i, a in enumerate(elements):
        for j, b in enumerate(elements):
            if i != j:
                mat[i, j] = cat_dist.get(tuple(sorted([a, b])), 0.0)

    vals, vecs = np.linalg.eig(mat)
    axis = vecs[:, np.argmax(vals.real)].real
    order = np.argsort(axis)

    return [elements[i] for i in order]


# ============================================================
# Readability scoring
# ============================================================


def readability_score(assignments):
    required = ["base", "surface1", "overlay1", "text"]
    for k in required:
        if k not in assignments:
            return -np.inf

    base = assignments["base"]
    text = assignments["text"]

    delta = abs(text["L"] - base["L"])
    score = delta * 2

    chain = [("base", "surface1"), ("surface1", "overlay1"), ("overlay1", "text")]
    for a, b in chain:
        score += abs(assignments[b]["L"] - assignments[a]["L"])

    if delta < MIN_TEXT_BG_DELTA:
        score -= (MIN_TEXT_BG_DELTA - delta) * 4

    return score


# ============================================================
# Structural assignment (bounded, safe)
# ============================================================


def assign_structural_joint(df, cat_dist):
    role_dfs = {
        r: df[df.assigned_catppuccin_role == r].sort_values("L").reset_index(drop=True)
        for r in STRUCTURAL_ROLES
    }

    slot_map = {
        r: infer_element_slots(cat_dist, CATPPUCCIN_ELEMENTS[r])
        for r in STRUCTURAL_ROLES
    }

    # pick up to 5 candidates per role (prevents explosion)
    candidates = {}
    for r, rdf in role_dfs.items():
        if len(rdf) < len(slot_map[r]):
            return None
        step = max(1, len(rdf) // 5)
        candidates[r] = rdf.iloc[::step].head(5)

    best = None
    best_score = -np.inf

    for bg in candidates["background"].itertuples(index=False):
        for txt in candidates["text"].itertuples(index=False):
            if abs(txt.L - bg.L) < MIN_TEXT_BG_DELTA:
                continue

            for surf in candidates["surface"].itertuples(index=False):
                for ov in candidates["overlay"].itertuples(index=False):
                    trial = {}

                    trial.update(dict(zip(slot_map["background"], [bg])))
                    trial.update(dict(zip(slot_map["text"], [txt])))
                    trial.update(dict(zip(slot_map["surface"], [surf])))
                    trial.update(dict(zip(slot_map["overlay"], [ov])))

                    score = readability_score(trial)
                    if score > best_score:
                        best_score = score
                        best = trial

    return best


# ============================================================
# Fallback synthesis (deterministic, safe)
# ============================================================


def synthesize(a, b, alpha):
    return {
        "L": a["L"] * (1 - alpha) + b["L"] * alpha,
        "a": a["a"] * (1 - alpha) + b["a"] * alpha,
        "b": a["b"] * (1 - alpha) + b["b"] * alpha,
        "R": int(a["R"] * (1 - alpha) + b["R"] * alpha),
        "G": int(a["G"] * (1 - alpha) + b["G"] * alpha),
        "B": int(a["B"] * (1 - alpha) + b["B"] * alpha),
    }


def derive_structural_fallback(df):
    bg = (
        df[df.assigned_catppuccin_role == "background"]
        .sort_values("L")
        .iloc[1]
        .to_dict()
    )

    txt = df[df.assigned_catppuccin_role == "text"].sort_values("L").iloc[-1].to_dict()

    if abs(txt["L"] - bg["L"]) < MIN_TEXT_BG_DELTA:
        txt = synthesize(bg, txt, 0.85)

    surface = synthesize(bg, txt, 0.35)
    overlay = synthesize(bg, txt, 0.6)

    return {
        "base": bg,
        "surface1": surface,
        "overlay1": overlay,
        "text": txt,
    }


# ============================================================
# Accent assignment (after structure)
# ============================================================


def assign_accents(df, assignments):
    for role in ACCENT_ROLES:
        role_df = df[df.assigned_catppuccin_role == role]
        if role_df.empty:
            continue

        slots = CATPPUCCIN_ELEMENTS[role]
        role_df = role_df.sort_values("frequency", ascending=False).head(40)

        if len(role_df) < len(slots):
            continue

        best = None
        best_score = -np.inf

        for rows in itertools.combinations(role_df.to_dict("records"), len(slots)):
            score = 0.0
            for a, b in itertools.combinations(rows, 2):
                score += delta_e(a, b)

            for r in rows:
                score -= 0.3 * delta_e(r, assignments["text"])
                score -= 0.2 * delta_e(r, assignments["base"])

            if score > best_score:
                best_score = score
                best = rows

        if best:
            assignments.update(dict(zip(slots, best)))

    return assignments


# ============================================================
# CLI
# ============================================================


@click.command()
@click.argument("image_colors_csv", type=click.Path(exists=True))
@click.argument("role_assignment_csv", type=click.Path(exists=True))
@click.argument("catppuccin_distances_csv", type=click.Path(exists=True))
@click.option("--out-lua", default="theme.lua")
@click.option("--theme-name", default="painting_light")
def assign_elements(
    image_colors_csv, role_assignment_csv, catppuccin_distances_csv, out_lua, theme_name
):
    colors = pd.read_csv(image_colors_csv)
    roles = pd.read_csv(role_assignment_csv)

    df = colors.merge(
        roles,
        left_on="role",
        right_on="image_role",
        how="inner",
    )

    assignments = assign_structural_joint(df, None)
    if assignments is None:
        print("⚠️ No readable structural theme found — using fallback synthesis")
        assignments = derive_structural_fallback(df)

    assignments = assign_accents(df, assignments)

    with open(out_lua, "w") as f:
        f.write(f"local {theme_name} = {{\n")
        for role in ROLE_ORDER:
            for elem in CATPPUCCIN_ELEMENTS[role]:
                row = assignments.get(elem)
                if row:
                    f.write(
                        f"  {elem} = '#{int(row['R']):02x}{int(row['G']):02x}{int(row['B']):02x}',\n"
                    )
        f.write("}\n\nreturn " + theme_name + "\n")


if __name__ == "__main__":
    assign_elements()
