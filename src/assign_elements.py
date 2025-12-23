"""
select_final_palette.py

Pick a full 16-color Catppuccin-style palette (all elements, all distinct)
from a role-aware candidate pool produced by extract_colors.py.

Input CSV is expected to be the *pool* output (one row per eligible role):
  columns: R,G,B,L,a,b,frequency,chroma,hue,role,score
(Extra columns are fine.)

This script:
- picks structural UI colors (base/surface1/overlay1/text) with hard constraints
- fills in remaining UI elements (mantle/crust, surface0/2, overlay0/2, subtexts)
- picks accents per group (accent_red/warm/cool + bridge) with distinct colors
- outputs:
  - JSON mapping element -> #rrggbb
  - Lua palette file compatible with your theme generator
  - Rich preview table

Notes:
- No clustering. Selection is constrained + scored.
- Uses beam-search-ish local search for accents (small combinatorics).
"""

from __future__ import annotations

import itertools
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import click
import numpy as np
import pandas as pd
from rich.console import Console
from rich.style import Style
from rich.table import Table
from rich.text import Text

# ============================================================
# Catppuccin element structure (must assign all 16)
# ============================================================

CATPPUCCIN_ELEMENTS: Dict[str, List[str]] = {
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

# Write order for Lua output (your previous ordering)
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

# ============================================================
# Structural constraints (tuned like old script)
# ============================================================

MIN_TEXT_BG_DELTA = 35.0
MIN_UI_BG_DELTA = 25.0
MIN_SURFACE_BG_DELTA = 15.0
MIN_OVERLAY_SURFACE_DELTA = 10.0
MIN_TEXT_OVERLAY_DELTA = 20.0

RELAX_OVERLAY_SURFACE_DELTA = 6.0
RELAX_TEXT_OVERLAY_DELTA = 15.0

# Accents
ACCENT_TEXT_GAP = 20.0
ACCENT_IDEAL_OFFSET = 30.0
ACCENT_SOFT_WIDTH = 12.0
ACCENT_SOFT_WEIGHT = 0.5

# ============================================================
# Helpers
# ============================================================


def _hex_from_rgb(r: int, g: int, b: int) -> str:
    return f"#{int(r):02x}{int(g):02x}{int(b):02x}"


def _hex(row: dict) -> str:
    return _hex_from_rgb(row["R"], row["G"], row["B"])


def lab_vec(row: dict) -> np.ndarray:
    return np.array([float(row["L"]), float(row["a"]), float(row["b"])], dtype=float)


def delta_e(a: dict, b: dict) -> float:
    return float(np.linalg.norm(lab_vec(a) - lab_vec(b)))


def ensure_columns(df: pd.DataFrame, cols: Iterable[str]):
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise click.ClickException(f"Missing required columns: {', '.join(missing)}")


def attach_color_id(df: pd.DataFrame) -> pd.DataFrame:
    """Stable ID used to enforce distinctness across elements/roles."""
    df = df.copy()
    df["color_hex"] = df.apply(lambda r: _hex_from_rgb(r.R, r.G, r.B), axis=1)
    return df


def _with_idx(series: pd.Series) -> dict:
    d = series.to_dict()
    d["_idx"] = int(series.name)
    # also carry a color_id that survives reset_index
    if "color_hex" in d:
        d["_color_id"] = d["color_hex"]
    else:
        d["_color_id"] = _hex_from_rgb(d["R"], d["G"], d["B"])
    return d


# ============================================================
# Structural invariant checks
# ============================================================


def _struct_ok(bg: dict, surface: dict, overlay: dict, text: dict) -> bool:
    return (
        (text["L"] - bg["L"] >= MIN_TEXT_BG_DELTA)
        and (surface["L"] - bg["L"] >= MIN_SURFACE_BG_DELTA)
        and (overlay["L"] - bg["L"] >= MIN_UI_BG_DELTA)
        and (overlay["L"] - surface["L"] >= MIN_OVERLAY_SURFACE_DELTA)
        and (text["L"] - overlay["L"] >= MIN_TEXT_OVERLAY_DELTA)
        and (bg["L"] < surface["L"] < overlay["L"] < text["L"])
    )


def _struct_ok_relaxed(bg: dict, surface: dict, overlay: dict, text: dict) -> bool:
    return (
        (text["L"] - bg["L"] >= MIN_TEXT_BG_DELTA)
        and (overlay["L"] - bg["L"] >= MIN_UI_BG_DELTA)
        and (overlay["L"] - surface["L"] >= RELAX_OVERLAY_SURFACE_DELTA)
        and (text["L"] - overlay["L"] >= RELAX_TEXT_OVERLAY_DELTA)
        and (bg["L"] < surface["L"] < overlay["L"] < text["L"])
    )


def debug_structural(assignments: dict, label: str):
    b = assignments["base"]
    s = assignments["surface1"]
    o = assignments["overlay1"]
    t = assignments["text"]

    print(f"\n=== {label} ===")
    print(f"base     L* = {b['L']:6.1f}")
    print(f"surface  L* = {s['L']:6.1f}   Δsurface-base = {s['L']-b['L']:5.1f}")
    print(f"overlay  L* = {o['L']:6.1f}   Δoverlay-base = {o['L']-b['L']:5.1f}")
    print(f"text     L* = {t['L']:6.1f}   Δtext-base    = {t['L']-b['L']:5.1f}")
    print(f"overlay-surface Δ = {o['L']-s['L']:5.1f}")
    print(f"text-overlay    Δ = {t['L']-o['L']:5.1f}")


# ============================================================
# Candidate pools
# ============================================================


def top_pool(
    df: pd.DataFrame, role: str, k: int, used_color_ids: set[str]
) -> pd.DataFrame:
    sub = df[df["role"] == role].copy()
    if sub.empty:
        return sub
    # Filter already-used colors globally
    sub = sub.loc[~sub["color_hex"].isin(used_color_ids)]
    # Prefer high score, then frequency, then “interestingness”
    sort_cols = [c for c in ["score", "frequency", "chroma"] if c in sub.columns]
    if sort_cols:
        sub = sub.sort_values(sort_cols, ascending=[False] * len(sort_cols))
    return sub.head(k)


# ============================================================
# Structural pick: choose base/surface1/overlay1/text
# ============================================================


def pick_structural(pool: pd.DataFrame) -> dict:
    bg_pool = (
        pool[pool.role == "background"]
        .copy()
        .sort_values(["L", "score"], ascending=[True, False])
    )
    text_pool = (
        pool[pool.role == "text"]
        .copy()
        .sort_values(["L", "score"], ascending=[False, False])
    )
    surface_pool = (
        pool[pool.role == "surface"]
        .copy()
        .sort_values(["L", "score"], ascending=[True, False])
    )
    overlay_pool = (
        pool[pool.role == "overlay"]
        .copy()
        .sort_values(["L", "score"], ascending=[True, False])
    )

    if bg_pool.empty or text_pool.empty or surface_pool.empty or overlay_pool.empty:
        raise RuntimeError("Missing one of background/surface/overlay/text in pool.csv")

    # choose bg from darker quantiles; text from brighter quantiles
    bg_targets = bg_pool["L"].quantile([0.15, 0.20, 0.25]).values
    text_targets = text_pool["L"].quantile([0.90, 0.85, 0.80]).values

    def nearest_k(pool_df: pd.DataFrame, target_L: float, k: int = 12) -> List[dict]:
        # use absolute L distance, but still keep higher score preference by taking a bit more then re-sorting
        d = (pool_df["L"] - target_L).abs()
        idxs = d.nsmallest(min(k, len(pool_df))).index
        sub = pool_df.loc[idxs].copy()
        if "score" in sub.columns:
            sub = sub.sort_values(["score", "frequency"], ascending=[False, False])
        return [_with_idx(sub.loc[i]) for i in sub.index]

    # local search neighborhood
    for bg_L in bg_targets:
        bg_row = bg_pool.iloc[(bg_pool["L"] - bg_L).abs().argsort().iloc[0]]
        bg = _with_idx(bg_row)

        for t_L in text_targets:
            # avoid same exact color
            tc = text_pool.loc[text_pool["color_hex"] != bg["color_hex"]]
            if tc.empty:
                continue

            text_row = tc.iloc[(tc["L"] - t_L).abs().argsort().iloc[0]]
            text = _with_idx(text_row)
            if (text["L"] - bg["L"]) < MIN_TEXT_BG_DELTA:
                continue

            surface_target = (bg["L"] + text["L"]) / 2.0
            surface_cands = nearest_k(surface_pool, surface_target, k=14)

            for surface in surface_cands:
                if surface["color_hex"] in {bg["color_hex"], text["color_hex"]}:
                    continue
                overlay_target = (surface["L"] + text["L"]) / 2.0
                overlay_cands = nearest_k(overlay_pool, overlay_target, k=14)

                for overlay in overlay_cands:
                    if overlay["color_hex"] in {
                        bg["color_hex"],
                        text["color_hex"],
                        surface["color_hex"],
                    }:
                        continue

                    if _struct_ok(bg, surface, overlay, text):
                        return {
                            "base": bg,
                            "surface1": surface,
                            "overlay1": overlay,
                            "text": text,
                        }

                    if _struct_ok_relaxed(bg, surface, overlay, text):
                        return {
                            "base": bg,
                            "surface1": surface,
                            "overlay1": overlay,
                            "text": text,
                        }

    # deterministic fallback, still distinct
    bg = _with_idx(bg_pool.iloc[0])
    text = _with_idx(text_pool[text_pool["color_hex"] != bg["color_hex"]].iloc[0])

    surface_df = surface_pool.loc[
        ~surface_pool["color_hex"].isin({bg["color_hex"], text["color_hex"]})
    ]
    overlay_df = overlay_pool.loc[
        ~overlay_pool["color_hex"].isin({bg["color_hex"], text["color_hex"]})
    ]

    surface = _with_idx(
        surface_df.iloc[
            (surface_df["L"] - (bg["L"] + text["L"]) / 2).abs().argsort().iloc[0]
        ]
    )
    overlay_df2 = overlay_df.loc[~overlay_df["color_hex"].isin({surface["color_hex"]})]
    overlay = _with_idx(
        overlay_df2.iloc[
            (overlay_df2["L"] - (surface["L"] + text["L"]) / 2).abs().argsort().iloc[0]
        ]
    )

    return {"base": bg, "surface1": surface, "overlay1": overlay, "text": text}


# ============================================================
# Fill remaining UI elements (mantle/crust etc.)
# ============================================================


def fill_ui_elements(pool: pd.DataFrame, assignments: dict) -> dict:
    used = {assignments[k]["color_hex"] for k in assignments}

    def pick_near(
        role: str, target_L: float, avoid: set[str], topk: int = 120
    ) -> dict | None:
        sub = pool[pool.role == role].copy()
        if sub.empty:
            return None
        sub = sub.loc[~sub["color_hex"].isin(avoid)]
        sub = (
            sub.sort_values(["score", "frequency"], ascending=[False, False])
            .head(topk)
            .copy()
        )
        # rank by L distance then by score
        sub["Ldist"] = (sub["L"] - target_L).abs()
        sub = sub.sort_values(
            ["Ldist", "score", "frequency"], ascending=[True, False, False]
        )
        return _with_idx(sub.iloc[0])

    # background: mantle between base and surface0-ish; crust near base but distinct
    base = assignments["base"]
    surface1 = assignments["surface1"]
    overlay1 = assignments["overlay1"]
    text = assignments["text"]

    # surface0/2 around surface1
    s0 = pick_near("surface", target_L=float(surface1["L"]) - 6.0, avoid=used, topk=160)
    if s0:
        assignments["surface0"] = s0
        used.add(s0["color_hex"])

    s2 = pick_near("surface", target_L=float(surface1["L"]) + 6.0, avoid=used, topk=160)
    if s2:
        assignments["surface2"] = s2
        used.add(s2["color_hex"])

    # overlay0/2 around overlay1
    o0 = pick_near("overlay", target_L=float(overlay1["L"]) - 6.0, avoid=used, topk=160)
    if o0:
        assignments["overlay0"] = o0
        used.add(o0["color_hex"])

    o2 = pick_near("overlay", target_L=float(overlay1["L"]) + 6.0, avoid=used, topk=160)
    if o2:
        assignments["overlay2"] = o2
        used.add(o2["color_hex"])

    # subtext1/0 near text but lower
    st1 = pick_near("text", target_L=float(text["L"]) - 6.0, avoid=used, topk=160)
    if st1:
        assignments["subtext1"] = st1
        used.add(st1["color_hex"])

    st0 = pick_near("text", target_L=float(text["L"]) - 12.0, avoid=used, topk=160)
    if st0:
        assignments["subtext0"] = st0
        used.add(st0["color_hex"])

    # mantle/crust near base, but distinct; mantle slightly higher L than base
    mantle = pick_near(
        "background", target_L=float(base["L"]) + 4.0, avoid=used, topk=200
    )
    if mantle:
        assignments["mantle"] = mantle
        used.add(mantle["color_hex"])

    crust = pick_near(
        "background", target_L=float(base["L"]) - 4.0, avoid=used, topk=200
    )
    if crust:
        assignments["crust"] = crust
        used.add(crust["color_hex"])

    # ensure keys exist even if a role was too sparse
    # fall back by reusing L-nearest from same role (still distinct) with wider search
    def must_have(elem: str, role: str, target_L: float):
        if elem in assignments:
            return
        cand = pick_near(role, target_L=target_L, avoid=used, topk=500)
        if cand is None:
            raise RuntimeError(
                f"Could not fill required element {elem} from role={role}"
            )
        assignments[elem] = cand
        used.add(cand["color_hex"])

    must_have("surface0", "surface", float(surface1["L"]) - 6.0)
    must_have("surface2", "surface", float(surface1["L"]) + 6.0)
    must_have("overlay0", "overlay", float(overlay1["L"]) - 6.0)
    must_have("overlay2", "overlay", float(overlay1["L"]) + 6.0)
    must_have("subtext1", "text", float(text["L"]) - 6.0)
    must_have("subtext0", "text", float(text["L"]) - 12.0)
    must_have("mantle", "background", float(base["L"]) + 4.0)
    must_have("crust", "background", float(base["L"]) - 4.0)

    return assignments


# ============================================================
# Accent picking (distinct, role-wise)
# ============================================================


def pick_accents(pool: pd.DataFrame, assignments: dict) -> dict:
    text_L = float(assignments["text"]["L"])
    overlay_L = float(assignments["overlay1"]["L"])
    ideal_L = text_L - ACCENT_IDEAL_OFFSET

    used_color_ids = {v["color_hex"] for v in assignments.values()}

    for role in ACCENT_ROLES:
        sub = pool[pool.role == role].copy()
        if sub.empty:
            continue

        elems = CATPPUCCIN_ELEMENTS[role]

        # filter unused, take top N by score/frequency
        sub = sub.loc[~sub["color_hex"].isin(used_color_ids)]
        sub = sub.sort_values(["score", "frequency"], ascending=[False, False]).head(80)

        if len(sub) < len(elems):
            raise RuntimeError(
                f"Not enough candidates for {role}: need {len(elems)}, have {len(sub)}"
            )

        best_rows = None
        best_score = -float("inf")

        # combinations can blow up: limit candidate set further for large groups
        cand_list = sub.to_dict("records")
        if len(elems) >= 5 and len(cand_list) > 45:
            cand_list = cand_list[:45]
        if len(elems) == 3 and len(cand_list) > 60:
            cand_list = cand_list[:60]

        for rows in itertools.combinations(cand_list, len(elems)):
            # distinctness
            row_hexes = [r["color_hex"] for r in rows]
            if len(set(row_hexes)) != len(row_hexes):
                continue
            if any(h in used_color_ids for h in row_hexes):
                continue

            # L gating: avoid too close to text or too dark (below overlay)
            if any(r["L"] > text_L - 5 or r["L"] < overlay_L + 5 for r in rows):
                continue

            score = 0.0

            # encourage separation within the group
            for a, b in itertools.combinations(rows, 2):
                score += delta_e(a, b)

            # encourage popularity + respect "score" from pool
            for r in rows:
                score += 0.6 * float(r.get("score", 0.0))
                score += 2.0 * float(r.get("frequency", 0.0))

                # stay away from text/background in Lab (readability / UI cohesion)
                score -= 0.30 * delta_e(r, assignments["text"])
                score -= 0.20 * delta_e(r, assignments["base"])

                # hard: keep accent away from text by L
                if r["L"] > text_L - ACCENT_TEXT_GAP:
                    score -= 100.0

                # soft: prefer a band below text
                dist = abs(float(r["L"]) - ideal_L)
                score -= (dist / ACCENT_SOFT_WIDTH) ** 2 * ACCENT_SOFT_WEIGHT

            if score > best_score:
                best_score = score
                best_rows = rows

        if best_rows is None:
            raise RuntimeError(f"Failed to choose distinct accents for {role}")

        # assign in a stable order: sort by hue to look nice (optional), but keep deterministic
        chosen = list(best_rows)
        # If hue exists, sort by hue for nicer spread within group
        if all("hue" in r for r in chosen):
            chosen = sorted(chosen, key=lambda r: float(r["hue"]))

        assignments.update(dict(zip(elems, chosen)))
        used_color_ids.update(r["color_hex"] for r in chosen)

    # ensure bridge exists
    if "mauve" not in assignments:
        role = "accent_bridge"
        sub = pool[pool.role == role].copy()
        sub = sub.loc[
            ~sub["color_hex"].isin({v["color_hex"] for v in assignments.values()})
        ]
        sub = sub.sort_values(["score", "frequency"], ascending=[False, False]).head(30)
        if sub.empty:
            raise RuntimeError("Missing accent_bridge candidates for mauve")
        assignments["mauve"] = sub.iloc[0].to_dict()

    return assignments


# ============================================================
# Rich preview
# ============================================================


def render_elements(assignments: dict, theme_name: str):
    console = Console()
    table = Table(title=theme_name, show_header=True, header_style="bold")

    table.add_column("Element", style="cyan")
    table.add_column("Hex")
    table.add_column("Swatch")
    table.add_column("L*")
    table.add_column("Chroma", justify="right")
    table.add_column("Hue", justify="right")

    def swatch(h: str) -> Text:
        return Text("      ", style=Style(bgcolor=h))

    # display in canonical catppuccin order
    ordered_elements = []
    for role in ROLE_ORDER:
        ordered_elements.extend(CATPPUCCIN_ELEMENTS[role])

    for elem in ordered_elements:
        row = assignments.get(elem)
        if row is None:
            continue
        h = _hex(row)
        table.add_row(
            elem,
            h,
            swatch(h),
            f"{float(row['L']):.1f}",
            f"{float(row.get('chroma', np.nan)):.1f}" if "chroma" in row else "",
            f"{float(row.get('hue', np.nan)):.0f}°" if "hue" in row else "",
        )

    console.print(table)


# ============================================================
# Output writers
# ============================================================


def write_lua(assignments: dict, out_lua: Path, theme_name: str):
    with out_lua.open("w") as f:
        f.write(f"local {theme_name} = {{\n")
        for role in ROLE_ORDER:
            for elem in CATPPUCCIN_ELEMENTS[role]:
                row = assignments.get(elem)
                if row is None:
                    raise RuntimeError(f"Missing element {elem} in final assignments")
                f.write(f"  {elem} = '{_hex(row)}',\n")
        f.write("}\n")
        f.write(f"\nreturn {theme_name}\n")


def write_json(assignments: dict, out_json: Path, theme_name: str):
    ordered = {}
    for role in ROLE_ORDER:
        for elem in CATPPUCCIN_ELEMENTS[role]:
            row = assignments.get(elem)
            if row is None:
                raise RuntimeError(f"Missing element {elem} in final assignments")
            ordered[elem] = _hex(row)
    out_json.write_text(
        json.dumps({"name": theme_name, "palette": ordered}, indent=2) + "\n"
    )


# ============================================================
# CLI
# ============================================================


@click.command()
@click.argument(
    "color_pool_csv", type=click.Path(exists=True, dir_okay=False, path_type=Path)
)
@click.option("--theme-name", default="painting", show_default=True)
@click.option(
    "--out-lua",
    type=click.Path(dir_okay=False, path_type=Path),
    default=Path("theme.lua"),
    show_default=True,
)
@click.option(
    "--out-json",
    type=click.Path(dir_okay=False, path_type=Path),
    default=Path("theme.json"),
    show_default=True,
)
@click.option(
    "--seed",
    type=int,
    default=0,
    show_default=True,
    help="Seed for any randomized steps (future-proof).",
)
def main(
    color_pool_csv: Path, theme_name: str, out_lua: Path, out_json: Path, seed: int
):
    """
    Pick a complete Catppuccin-style 16-color palette from a role-aware color pool.

    COLOR_POOL_CSV: output from extract_colors.py (role-aware pool)
    """
    np.random.seed(seed)

    df = pd.read_csv(color_pool_csv)
    ensure_columns(df, ["R", "G", "B", "L", "a", "b", "frequency", "role"])
    if "score" not in df.columns:
        df["score"] = df["frequency"]

    df = attach_color_id(df)

    # Structural
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
            raise RuntimeError(
                "Rejected palette: no readable structural configuration found"
            )

    debug_structural(assignments, "FINAL STRUCTURAL ASSIGNMENT")

    # Fill remaining UI (ensure all distinct)
    assignments = fill_ui_elements(df, assignments)

    # Accents (ensure all distinct)
    assignments = pick_accents(df, assignments)

    # Sanity: ensure all 16 present and distinct
    all_elems = [e for role in ROLE_ORDER for e in CATPPUCCIN_ELEMENTS[role]]
    missing = [e for e in all_elems if e not in assignments]
    if missing:
        raise RuntimeError(f"Missing elements in final palette: {missing}")

    hexes = [assignments[e]["color_hex"] for e in all_elems]
    if len(set(hexes)) != len(hexes):
        raise RuntimeError("Final palette has duplicate colors (distinctness violated)")

    # Output
    render_elements(assignments, theme_name)
    write_lua(assignments, out_lua, theme_name)
    write_json(assignments, out_json, theme_name)

    print(f"\n✓ Wrote {out_lua}")
    print(f"✓ Wrote {out_json}")


if __name__ == "__main__":
    main()
