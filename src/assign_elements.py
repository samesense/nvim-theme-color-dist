from __future__ import annotations

import json
from pathlib import Path

import click
import numpy as np
import pandas as pd
from rich.console import Console
from rich.style import Style
from rich.table import Table
from rich.text import Text

# ============================================================
# Catppuccin structure (semantic, fixed)
# ============================================================

ELEMENTS_BY_ROLE = {
    "background": ["base", "mantle", "crust"],
    "surface": ["surface2", "surface1", "surface0"],
    "overlay": ["overlay2", "overlay1", "overlay0"],
    "text": ["text", "subtext1", "subtext0"],
    "accent_red": ["rosewater", "flamingo", "pink", "red", "maroon"],
    "accent_warm": ["peach", "yellow", "green"],
    # Put the "often-used-as-FG" cools first so Include/imports tend to be readable.
    "accent_cool": ["blue", "sapphire", "sky", "lavender", "teal"],
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

ACCENT_ROLES = [
    "accent_red",
    "accent_warm",
    "accent_cool",
    "accent_bridge",
]

# ============================================================
# Helpers
# ============================================================


def hex_from_row(r) -> str:
    return f"#{int(r.R):02x}{int(r.G):02x}{int(r.B):02x}"


def circ_dist(a, b) -> float:
    d = abs(a - b) % 360
    return min(d, 360 - d)


def ensure_rank_columns(pool: pd.DataFrame) -> pd.DataFrame:
    """
    Ensure the pool has the new ranks added by extract_color_pool:
      - deltaE_bg_rank
      - abs_deltaL_bg_rank

    Also normalize a couple legacy column names if present.
    """
    pool = pool.copy()

    # Some earlier versions used slightly different names; normalize if present
    if "abs_deltaL_bg" not in pool.columns and "abs_deltaL" in pool.columns:
        pool["abs_deltaL_bg"] = pool["abs_deltaL"]

    if "deltaE_bg_rank" not in pool.columns:
        if "deltaE_bg" in pool.columns:
            pool["deltaE_bg_rank"] = pool.groupby("role")["deltaE_bg"].rank(
                pct=True, method="average"
            )
        else:
            pool["deltaE_bg_rank"] = np.nan

    if "abs_deltaL_bg_rank" not in pool.columns:
        if "abs_deltaL_bg" in pool.columns:
            pool["abs_deltaL_bg_rank"] = pool.groupby("role")["abs_deltaL_bg"].rank(
                pct=True, method="average"
            )
        else:
            pool["abs_deltaL_bg_rank"] = np.nan

    return pool


# ============================================================
# Constraint accessors
# ============================================================


def deltaL_target(constraints, pair):
    return constraints["deltaL"][pair]["median"]


def deltaL_min(constraints, pair):
    return constraints["deltaL"][pair]["q25"]


def hue_center(constraints, role):
    return constraints["hue"].get(role, {}).get("center")


def hue_width(constraints, role):
    return constraints["hue"].get(role, {}).get("width")


# ============================================================
# Structural selection (required)
# ============================================================


def pick_structural(pool: pd.DataFrame, constraints: dict):
    bg_pool = pool[pool.role == "background"].sort_values("L")
    surf_pool = pool[pool.role == "surface"].sort_values("L")
    over_pool = pool[pool.role == "overlay"].sort_values("L")
    text_pool = pool[pool.role == "text"].sort_values("L", ascending=False)

    best = None
    best_score = float("inf")

    for bg in bg_pool.head(40).itertuples():
        for text in text_pool.head(40).itertuples():
            if text.L - bg.L < deltaL_min(constraints, "background→text"):
                continue

            for surf in surf_pool.itertuples():
                if not (bg.L < surf.L < text.L):
                    continue

                for over in over_pool.itertuples():
                    if not (surf.L < over.L < text.L):
                        continue

                    score = (
                        abs(
                            (text.L - bg.L)
                            - deltaL_target(constraints, "background→text")
                        )
                        + abs(
                            (surf.L - bg.L)
                            - deltaL_target(constraints, "background→surface")
                        )
                        + abs(
                            (over.L - surf.L)
                            - deltaL_target(constraints, "surface→overlay")
                        )
                        + abs(
                            (text.L - over.L)
                            - deltaL_target(constraints, "overlay→text")
                        )
                        - 2.0
                        * (
                            bg.frequency
                            + surf.frequency
                            + over.frequency
                            + text.frequency
                        )
                    )

                    if score < best_score:
                        best_score = score
                        best = {
                            "base": bg,
                            "surface1": surf,
                            "overlay1": over,
                            "text": text,
                        }

    return best or {}


# ============================================================
# Fill remaining UI elements (best effort)
# ============================================================


def fill_ui(pool, assignments):
    used = {hex_from_row(v) for v in assignments.values()}

    def pick(role, target_L):
        sub = pool[(pool.role == role) & (~pool.hex.isin(used))].copy()
        if sub.empty:
            return None
        sub["dist"] = (sub.L - target_L).abs()
        r = sub.sort_values(["dist", "score"], ascending=[True, False]).iloc[0]
        used.add(r.hex)
        return r

    if "base" not in assignments or "surface1" not in assignments:
        return assignments

    base = assignments["base"]
    surf = assignments["surface1"]
    over = assignments.get("overlay1")
    text = assignments.get("text")

    for k, r in {
        "mantle": pick("background", base.L + 4),
        "crust": pick("background", base.L - 4),
        "surface0": pick("surface", surf.L - 6),
        "surface2": pick("surface", surf.L + 6),
        "overlay0": pick("overlay", over.L - 6) if over is not None else None,
        "overlay2": pick("overlay", over.L + 6) if over is not None else None,
        "subtext1": pick("text", text.L - 6) if text is not None else None,
        "subtext0": pick("text", text.L - 12) if text is not None else None,
    }.items():
        if r is not None:
            assignments[k] = r

    return assignments


# ============================================================
# Accent selection (non-fatal, greedy)
# ============================================================


def _apply_hue_window(sub: pd.DataFrame, constraints: dict, role: str) -> pd.DataFrame:
    h0 = hue_center(constraints, role)
    w = hue_width(constraints, role)
    if h0 is None or w is None or sub.empty:
        return sub

    tmp = sub.copy()
    tmp["hue_dist"] = tmp.hue.apply(lambda h: circ_dist(h, h0))
    cand = tmp[tmp.hue_dist <= w / 2]
    return cand if not cand.empty else tmp


def _prefer_fg_safe_cool(
    cand: pd.DataFrame,
    *,
    base_L: float,
    min_dl: float,
    relax_to_positive: bool = True,
) -> pd.DataFrame:
    """
    Prefer cool accents that can be used as foreground on base:
      - hard gate: L >= base_L + min_dl
      - relax: L > base_L (if relax_to_positive)
      - never intentionally prefer "darker than base" for cool FG.
    """
    if cand.empty or "L" not in cand.columns:
        return cand

    strict = cand[cand["L"] >= (base_L + min_dl)]
    if not strict.empty:
        return strict

    if relax_to_positive:
        pos = cand[cand["L"] > base_L]
        if not pos.empty:
            return pos

    return cand


def pick_accents(
    pool: pd.DataFrame,
    assignments: dict,
    constraints: dict,
    *,
    cool_rank_floor: float = 0.60,
    cool_min_deltal: float = 24.0,
):
    used = {hex_from_row(v) for v in assignments.values()}

    base_L = None
    if "base" in assignments:
        base_L = float(
            assignments["base"].L
            if hasattr(assignments["base"], "L")
            else assignments["base"]["L"]
        )

    for role in ACCENT_ROLES:
        elems = ELEMENTS_BY_ROLE[role]
        sub = pool[(pool.role == role) & (~pool.hex.isin(used))].copy()
        if sub.empty:
            continue

        # hue window (same as before)
        h0 = hue_center(constraints, role)
        w = hue_width(constraints, role)
        if h0 is not None and w is not None:
            sub["hue_dist"] = sub.hue.apply(lambda h: circ_dist(h, h0))
            cand = sub[sub.hue_dist <= w / 2]
            if cand.empty:
                cand = sub
        else:
            cand = sub

        if role == "accent_cool":
            # --- NEW: enforce readability vs base ---
            if base_L is not None:
                # primary: enforce lightness delta
                cand = cand[cand["L"] >= (base_L + cool_min_deltal)].copy()

                # if that nukes everything, relax to rank-based separation
                if cand.empty:
                    cand = sub.copy()

            have_ranks = (
                cand["deltaE_bg_rank"].notna().any()
                and cand["abs_deltaL_bg_rank"].notna().any()
            )

            if have_ranks:
                strict = cand[
                    (cand["deltaE_bg_rank"] >= cool_rank_floor)
                    & (cand["abs_deltaL_bg_rank"] >= cool_rank_floor)
                ]
                if strict.empty:
                    strict = cand[cand["deltaE_bg_rank"] >= cool_rank_floor]
                if strict.empty:
                    strict = cand[cand["abs_deltaL_bg_rank"] >= cool_rank_floor]
                if strict.empty:
                    strict = cand

                cand = strict.sort_values(
                    ["deltaE_bg_rank", "abs_deltaL_bg_rank", "score", "frequency"],
                    ascending=[False, False, False, False],
                )
            else:
                cand = cand.sort_values(
                    ["frequency", "score"], ascending=[False, False]
                )

        else:
            cand = cand.sort_values(["frequency", "score"], ascending=[False, False])

        for elem in elems:
            if cand.empty:
                break
            row = cand.iloc[0]
            assignments[elem] = row
            used.add(row.hex)
            cand = cand[cand.hex != row.hex]

    return assignments


# ============================================================
# Rendering + output
# ============================================================


def render(assignments, name):
    console = Console()
    table = Table(title=name)

    table.add_column("Element")
    table.add_column("Hex")
    table.add_column(" ")
    table.add_column("L*")
    table.add_column("C*")
    table.add_column("Hue")
    table.add_column("dE_rank", justify="right")
    table.add_column("|dL|_rank", justify="right")

    for role in ROLE_ORDER:
        for elem in ELEMENTS_BY_ROLE[role]:
            r = assignments.get(elem)
            if r is None:
                table.add_row(elem, "[dim]—[/dim]", "", "", "", "", "", "")
                continue

            h = hex_from_row(r)
            dE_rank = getattr(r, "deltaE_bg_rank", None)
            dL_rank = getattr(r, "abs_deltaL_bg_rank", None)

            def fmt_rank(x):
                if x is None:
                    return ""
                try:
                    if np.isnan(x):
                        return ""
                except Exception:
                    pass
                return f"{float(x):.2f}"

            table.add_row(
                elem,
                h,
                Text("   ", style=Style(bgcolor=h)),
                f"{r.L:.1f}",
                f"{r.chroma:.1f}",
                f"{r.hue:.0f}°",
                fmt_rank(dE_rank),
                fmt_rank(dL_rank),
            )

    console.print(table)


def row_to_dict(r):
    if hasattr(r, "_asdict"):  # namedtuple
        return dict(r._asdict())
    if isinstance(r, pd.Series):  # pandas row
        return r.to_dict()
    raise TypeError(f"Unsupported row type: {type(r)}")


@click.command()
@click.argument("color_pool_csv", type=click.Path(exists=True, path_type=Path))
@click.option("--constraints-json", required=True, type=click.Path(exists=True))
@click.option("--theme-name", default="painting")
@click.option("--out-json", default="assignments.json", show_default=True)
@click.option(
    "--cool-rank-floor",
    default=0.60,
    show_default=True,
    type=float,
    help="Minimum deltaE_bg_rank percentile for accent_cool (relaxed if it prunes everything).",
)
@click.option(
    "--cool-min-deltal",
    default=24.0,
    show_default=True,
    type=float,
    help="Minimum (cool.L - base.L) for accent_cool foreground safety (relaxed to L>base if needed).",
)
def main(
    color_pool_csv,
    constraints_json,
    theme_name,
    out_json,
    cool_rank_floor,
    cool_min_deltal,
):
    pool = pd.read_csv(color_pool_csv)
    pool["hex"] = pool.apply(hex_from_row, axis=1)

    # Ensure new rank columns exist (computed if missing)
    pool = ensure_rank_columns(pool)

    constraints_all = json.loads(Path(constraints_json).read_text())
    palette = pool.palette.iloc[0]

    constraints = {
        "deltaL": constraints_all["constraints"]["deltaL"][palette],
        "chroma": constraints_all["constraints"]["chroma"][palette],
        "hue": constraints_all["constraints"]["hue"][palette],
    }

    assignments = pick_structural(pool, constraints)
    assignments = fill_ui(pool, assignments)
    assignments = pick_accents(
        pool,
        assignments,
        constraints,
        cool_rank_floor=cool_rank_floor,
        cool_min_deltal=cool_min_deltal,
    )

    # Record missing elements
    missing = [
        elem
        for role in ROLE_ORDER
        for elem in ELEMENTS_BY_ROLE[role]
        if elem not in assignments
    ]

    assigned_out = {k: row_to_dict(v) for k, v in assignments.items()}

    Path(out_json).write_text(
        json.dumps(
            {
                "palette": palette,
                "assigned": assigned_out,
                "missing": missing,
            },
            indent=2,
        )
    )

    render(assignments, theme_name)


if __name__ == "__main__":
    main()
