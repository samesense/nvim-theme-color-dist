import itertools

import click
import numpy as np
import pandas as pd
from rich.console import Console
from rich.style import Style
from rich.table import Table
from rich.text import Text

# ============================================================
# Constants
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

ACCENT_ROLES = ["accent_red", "accent_warm", "accent_cool", "accent_bridge"]

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

# --- HARD STRUCTURAL CONSTRAINTS ---
MIN_TEXT_BG_DELTA = 35.0
MIN_UI_BG_DELTA = 25.0
MIN_SURFACE_BG_DELTA = 15.0
MIN_OVERLAY_SURFACE_DELTA = 10.0
MIN_TEXT_OVERLAY_DELTA = 20.0

# --- RELAXED CONSTRAINTS (Tier 2) ---
RELAX_OVERLAY_SURFACE_DELTA = 6.0
RELAX_TEXT_OVERLAY_DELTA = 15.0

# --- ACCENTS ---
ACCENT_TEXT_GAP = 20.0
ACCENT_IDEAL_OFFSET = 30.0
ACCENT_SOFT_WIDTH = 12.0
ACCENT_SOFT_WEIGHT = 0.5


# ============================================================
# Geometry helpers
# ============================================================


def lab(row):
    return np.array([row["L"], row["a"], row["b"]])


def delta_e(a, b):
    return np.linalg.norm(lab(a) - lab(b))


def _hex(row):
    return f"#{int(row['R']):02x}{int(row['G']):02x}{int(row['B']):02x}"


def _with_idx(series):
    d = series.to_dict()
    d["_idx"] = series.name
    return d


# ============================================================
# Structural invariant checks
# ============================================================


def _struct_ok(bg, surface, overlay, text):
    return (
        (text["L"] - bg["L"] >= MIN_TEXT_BG_DELTA)
        and (surface["L"] - bg["L"] >= MIN_SURFACE_BG_DELTA)
        and (overlay["L"] - bg["L"] >= MIN_UI_BG_DELTA)
        and (overlay["L"] - surface["L"] >= MIN_OVERLAY_SURFACE_DELTA)
        and (text["L"] - overlay["L"] >= MIN_TEXT_OVERLAY_DELTA)
        and (bg["L"] < surface["L"] < overlay["L"] < text["L"])
    )


def _struct_ok_relaxed(bg, surface, overlay, text):
    return (
        (text["L"] - bg["L"] >= MIN_TEXT_BG_DELTA)
        and (overlay["L"] - bg["L"] >= MIN_UI_BG_DELTA)
        and (overlay["L"] - surface["L"] >= RELAX_OVERLAY_SURFACE_DELTA)
        and (text["L"] - overlay["L"] >= RELAX_TEXT_OVERLAY_DELTA)
        and (bg["L"] < surface["L"] < overlay["L"] < text["L"])
    )


# ============================================================
# Debugging
# ============================================================


def debug_structural(assignments, label):
    print(f"\n=== {label} ===")
    b = assignments["base"]
    s = assignments["surface1"]
    o = assignments["overlay1"]
    t = assignments["text"]

    print(f"base     L* = {b['L']:6.1f}")
    print(f"surface  L* = {s['L']:6.1f}   Δsurface-base = {s['L']-b['L']:5.1f}")
    print(f"overlay  L* = {o['L']:6.1f}   Δoverlay-base = {o['L']-b['L']:5.1f}")
    print(f"text     L* = {t['L']:6.1f}   Δtext-base    = {t['L']-b['L']:5.1f}")
    print(f"overlay-surface Δ = {o['L']-s['L']:5.1f}")
    print(f"text-overlay    Δ = {t['L']-o['L']:5.1f}")


# ============================================================
# Initial structural pick (unchanged logic)
# ============================================================


def pick_structural(df):
    bg_pool = df[df.assigned_catppuccin_role == "background"].copy().sort_values("L")
    text_pool = (
        df[df.assigned_catppuccin_role == "text"]
        .copy()
        .sort_values("L", ascending=False)
    )

    if bg_pool.empty or text_pool.empty:
        raise RuntimeError("Missing background or text colors")

    bg_targets = bg_pool["L"].quantile([0.15, 0.20, 0.25]).values
    text_targets = text_pool["L"].quantile([0.90, 0.85, 0.80]).values

    for bg_L in bg_targets:
        bg = _with_idx(bg_pool.iloc[(bg_pool["L"] - bg_L).abs().argsort().iloc[0]])

        for t_L in text_targets:
            tc = text_pool.loc[~text_pool.index.isin({bg["_idx"]})]
            if tc.empty:
                continue

            text = _with_idx(tc.iloc[(tc["L"] - t_L).abs().argsort().iloc[0]])
            if abs(text["L"] - bg["L"]) < MIN_TEXT_BG_DELTA:
                continue

            surface_pool = df[df.assigned_catppuccin_role == "surface"].copy()
            overlay_pool = df[df.assigned_catppuccin_role == "overlay"].copy()

            surface_target = (bg["L"] + text["L"]) / 2
            surface = _with_idx(
                surface_pool.iloc[
                    (surface_pool["L"] - surface_target).abs().argsort().iloc[0]
                ]
            )

            overlay_target = (surface["L"] + text["L"]) / 2
            overlay = _with_idx(
                overlay_pool.iloc[
                    (overlay_pool["L"] - overlay_target).abs().argsort().iloc[0]
                ]
            )

            return {
                "base": bg,
                "surface1": surface,
                "overlay1": overlay,
                "text": text,
            }

    # Extreme fallback (still deterministic)
    bg = _with_idx(bg_pool.iloc[0])
    text = _with_idx(text_pool.iloc[0])

    surface_pool = df[df.assigned_catppuccin_role == "surface"]
    overlay_pool = df[df.assigned_catppuccin_role == "overlay"]

    surface = _with_idx(
        surface_pool.iloc[
            (surface_pool["L"] - (bg["L"] + text["L"]) / 2).abs().argsort().iloc[0]
        ]
    )
    overlay = _with_idx(
        overlay_pool.iloc[
            (overlay_pool["L"] - (surface["L"] + text["L"]) / 2).abs().argsort().iloc[0]
        ]
    )

    return {"base": bg, "surface1": surface, "overlay1": overlay, "text": text}


# ============================================================
# Tier-3 fallback: single midtone
# ============================================================


def fallback_single_midtone(assignments, df):
    bg = assignments["base"]
    text = assignments["text"]

    mid_pool = df[df.assigned_catppuccin_role.isin(["surface", "overlay"])].copy()
    mid_pool["bg_sep"] = mid_pool["L"] - bg["L"]
    mid_pool["text_sep"] = text["L"] - mid_pool["L"]

    mid_pool = mid_pool[
        (mid_pool["bg_sep"] >= MIN_UI_BG_DELTA)
        & (mid_pool["text_sep"] >= MIN_TEXT_OVERLAY_DELTA)
    ]

    if mid_pool.empty:
        return None

    mid = mid_pool.sort_values(by=["bg_sep", "text_sep"], ascending=[True, True]).iloc[
        0
    ]

    return {
        "base": bg,
        "surface1": mid.to_dict(),
        "overlay1": mid.to_dict(),
        "text": text,
    }


# ============================================================
# Accent assignment (unchanged)
# ============================================================


def pick_accents(df, assignments):
    text_L = float(assignments["text"]["L"])
    overlay_L = float(assignments["overlay1"]["L"])
    ideal_L = text_L - ACCENT_IDEAL_OFFSET

    used_idxs = {v.get("_idx") for v in assignments.values() if "_idx" in v}

    for role in ACCENT_ROLES:
        sub = df[df.assigned_catppuccin_role == role].copy()
        if sub.empty:
            continue

        elems = CATPPUCCIN_ELEMENTS[role]
        sub = sub.reset_index().rename(columns={"index": "_idx"})
        sub = sub.loc[~sub["_idx"].isin(used_idxs)]
        sub = sub.sort_values("frequency", ascending=False).head(50)

        if len(sub) < len(elems):
            continue

        best = None
        best_score = -np.inf

        for rows in itertools.combinations(sub.to_dict("records"), len(elems)):
            if any(r["_idx"] in used_idxs for r in rows):
                continue

            if any(r["L"] > text_L - 5 or r["L"] < overlay_L + 5 for r in rows):
                continue

            score = sum(delta_e(a, b) for a, b in itertools.combinations(rows, 2))

            for r in rows:
                score -= 0.3 * delta_e(r, assignments["text"])
                score -= 0.2 * delta_e(r, assignments["base"])

                if r["L"] > text_L - ACCENT_TEXT_GAP:
                    score -= 100

                dist = abs(r["L"] - ideal_L)
                score -= (dist / ACCENT_SOFT_WIDTH) ** 2 * ACCENT_SOFT_WEIGHT

            if score > best_score:
                best_score = score
                best = rows

        if best:
            assignments.update(dict(zip(elems, best)))
            used_idxs.update(r["_idx"] for r in best)

    return assignments


# ============================================================
# Rich display
# ============================================================


def render_elements(assignments, theme_name):
    console = Console()
    table = Table(title=theme_name, show_header=True, header_style="bold")

    table.add_column("Element", style="cyan")
    table.add_column("Semantic hex")
    table.add_column("Semantic")
    table.add_column("Final hex")
    table.add_column("Final")
    table.add_column("L*")

    for elem, row in assignments.items():
        h = _hex(row)
        sw = Text("      ", style=Style(bgcolor=h))
        table.add_row(elem, h, sw, h, sw, f"{row['L']:.1f}")

    console.print("\n[bold]Semantic vs Final Theme Colors[/bold]\n")
    console.print(table)


# ============================================================
# CLI
# ============================================================


@click.command()
@click.argument("role_colors_csv", type=click.Path(exists=True))
@click.option("--out-lua", default="theme.lua")
@click.option("--theme-name", default="painting")
def assign_elements(role_colors_csv, out_lua, theme_name):
    df = pd.read_csv(role_colors_csv)

    assignments = pick_structural(df)
    debug_structural(assignments, "PRIMARY STRUCTURAL ASSIGNMENT")

    if not _struct_ok(
        assignments["base"],
        assignments["surface1"],
        assignments["overlay1"],
        assignments["text"],
    ):
        print("⚠️  Tier 1 failed → trying relaxed constraints")

        if not _struct_ok_relaxed(
            assignments["base"],
            assignments["surface1"],
            assignments["overlay1"],
            assignments["text"],
        ):
            print("⚠️  Tier 2 failed → trying single-midtone fallback")
            fb = fallback_single_midtone(assignments, df)
            if fb is None:
                raise RuntimeError(
                    "Rejected palette: no readable structural configuration found"
                )
            assignments = fb

    debug_structural(assignments, "FINAL STRUCTURAL ASSIGNMENT")

    assignments = pick_accents(df, assignments)
    render_elements(assignments, theme_name)

    with open(out_lua, "w") as f:
        f.write(f"local {theme_name} = {{\n")
        for role in ROLE_ORDER:
            for elem in CATPPUCCIN_ELEMENTS[role]:
                row = assignments.get(elem)
                if row:
                    f.write(f"  {elem} = '{_hex(row)}',\n")
        f.write("}\n")


if __name__ == "__main__":
    assign_elements()
