import itertools
import math

import click
import numpy as np
import pandas as pd

# ============================================================
# Accent role definitions
# ============================================================

ACCENT_ROLES = {
    "accent_red": ["rosewater", "flamingo", "pink", "red", "maroon"],
    "accent_warm": ["peach", "yellow", "green"],
    "accent_cool": ["teal", "sky", "sapphire", "blue", "lavender"],
    "accent_bridge": ["mauve"],
}

# ============================================================
# Constraints
# ============================================================

ACCENT_TEXT_GAP = 20.0  # must sit below text
ACCENT_OVERLAY_GAP = 5.0  # must sit above overlay
ACCENT_IDEAL_OFFSET = 30.0  # ideal L* below text
ACCENT_SOFT_WIDTH = 12.0
ACCENT_SOFT_WEIGHT = 0.5

MAX_CANDIDATES = 120

# ============================================================
# Color helpers
# ============================================================


def lab(row):
    return np.array([row["L"], row["a"], row["b"]])


def delta_e(a, b):
    return np.linalg.norm(lab(a) - lab(b))


def rgb_to_hex(r):
    return f"#{int(r['R']):02x}{int(r['G']):02x}{int(r['B']):02x}"


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


# ============================================================
# Retinting (LAST RESORT)
# ============================================================


def retint_color(row, target_L):
    """
    Retint by adjusting L* only, preserving hue/chroma.
    """
    r = row.copy()
    r["L"] = target_L
    r["_retinted"] = True
    return r


# ============================================================
# Accent assignment
# ============================================================


def assign_accents(df, structural):
    """
    df: role_colors.csv dataframe (ALL image colors)
    structural: dict with keys base/surface1/overlay1/text
    """

    base_L = float(structural["base"]["L"])
    overlay_L = float(structural["overlay1"]["L"])
    text_L = float(structural["text"]["L"])

    band_lo = overlay_L + ACCENT_OVERLAY_GAP
    band_hi = text_L - ACCENT_TEXT_GAP
    ideal_L = text_L - ACCENT_IDEAL_OFFSET

    used_idxs = {
        structural[k].get("_idx") for k in structural if "_idx" in structural[k]
    }

    accents = {}

    # Work from all image colors
    pool = df.copy()
    pool = pool.reset_index().rename(columns={"index": "_idx"})

    for role, elements in ACCENT_ROLES.items():
        needed = len(elements)

        # Filter feasible candidates
        cand = pool[
            (pool["_idx"].isin(used_idxs) == False)
            & (pool["L"] >= band_lo)
            & (pool["L"] <= band_hi)
        ].copy()

        if "frequency" in cand.columns:
            cand = cand.sort_values("frequency", ascending=False)

        cand = cand.head(MAX_CANDIDATES)

        best = None
        best_score = -np.inf

        # Try real image colors first
        for rows in itertools.combinations(cand.to_dict("records"), needed):
            score = 0.0

            for a, b in itertools.combinations(rows, 2):
                score += delta_e(a, b)

            for r in rows:
                score -= 0.3 * abs(r["L"] - ideal_L)
                score -= 0.2 * delta_e(r, structural["text"])
                score -= 0.2 * delta_e(r, structural["base"])

            if score > best_score:
                best_score = score
                best = rows

        # If no valid image-only solution → retint
        if best is None:
            retinted = []
            for i in range(needed):
                src = pool.iloc[i % len(pool)].to_dict()
                target_L = clamp(
                    ideal_L + (i - needed / 2) * 6,
                    band_lo + 2,
                    band_hi - 2,
                )
                retinted.append(retint_color(src, target_L))
            best = retinted

        for elem, row in zip(elements, best):
            accents[elem] = row
            used_idxs.add(row.get("_idx"))

    return accents


# ============================================================
# CLI
# ============================================================


@click.command()
@click.argument("role_colors_csv", type=click.Path(exists=True))
@click.argument("structural_json", type=click.Path(exists=True))
@click.argument("out_csv", type=click.Path())
def main(role_colors_csv, structural_json, out_csv):
    df = pd.read_csv(role_colors_csv)

    import json

    with open(structural_json) as f:
        structural = json.load(f)

    accents = assign_accents(df, structural)

    out = df.copy()
    out["assigned_catppuccin_role"] = out.get("assigned_catppuccin_role", None)

    for elem, row in accents.items():
        r = row.copy()
        r["assigned_catppuccin_role"] = elem
        out = pd.concat([out, pd.DataFrame([r])], ignore_index=True)

    out.to_csv(out_csv, index=False)


if __name__ == "__main__":
    main()
