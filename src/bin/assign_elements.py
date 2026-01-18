#!/usr/local/bin/python
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
    "overlay": (
        ["overlay2", "overlay1", "overlay1", "overlay0"]
        if False
        else ["overlay2", "overlay1", "overlay0"]
    ),
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
    # Always lower-case for stable uniqueness checks
    return f"#{int(r.R):02x}{int(r.G):02x}{int(r.B):02x}".lower()


def norm_hex(h: str) -> str:
    return str(h).strip().lower()


def circ_dist(a, b) -> float:
    d = abs(a - b) % 360
    return min(d, 360 - d)


def deltaE76(lab1: np.ndarray, lab2: np.ndarray) -> float:
    d = lab1 - lab2
    return float(np.sqrt(np.dot(d, d)))


def circ_dist_series(series, center: float) -> pd.Series:
    d = (series - center).abs() % 360
    return np.minimum(d, 360 - d)


def pool_add_hex_and_dedupe(pool: pd.DataFrame) -> pd.DataFrame:
    """
    Normalize and dedupe the pool by hex so we don't accidentally select
    the same visible color multiple times via duplicate rows.
    """
    pool = pool.copy()
    pool["hex"] = pool.apply(hex_from_row, axis=1).map(norm_hex)

    # keep "best" row per hex (prefer higher frequency, then higher score)
    sort_cols = [c for c in ["frequency", "score"] if c in pool.columns]
    if sort_cols:
        pool = pool.sort_values(sort_cols, ascending=[False] * len(sort_cols))
    pool = pool.drop_duplicates(subset=["hex"], keep="first").reset_index(drop=True)
    return pool


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


def chroma_bounds(constraints, role, *, relax: bool):
    c = constraints["chroma"].get(role)
    if c is None:
        return None
    q25 = float(c["q25"])
    q75 = float(c["q75"])
    if relax:
        relax_delta = float(c.get("relax_delta", (float(c["q90"]) - float(c["q10"])) / 2))
        q25 = max(0.0, q25 - relax_delta)
        q75 = q75 + relax_delta
    return q25, q75


def lightness_bounds(constraints, role, *, relax: bool):
    l = constraints.get("lightness", {}).get(role)
    if l is None:
        return None
    q25 = float(l["q25"])
    q75 = float(l["q75"])
    if relax:
        relax_delta = float(l.get("relax_delta", (float(l["q90"]) - float(l["q10"])) / 2))
        q25 = max(0.0, q25 - relax_delta)
        q75 = min(100.0, q75 + relax_delta)
    return q25, q75


def hue_window(constraints, role, *, relax: bool):
    h = constraints["hue"].get(role)
    if h is None:
        return None
    center = float(h["center"])
    width = float(h["width"])
    mult = float(h.get("relax_mult", 1.3)) if relax else 1.0
    return center, (width / 2.0) * mult


def get_role_pool(pool: pd.DataFrame, role: str, constraints: dict, *, relax: bool):
    sub = pool[pool.role == role].copy()
    if not sub.empty and not relax:
        return sub

    cand = pool.copy()

    if role in ["background", "surface", "overlay", "text"]:
        cb = chroma_bounds(constraints, role, relax=relax)
        if cb is not None:
            c_lo, c_hi = cb
            cand = cand[(cand["chroma"] >= c_lo) & (cand["chroma"] <= c_hi)]

        lb = lightness_bounds(constraints, role, relax=relax)
        if lb is not None:
            l_lo, l_hi = lb
            cand = cand[(cand["L"] >= l_lo) & (cand["L"] <= l_hi)]

        return cand if not cand.empty else sub

    cb = chroma_bounds(constraints, role, relax=relax)
    if cb is not None:
        c_lo, _ = cb
        cand = cand[cand["chroma"] >= c_lo]

    hw = hue_window(constraints, role, relax=relax)
    if hw is not None:
        center, half = hw
        cand = cand[circ_dist_series(cand["hue"], center) <= half]

    lb = lightness_bounds(constraints, role, relax=relax)
    if lb is not None:
        l_lo, l_hi = lb
        cand = cand[(cand["L"] >= l_lo) & (cand["L"] <= l_hi)]

    return cand if not cand.empty else sub


# ============================================================
# Structural selection (required)
# ============================================================


def pick_structural(pool: pd.DataFrame, constraints: dict):
    polarity = constraints.get("polarity", "dark")
    is_dark = polarity != "light"
    pref_hue = constraints.get("photo_dark_hue")
    pref_hue_conf = float(constraints.get("photo_dark_hue_conf") or 0.0)
    cluster_hue = constraints.get("photo_dark_cluster_hue")
    cluster_score = float(constraints.get("photo_dark_cluster_score") or 0.0)
    bg_photo_hue = constraints.get("photo_bg_hue")
    bg_photo_conf = float(constraints.get("photo_bg_hue_conf") or 0.0)
    photo_L_q30 = constraints.get("photo_L_q30")
    photo_L_q40 = constraints.get("photo_L_q40")
    photo_C_median = constraints.get("photo_C_median")
    bg_hue = constraints.get("background_hue", {})
    bg_width = float(bg_hue.get("width", 60.0))
    ui_hue = constraints.get("ui_hue_coherence", {})
    ui_hue_max = float(ui_hue.get("max_dist", 90.0))

    desired_hue = None
    hue_weight = 0.0
    if bg_photo_hue is not None and bg_photo_conf > 0.05:
        desired_hue = float(bg_photo_hue)
        hue_weight = 0.10 + 0.25 * min(1.0, bg_photo_conf * 2.0)
    if pref_hue is not None and pref_hue_conf > 0.05:
        if desired_hue is None or pref_hue_conf > (bg_photo_conf + 0.05):
            desired_hue = float(pref_hue)
            hue_weight = 0.10 + 0.25 * min(1.0, pref_hue_conf * 2.0)
    if cluster_hue is not None and cluster_score > 0.0:
        if desired_hue is None or cluster_score > (pref_hue_conf * 2.0):
            desired_hue = float(cluster_hue)
            hue_weight = max(hue_weight, 0.15)

    hue_weight *= min(1.0, max(0.3, bg_width / 90.0))

    min_bg_L = None
    if photo_L_q30 is not None and photo_L_q40 is not None:
        if (photo_L_q30 > 28.0) or (photo_L_q40 > 32.0):
            min_bg_L = max(0.0, float(photo_L_q30) - 5.0)

    for relax in [False, True]:
        bg_pool = get_role_pool(pool, "background", constraints, relax=relax)
        surf_pool = get_role_pool(pool, "surface", constraints, relax=relax)
        over_pool = get_role_pool(pool, "overlay", constraints, relax=relax)
        text_pool = get_role_pool(pool, "text", constraints, relax=relax)

        def top_k(df, k):
            if df.empty:
                return df
            return df.sort_values(["score", "frequency"], ascending=[False, False]).head(
                k
            )

        k_bg = 24 if relax else 16
        k_text = 24 if relax else 16
        k_surf = 32 if relax else 20
        k_over = 32 if relax else 20

        bg_pool = top_k(bg_pool, k_bg)
        text_pool = top_k(text_pool, k_text)
        surf_pool = top_k(surf_pool, k_surf)
        over_pool = top_k(over_pool, k_over)

        if bg_pool.empty or text_pool.empty or surf_pool.empty or over_pool.empty:
            continue

        bg_rows = list(bg_pool.itertuples())
        text_rows = list(text_pool.itertuples())
        surf_rows = list(surf_pool.itertuples())
        over_rows = list(over_pool.itertuples())

        bg_L = np.array([r.L for r in bg_rows], dtype=float)
        text_L = np.array([r.L for r in text_rows], dtype=float)

        min_mult = 0.6 if relax else 1.0
        min_bt = deltaL_min(constraints, "background→text") * min_mult

        if is_dark:
            max_text = float(text_L.max())
            bg_keep = bg_L <= (max_text - min_bt)
            min_bg = float(bg_L.min())
            text_keep = text_L >= (min_bg + min_bt)
        else:
            min_text = float(text_L.min())
            bg_keep = bg_L >= (min_text + min_bt)
            max_bg = float(bg_L.max())
            text_keep = text_L <= (max_bg - min_bt)

        bg_rows = [r for r, keep in zip(bg_rows, bg_keep) if keep]
        text_rows = [r for r, keep in zip(text_rows, text_keep) if keep]

        if not bg_rows or not text_rows:
            continue

        best = None
        best_score = float("inf")

        for bg in bg_rows:
            for text in text_rows:
                bt = (text.L - bg.L) if is_dark else (bg.L - text.L)
                if bt < min_bt:
                    continue

                for surf in surf_rows:
                    if is_dark:
                        if not (bg.L < surf.L < text.L):
                            continue
                    else:
                        if not (bg.L > surf.L > text.L):
                            continue

                    for over in over_rows:
                        if is_dark:
                            if not (surf.L < over.L < text.L):
                                continue
                        else:
                            if not (surf.L > over.L > text.L):
                                continue

                        bs = (surf.L - bg.L) if is_dark else (bg.L - surf.L)
                        so = (over.L - surf.L) if is_dark else (surf.L - over.L)
                        ot = (text.L - over.L) if is_dark else (over.L - text.L)

                        score = (
                            abs(bt - deltaL_target(constraints, "background→text"))
                            + abs(bs - deltaL_target(constraints, "background→surface"))
                            + abs(so - deltaL_target(constraints, "surface→overlay"))
                            + abs(ot - deltaL_target(constraints, "overlay→text"))
                            - 2.0
                            * (
                                float(getattr(bg, "frequency", 0.0))
                                + float(getattr(surf, "frequency", 0.0))
                                + float(getattr(over, "frequency", 0.0))
                                + float(getattr(text, "frequency", 0.0))
                            )
                        )
                        if desired_hue is not None and hue_weight > 0.0:
                            score += circ_dist(float(bg.hue), desired_hue) * hue_weight
                        if bg_photo_hue is not None and bg_photo_conf > 0.05:
                            coherence = (
                                circ_dist(float(bg.hue), float(bg_photo_hue))
                                + circ_dist(float(surf.hue), float(bg_photo_hue))
                                + circ_dist(float(over.hue), float(bg_photo_hue))
                            ) / 3.0
                            score += coherence * 0.06
                        ui_dist = max(
                            circ_dist(float(bg.hue), float(surf.hue)),
                            circ_dist(float(bg.hue), float(over.hue)),
                            circ_dist(float(bg.hue), float(text.hue)),
                            circ_dist(float(surf.hue), float(over.hue)),
                            circ_dist(float(surf.hue), float(text.hue)),
                            circ_dist(float(over.hue), float(text.hue)),
                        )
                        if ui_dist > ui_hue_max:
                            score += (ui_dist - ui_hue_max) * 0.15
                        if min_bg_L is not None and float(bg.L) < min_bg_L:
                            score += (min_bg_L - float(bg.L)) * 1.2
                        if photo_C_median is not None and float(photo_C_median) > 18.0:
                            if float(bg.chroma) < 6.0:
                                score += (6.0 - float(bg.chroma)) * 1.5

                        if score < best_score:
                            best_score = score
                            best = {
                                "base": bg,
                                "surface1": surf,
                                "overlay1": over,
                                "text": text,
                            }

        if best:
            return best

    return {}


# ============================================================
# Fill remaining UI elements (best effort)
# ============================================================


def get_offset(constraints, offset_name, fallback):
    """Get learned element offset, with fallback for missing constraints."""
    offsets = constraints.get("element_offsets", {})
    if offset_name in offsets:
        return offsets[offset_name].get("value", fallback)
    return fallback


def fill_ui(pool, assignments, constraints):
    used = {norm_hex(hex_from_row(v)) for v in assignments.values()}

    def pick(role, target_L):
        sub = pool[(pool.role == role) & (~pool.hex.isin(used))].copy()
        if sub.empty:
            sub = get_role_pool(pool, role, constraints, relax=True)
            sub = sub[~sub.hex.isin(used)].copy()
        if sub.empty:
            return None
        sub["dist"] = (sub.L - target_L).abs()
        r = sub.sort_values(["dist", "score"], ascending=[True, False]).iloc[0]
        used.add(norm_hex(r.hex))
        return r

    if "base" not in assignments or "surface1" not in assignments:
        return assignments

    base = assignments["base"]
    surf = assignments["surface1"]
    over = assignments.get("overlay1")
    text = assignments.get("text")

    # Use learned offsets from Catppuccin constraints
    for k, r in {
        "mantle": pick(
            "background",
            base.L + get_offset(constraints, "mantle_from_base", -3.0),
        ),
        "crust": pick(
            "background",
            base.L + get_offset(constraints, "crust_from_base", -6.5),
        ),
        "surface0": pick(
            "surface",
            surf.L + get_offset(constraints, "surface0_from_surface1", -9.0),
        ),
        "surface2": pick(
            "surface",
            surf.L + get_offset(constraints, "surface2_from_surface1", 8.5),
        ),
        "overlay0": (
            pick(
                "overlay",
                over.L + get_offset(constraints, "overlay0_from_overlay1", -8.0),
            )
            if over is not None
            else None
        ),
        "overlay2": (
            pick(
                "overlay",
                over.L + get_offset(constraints, "overlay2_from_overlay1", 8.0),
            )
            if over is not None
            else None
        ),
        "subtext1": (
            pick(
                "text",
                text.L + get_offset(constraints, "subtext1_from_text", -7.0),
            )
            if text is not None
            else None
        ),
        "subtext0": (
            pick(
                "text",
                text.L + get_offset(constraints, "subtext0_from_text", -15.0),
            )
            if text is not None
            else None
        ),
    }.items():
        if r is not None:
            assignments[k] = r

    return assignments


# ============================================================
# Accent selection (non-fatal, greedy)
# ============================================================


def get_accent_min_deltal(constraints, role, polarity, fallback):
    """
    Get learned minimum L* separation for an accent role from constraints.

    Uses accent_separation[polarity][role]["min"], with fallback.
    """
    sep = constraints.get("accent_separation", {})
    pol_sep = sep.get(polarity, {})
    role_sep = pol_sep.get(role, {})
    return role_sep.get("min", fallback)


def pick_accents(
    pool: pd.DataFrame,
    assignments: dict,
    constraints: dict,
    *,
    cool_rank_floor: float = 0.60,
    cool_min_deltal: float | None = None,
    accent_min_deltal: float | None = None,
):
    """
    Select accent colors from pool, respecting hue and L* separation constraints.

    If cool_min_deltal or accent_min_deltal are None, uses learned values from
    constraints["accent_separation"].
    """
    used = {norm_hex(hex_from_row(v)) for v in assignments.values()}

    base = assignments.get("base")
    base_L = float(base.L) if base is not None else None
    is_dark = base_L is not None and base_L < 50.0
    polarity = "dark" if is_dark else "light"
    warm_hue = constraints.get("photo_warm_hue")
    warm_hue_conf = float(constraints.get("photo_warm_hue_conf") or 0.0)
    text = assignments.get("text")
    text_lab = (
        np.array([float(text.L), float(text.a), float(text.b)], dtype=float)
        if text is not None
        else None
    )
    accent_text_sep = constraints.get("accent_text_separation", {})

    for role in ACCENT_ROLES:
        elems = ELEMENTS_BY_ROLE[role]
        sub = pool[(pool.role == role) & (~pool.hex.isin(used))].copy()
        if sub.empty:
            sub = get_role_pool(pool, role, constraints, relax=True)
            sub = sub[~sub.hex.isin(used)].copy()
        if sub.empty:
            continue

        # Hue window (if present)
        h0 = hue_center(constraints, role)
        w = hue_width(constraints, role)
        if h0 is not None and w is not None:
            sub["hue_dist"] = sub.hue.apply(lambda h: circ_dist(h, h0))
            cand = sub[sub.hue_dist <= w / 2].copy()
            if cand.empty:
                cand = sub
        else:
            cand = sub

        # Get role-specific min L* separation (learned or override)
        if role == "accent_cool":
            min_deltal = (
                cool_min_deltal
                if cool_min_deltal is not None
                else get_accent_min_deltal(constraints, role, polarity, 48.0)
            )
        else:
            min_deltal = (
                accent_min_deltal
                if accent_min_deltal is not None
                else get_accent_min_deltal(constraints, role, polarity, 43.0)
            )

        # Require accents to be separated from base in L* (only if it doesn't wipe everything)
        if base_L is not None and "L" in cand.columns:
            if is_dark:
                floored = cand[cand["L"] >= (base_L + abs(min_deltal))].copy()
            else:
                floored = cand[cand["L"] <= (base_L - abs(min_deltal))].copy()
            if not floored.empty:
                cand = floored

        # Accent-text separation (avoid accents too close to text)
        if text_lab is not None and "L" in cand.columns:
            sep = accent_text_sep.get(role, {})
            min_de = float(sep.get("deltaE_q10", 0.0))
            min_dl = float(sep.get("deltaL_q10", 0.0))
            if min_de > 0.0 or min_dl > 0.0:
                cand["deltaE_text"] = cand.apply(
                    lambda r: deltaE76(
                        np.array([r.L, r.a, r.b], dtype=float), text_lab
                    ),
                    axis=1,
                )
                cand["abs_deltaL_text"] = (cand["L"] - float(text.L)).abs()
                gated = cand[
                    (cand["deltaE_text"] >= min_de)
                    & (cand["abs_deltaL_text"] >= min_dl)
                ]
                if not gated.empty:
                    cand = gated

        # Rank-aware preference (if present)
        have_ranks = (
            "deltaE_bg_rank" in cand.columns
            and "abs_deltaL_bg_rank" in cand.columns
            and cand["deltaE_bg_rank"].notna().any()
            and cand["abs_deltaL_bg_rank"].notna().any()
        )

        if role == "accent_cool":
            # stronger cool FG-safety (min_deltal already set above from learned constraints)
            if base_L is not None and "L" in cand.columns:
                if is_dark:
                    cand = cand[cand["L"] >= (base_L + abs(min_deltal))]
                else:
                    cand = cand[cand["L"] <= (base_L - abs(min_deltal))]

                # Relax if empty but still prefer "not darker than base" in dark themes
                if cand.empty:
                    cand = sub.copy()
                    if is_dark:
                        cand = cand[cand["L"] >= base_L]
                    else:
                        cand = cand[cand["L"] <= base_L]
                    if cand.empty:
                        cand = sub.copy()

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
            if have_ranks:
                if role == "accent_warm" and warm_hue is not None and warm_hue_conf > 0.05:
                    cand["warm_dist"] = cand.hue.apply(lambda h: circ_dist(h, warm_hue))
                    cand = cand.sort_values(
                        ["warm_dist", "deltaE_bg_rank", "abs_deltaL_bg_rank", "score", "frequency"],
                        ascending=[True, False, False, False, False],
                    )
                else:
                    cand = cand.sort_values(
                        ["deltaE_bg_rank", "abs_deltaL_bg_rank", "score", "frequency"],
                        ascending=[False, False, False, False],
                    )
            else:
                if role == "accent_warm" and warm_hue is not None and warm_hue_conf > 0.05:
                    cand["warm_dist"] = cand.hue.apply(lambda h: circ_dist(h, warm_hue))
                    cand = cand.sort_values(
                        ["warm_dist", "score", "frequency"],
                        ascending=[True, False, False],
                    )
                else:
                    cand = cand.sort_values(
                        ["frequency", "score"], ascending=[False, False]
                    )

        # Assign unique colors per element
        for elem in elems:
            if cand.empty:
                break

            row = cand.iloc[0]
            hx = norm_hex(row.hex)

            # Extra guard: if we somehow collided, skip forward
            if hx in used:
                cand = cand[cand.hex != hx]
                continue

            assignments[elem] = row
            used.add(hx)
            cand = cand[cand.hex != hx]

    return assignments


# ============================================================
# Rendering + output
# ============================================================


def _build_table(assignments, name):
    """Build a Rich Table for the assignments."""
    table = Table(title=name)

    table.add_column("Element")
    table.add_column("Hex")
    table.add_column(" ")
    table.add_column("L*")
    table.add_column("C*")
    table.add_column("Hue")
    table.add_column("dE_rank", justify="right")
    table.add_column("|dL|_rank", justify="right")

    def fmt_rank(x):
        if x is None:
            return ""
        try:
            if np.isnan(x):
                return ""
        except Exception:
            pass
        return f"{float(x):.2f}"

    for role in ROLE_ORDER:
        for elem in ELEMENTS_BY_ROLE[role]:
            r = assignments.get(elem)
            if r is None:
                table.add_row(elem, "[dim]—[/dim]", "", "", "", "", "", "")
                continue

            h = hex_from_row(r)
            dE_rank = getattr(r, "deltaE_bg_rank", None)
            dL_rank = getattr(r, "abs_deltaL_bg_rank", None)

            table.add_row(
                elem,
                h,
                Text("   ", style=Style(bgcolor=h)),
                f"{float(r.L):.1f}",
                f"{float(r.chroma):.1f}",
                f"{float(r.hue):.0f}°",
                fmt_rank(dE_rank),
                fmt_rank(dL_rank),
            )

    return table


def render(assignments, name):
    """Print table to terminal."""
    console = Console()
    table = _build_table(assignments, name)
    console.print(table)


def save_table_image(assignments, name, out_path: Path):
    """
    Save table as SVG or PNG image.

    - .svg: Native Rich export
    - .png: Requires cairosvg (pip install cairosvg)
    """
    table = _build_table(assignments, name)

    # Record output to SVG
    console = Console(record=True, width=80, force_terminal=True)
    console.print(table)

    svg_content = console.export_svg(title=name)

    suffix = out_path.suffix.lower()
    if suffix == ".svg":
        out_path.write_text(svg_content)
    elif suffix == ".png":
        try:
            import cairosvg
        except ImportError:
            raise click.ClickException(
                "PNG export requires cairosvg: pip install cairosvg"
            )
        cairosvg.svg2png(bytestring=svg_content.encode(), write_to=str(out_path))
    else:
        raise click.ClickException(
            f"Unsupported image format: {suffix} (use .svg or .png)"
        )


def row_to_dict(r):
    if hasattr(r, "_asdict"):  # namedtuple
        d = dict(r._asdict())
        if "hex" in d and d["hex"]:
            d["hex"] = norm_hex(d["hex"])
        return d
    if isinstance(r, pd.Series):  # pandas row
        d = r.to_dict()
        if "hex" in d and d["hex"]:
            d["hex"] = norm_hex(d["hex"])
        return d
    raise TypeError(f"Unsupported row type: {type(r)}")


@click.command()
@click.argument("color_pool_csv", type=click.Path(exists=True, path_type=Path))
@click.option("--constraints-json", required=True, type=click.Path(exists=True))
@click.option("--theme-name", default="painting")
@click.option("--out-json", default="assignments.json", show_default=True)
@click.option(
    "--out-image",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Save table as image (.svg or .png). PNG requires cairosvg.",
)
@click.option(
    "--cool-rank-floor",
    default=0.60,
    show_default=True,
    type=float,
    help="Minimum deltaE_bg_rank percentile for accent_cool (relaxed if it prunes everything).",
)
@click.option(
    "--cool-min-deltal",
    default=None,
    type=float,
    help="Override learned minimum L* separation for accent_cool (default: use learned constraint).",
)
@click.option(
    "--accent-min-deltal",
    default=None,
    type=float,
    help="Override learned minimum L* separation for non-cool accents (default: use learned constraint).",
)
def main(
    color_pool_csv,
    constraints_json,
    theme_name,
    out_json,
    out_image,
    cool_rank_floor,
    cool_min_deltal,
    accent_min_deltal,
):
    pool = pd.read_csv(color_pool_csv)
    pool = pool_add_hex_and_dedupe(pool)

    # Ensure new rank columns exist (computed if missing)
    pool = ensure_rank_columns(pool)

    constraints_all = json.loads(Path(constraints_json).read_text())
    if "palette" not in pool.columns:
        raise click.ClickException("color_pool.csv must include a 'palette' column")
    palette = str(pool.palette.iloc[0])

    constraints = {
        "deltaL": constraints_all["constraints"]["deltaL"][palette],
        "chroma": constraints_all["constraints"]["chroma"][palette],
        "hue": constraints_all["constraints"]["hue"][palette],
        "lightness": constraints_all["constraints"].get("lightness", {}).get(
            palette, {}
        ),
        "polarity": constraints_all.get("polarity", {}).get(palette, "dark"),
        "background_hue": constraints_all["constraints"]
        .get("background_hue", {})
        .get(palette, {}),
        "ui_hue_coherence": constraints_all["constraints"]
        .get("ui_hue_coherence", {})
        .get(palette, {}),
        "element_offsets": constraints_all["constraints"]
        .get("element_offsets", {})
        .get(palette, {}),
        "accent_separation": constraints_all["constraints"].get(
            "accent_separation", {}
        ),
        "accent_text_separation": constraints_all["constraints"].get(
            "accent_text_separation", {}
        ).get(palette, {}),
    }

    if "photo_dark_hue" in pool.columns:
        constraints["photo_dark_hue"] = pool["photo_dark_hue"].dropna().iloc[0]
        constraints["photo_dark_hue_conf"] = (
            pool.get("photo_dark_hue_conf", pd.Series([0.0])).dropna().iloc[0]
        )
        constraints["photo_dark_cluster_hue"] = (
            pool.get("photo_dark_cluster_hue", pd.Series([np.nan])).dropna().iloc[0]
        )
        constraints["photo_dark_cluster_score"] = (
            pool.get("photo_dark_cluster_score", pd.Series([0.0])).dropna().iloc[0]
        )
        constraints["photo_bg_hue"] = (
            pool.get("photo_bg_hue", pd.Series([np.nan])).dropna().iloc[0]
        )
        constraints["photo_bg_hue_conf"] = (
            pool.get("photo_bg_hue_conf", pd.Series([0.0])).dropna().iloc[0]
        )
        constraints["photo_L_q30"] = (
            pool.get("photo_L_q30", pd.Series([np.nan])).dropna().iloc[0]
        )
        constraints["photo_L_q40"] = (
            pool.get("photo_L_q40", pd.Series([np.nan])).dropna().iloc[0]
        )
        constraints["photo_C_median"] = (
            pool.get("photo_C_median", pd.Series([np.nan])).dropna().iloc[0]
        )
        constraints["photo_warm_hue"] = (
            pool.get("photo_warm_hue", pd.Series([np.nan])).dropna().iloc[0]
        )
        constraints["photo_warm_hue_conf"] = (
            pool.get("photo_warm_hue_conf", pd.Series([0.0])).dropna().iloc[0]
        )

    assignments = pick_structural(pool, constraints)
    assignments = fill_ui(pool, assignments, constraints)
    assignments = pick_accents(
        pool,
        assignments,
        constraints,
        cool_rank_floor=cool_rank_floor,
        cool_min_deltal=cool_min_deltal,
        accent_min_deltal=accent_min_deltal,
    )

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

    if out_image is not None:
        save_table_image(assignments, theme_name, out_image)


if __name__ == "__main__":
    main()
