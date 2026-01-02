from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import click
import numpy as np
import pandas as pd
from rich.console import Console
from rich.style import Style
from rich.table import Table
from rich.text import Text
from skimage.color import lab2rgb

# ============================================================
# Catppuccin structure (fixed)
# ============================================================

ELEMENTS_BY_ROLE = {
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

UI_CORE = ["background", "surface", "overlay", "text"]
ACCENT_ROLES = ["accent_red", "accent_warm", "accent_cool", "accent_bridge"]

PAIR_BG_TEXT = "background→text"
PAIR_BG_SURF = "background→surface"
PAIR_SURF_OVER = "surface→overlay"
PAIR_OVER_TEXT = "overlay→text"

ROLE_BY_ELEMENT = {
    elem: role for role, elems in ELEMENTS_BY_ROLE.items() for elem in elems
}

# ============================================================
# Color helpers (Lab / LCh)
# ============================================================


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def circ_dist_deg(a: float, b: float) -> float:
    d = abs(a - b) % 360.0
    return min(d, 360.0 - d)


def lab_to_lch(L: float, a: float, b: float) -> Tuple[float, float, float]:
    C = math.sqrt(a * a + b * b)
    h = (math.degrees(math.atan2(b, a)) % 360.0) if C > 1e-9 else 0.0
    return (float(L), float(C), float(h))


def lch_to_lab(L: float, C: float, h: float) -> Tuple[float, float, float]:
    hr = math.radians(h)
    a = C * math.cos(hr)
    b = C * math.sin(hr)
    return (float(L), float(a), float(b))


def lab_to_rgb_hex(L: float, a: float, b: float) -> str:
    lab = np.array([[[L, a, b]]], dtype=float)
    rgb = lab2rgb(lab)[0, 0, :]
    rgb = np.clip(rgb, 0.0, 1.0)
    r, g, bb = (rgb * 255.0 + 0.5).astype(int)
    return f"#{r:02x}{g:02x}{bb:02x}"


def delta_e_lab_rows(r1: Dict[str, Any], r2: Dict[str, Any]) -> float:
    v1 = np.array([float(r1["L"]), float(r1["a"]), float(r1["b"])], dtype=float)
    v2 = np.array([float(r2["L"]), float(r2["a"]), float(r2["b"])], dtype=float)
    return float(np.linalg.norm(v1 - v2))


# ============================================================
# Constraints access (palette scoped)
# ============================================================


@dataclass(frozen=True)
class PaletteConstraints:
    deltaL: Dict[str, Dict[str, float]]
    chroma: Dict[str, Dict[str, float]]
    hue: Dict[str, Dict[str, float]]

    def deltaL_min(self, pair: str) -> float:
        return float(self.deltaL[pair]["q25"])

    def deltaL_target(self, pair: str) -> float:
        return float(self.deltaL[pair]["median"])

    def chroma_q25(self, role: str) -> float:
        return float(self.chroma[role]["q25"])

    def chroma_q75(self, role: str) -> float:
        return float(self.chroma[role]["q75"])

    def hue_center(self, role: str) -> Optional[float]:
        x = self.hue.get(role)
        return float(x["center"]) if x and "center" in x else None

    def hue_width(self, role: str) -> Optional[float]:
        x = self.hue.get(role)
        return float(x["width"]) if x and "width" in x else None


# ============================================================
# IO normalization
# ============================================================


def normalize_assignment_row(d: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(d)

    for k in ["L", "a", "b", "chroma", "hue", "frequency", "score", "R", "G", "B"]:
        if k not in out and k.capitalize() in out:
            out[k] = out[k.capitalize()]

    for k in ["L", "a", "b", "chroma", "hue", "frequency", "score"]:
        if k in out and out[k] is not None:
            try:
                out[k] = float(out[k])
            except Exception:
                pass

    for k in ["R", "G", "B"]:
        if k in out and out[k] is not None:
            try:
                out[k] = int(out[k])
            except Exception:
                pass

    return out


def element_hex(row: Dict[str, Any]) -> str:
    if "hex" in row and isinstance(row["hex"], str) and row["hex"].startswith("#"):
        return row["hex"]
    if all(k in row for k in ["R", "G", "B"]):
        return f"#{int(row['R']):02x}{int(row['G']):02x}{int(row['B']):02x}"
    return lab_to_rgb_hex(float(row["L"]), float(row["a"]), float(row["b"]))


# ============================================================
# Pool normalization / derived metrics
# ============================================================


def ensure_pool_columns(pool: pd.DataFrame) -> pd.DataFrame:
    pool = pool.copy()

    if "hex" not in pool.columns:
        raise click.ClickException("color_pool.csv must contain a 'hex' column")
    if "role" not in pool.columns:
        raise click.ClickException("color_pool.csv must contain a 'role' column")

    for c in [
        "L",
        "a",
        "b",
        "chroma",
        "hue",
        "frequency",
        "score",
        "deltaE_bg",
        "abs_deltaL_bg",
        "deltaE_bg_rank",
        "abs_deltaL_bg_rank",
    ]:
        if c in pool.columns:
            pool[c] = pd.to_numeric(pool[c], errors="coerce")

    # Compute abs_deltaL_bg if missing but we have background candidates later; if not possible, we leave NaN.
    if "abs_deltaL_bg" not in pool.columns:
        pool["abs_deltaL_bg"] = np.nan

    if "deltaE_bg_rank" not in pool.columns and "deltaE_bg" in pool.columns:
        pool["deltaE_bg_rank"] = pool.groupby("role")["deltaE_bg"].rank(
            pct=True, method="average"
        )
    if "abs_deltaL_bg_rank" not in pool.columns and "abs_deltaL_bg" in pool.columns:
        pool["abs_deltaL_bg_rank"] = pool.groupby("role")["abs_deltaL_bg"].rank(
            pct=True, method="average"
        )

    return pool


# ============================================================
# Nudge logic (H/C only; avoid darkening accents)
# ============================================================


def nudge_into_role(
    row: Dict[str, Any],
    role: str,
    pc: PaletteConstraints,
    *,
    relax: bool,
    base_L: Optional[float] = None,
    cool_min_deltal: float = 24.0,
    lock_L: bool = False,
    min_L: Optional[float] = None,
    forbid_L_decrease: bool = False,
) -> Dict[str, Any]:
    """
    Return a *new* row dict nudged toward palette constraints for role.
    By default, ONLY adjusts hue/chroma; L is locked unless explicitly allowed.

    For accent_cool safety:
      - enforce L >= base_L + cool_min_deltal (via min_L) when base_L available
      - never decrease L when forbid_L_decrease=True
    """
    L0, a0, b0 = float(row["L"]), float(row["a"]), float(row["b"])
    L, C, h = lab_to_lch(L0, a0, b0)

    # --- chroma band ---
    if role in pc.chroma:
        q25 = pc.chroma_q25(role)
        q75 = pc.chroma_q75(role)
        if relax:
            q25 = max(0.0, q25 - 8.0)
            q75 = q75 + 8.0

        if C < q25:
            C = q25
        elif C > q75:
            C = q75

    # --- hue window for accents ---
    hc = pc.hue_center(role)
    hw = pc.hue_width(role)
    if hc is not None and hw is not None:
        half = (hw / 2.0) * (1.3 if relax else 1.0)
        if circ_dist_deg(h, hc) > half:
            if relax:
                h = hc
            else:
                d = ((h - hc + 180) % 360) - 180  # signed [-180, 180)
                h = (hc + math.copysign(half, d)) % 360.0

    # --- L handling ---
    L_new = L
    if not lock_L:
        if min_L is not None:
            L_new = max(L_new, float(min_L))
        if forbid_L_decrease:
            L_new = max(L_new, L0)

    # clamp
    L_new = clamp(L_new, 0.0, 100.0)

    L2, a2, b2 = lch_to_lab(L_new, C, h)

    out = dict(row)
    out["L"], out["a"], out["b"] = float(L2), float(a2), float(b2)
    _, C2, h2 = lab_to_lch(out["L"], out["a"], out["b"])
    out["chroma"], out["hue"] = float(C2), float(h2)
    out["hex"] = lab_to_rgb_hex(out["L"], out["a"], out["b"])
    return out


def _role_hue_filter(
    sub: pd.DataFrame, role: str, pc: PaletteConstraints, relax: bool
) -> pd.DataFrame:
    hc = pc.hue_center(role)
    hw = pc.hue_width(role)
    if hc is None or hw is None:
        return sub

    half = (hw / 2.0) * (1.3 if relax else 1.0)
    tmp = sub.copy()
    tmp["hue_dist"] = tmp["hue"].apply(lambda x: circ_dist_deg(float(x), float(hc)))
    inwin = tmp[tmp["hue_dist"] <= half].copy()
    return inwin if not inwin.empty else sub


def pick_best_candidate(
    pool: pd.DataFrame,
    *,
    role: str,
    used_hex: set[str],
    pc: PaletteConstraints,
    relax: bool,
    base_L: Optional[float],
    cool_min_deltal: float,
    cool_rank_floor: float,
) -> Optional[Dict[str, Any]]:
    """
    Choose a seed extracted color (row) to use for role.
    For accent_cool: require strong separation from base using rank/ΔL floor.
    """
    sub = pool[~pool["hex"].isin(used_hex)].copy()
    if sub.empty:
        return None

    # prefer same role
    sub_role = sub[sub["role"] == role].copy()
    if not sub_role.empty:
        sub = sub_role

    # hue filter for accents
    sub = _role_hue_filter(sub, role, pc, relax=relax)

    # accent_cool safety gates + sort by ranks
    if role == "accent_cool":
        if base_L is not None and "L" in sub.columns:
            sub = sub[sub["L"].notna()]
            sub = sub[sub["L"] >= (float(base_L) + float(cool_min_deltal))]

        # If rank columns exist, enforce floors (non-fatal: relax pass will widen)
        if "deltaE_bg_rank" in sub.columns and sub["deltaE_bg_rank"].notna().any():
            if not relax:
                sub2 = sub[sub["deltaE_bg_rank"] >= float(cool_rank_floor)]
                if not sub2.empty:
                    sub = sub2
        if (
            "abs_deltaL_bg_rank" in sub.columns
            and sub["abs_deltaL_bg_rank"].notna().any()
        ):
            if not relax:
                sub2 = sub[sub["abs_deltaL_bg_rank"] >= float(cool_rank_floor)]
                if not sub2.empty:
                    sub = sub2

        # Sort preference: ranks (if present) then score/frequency
        sort_cols = []
        asc = []
        for c in ["deltaE_bg_rank", "abs_deltaL_bg_rank"]:
            if c in sub.columns and sub[c].notna().any():
                sort_cols.append(c)
                asc.append(False)
        for c in ["score", "frequency"]:
            if c in sub.columns and sub[c].notna().any():
                sort_cols.append(c)
                asc.append(False)

        if sort_cols:
            sub = sub.sort_values(sort_cols, ascending=asc)
        else:
            # fallback
            sub = sub.sort_values(["frequency", "score"], ascending=[False, False])

        return sub.iloc[0].to_dict() if not sub.empty else None

    # default roles: frequency + score
    sort_cols = []
    asc = []
    if "frequency" in sub.columns and sub["frequency"].notna().any():
        sort_cols.append("frequency")
        asc.append(False)
    if "score" in sub.columns and sub["score"].notna().any():
        sort_cols.append("score")
        asc.append(False)
    if sort_cols:
        sub = sub.sort_values(sort_cols, ascending=asc)

    return sub.iloc[0].to_dict() if not sub.empty else None


# ============================================================
# Structural polish (best-effort)
# ============================================================


def enforce_structural_L(
    assign: Dict[str, Dict[str, Any]], pc: PaletteConstraints
) -> None:
    needed = ["base", "surface1", "overlay1", "text"]
    if not all(k in assign for k in needed):
        return

    base = assign["base"]
    surf = assign["surface1"]
    over = assign["overlay1"]
    text = assign["text"]

    Lb, Ls, Lo, Lt = (
        float(base["L"]),
        float(surf["L"]),
        float(over["L"]),
        float(text["L"]),
    )

    eps = 1.0
    Ls = max(Ls, Lb + eps)
    Lo = max(Lo, Ls + eps)
    Lt = max(Lt, Lo + eps)

    min_bt = pc.deltaL_min(PAIR_BG_TEXT)
    min_bs = pc.deltaL_min(PAIR_BG_SURF)
    min_so = pc.deltaL_min(PAIR_SURF_OVER)
    min_ot = pc.deltaL_min(PAIR_OVER_TEXT)

    if (Lt - Lb) < min_bt:
        Lt = Lb + min_bt
    if (Ls - Lb) < min_bs:
        Ls = Lb + min_bs
    if (Lo - Ls) < min_so:
        Lo = Ls + min_so
    if (Lt - Lo) < min_ot:
        Lt = Lo + min_ot

    Lb = clamp(Lb, 0.0, 100.0)
    Ls = clamp(Ls, 0.0, 100.0)
    Lo = clamp(Lo, 0.0, 100.0)
    Lt = clamp(Lt, 0.0, 100.0)

    for key, newL in [("base", Lb), ("surface1", Ls), ("overlay1", Lo), ("text", Lt)]:
        r = assign[key]
        r["L"] = float(newL)
        r["hex"] = lab_to_rgb_hex(float(r["L"]), float(r["a"]), float(r["b"]))
        _, C, h = lab_to_lch(float(r["L"]), float(r["a"]), float(r["b"]))
        r["chroma"], r["hue"] = float(C), float(h)


# ============================================================
# Rendering
# ============================================================


def render_table(assignments: Dict[str, Dict[str, Any]], theme_name: str) -> None:
    console = Console()
    table = Table(title=theme_name)

    table.add_column("Element", style="cyan", no_wrap=True)
    table.add_column("Hex", no_wrap=True)
    table.add_column(" ")
    table.add_column("L*", justify="right")
    table.add_column("C*", justify="right")
    table.add_column("Hue", justify="right")
    table.add_column("Derived", justify="center")

    for role in ROLE_ORDER:
        for elem in ELEMENTS_BY_ROLE[role]:
            r = assignments.get(elem)
            if r is None:
                table.add_row(elem, "[dim]—[/dim]", "", "", "", "", "")
                continue
            h = r.get("hex") or element_hex(r)
            sw = Text("   ", style=Style(bgcolor=h))
            table.add_row(
                elem,
                h,
                sw,
                f"{float(r.get('L', 0.0)):.1f}",
                f"{float(r.get('chroma', 0.0)):.1f}",
                f"{float(r.get('hue', 0.0)):.0f}°",
                "✓" if r.get("derived") else "",
            )

    console.print(table)


# ============================================================
# Lua output
# ============================================================


def write_lua(
    assignments: Dict[str, Dict[str, Any]], out_lua: Path, theme_name: str
) -> None:
    lines = []
    lines.append(f"local {theme_name} = {{")
    for role in ROLE_ORDER[::-1]:
        for elem in ELEMENTS_BY_ROLE[role]:
            r = assignments.get(elem)
            if r is None:
                continue
            h = r.get("hex") or element_hex(r)
            lines.append(f"  {elem} = '{h}',")
    lines.append("}")
    out_lua.write_text("\n".join(lines))


# ============================================================
# Main polish routine
# ============================================================


def polish(
    assignments_in: Dict[str, Any],
    pool: pd.DataFrame,
    pc: PaletteConstraints,
    *,
    cool_min_deltal: float,
    cool_rank_floor: float,
) -> Dict[str, Any]:
    """
    Fill missing elements by selecting extracted colors, but:
      - Do NOT derive/darken accents (especially accent_cool).
      - For accent_cool, enforce L >= base.L + cool_min_deltal and prefer high ranks.
    """
    assigned_raw = assignments_in.get("assigned", {})
    palette = assignments_in.get("palette")

    assignments: Dict[str, Dict[str, Any]] = {
        k: normalize_assignment_row(v) for k, v in assigned_raw.items()
    }

    # ensure hex + derived flag
    for k, v in assignments.items():
        v["hex"] = v.get("hex") or element_hex(v)
        v["derived"] = bool(v.get("derived", False))

    pool = ensure_pool_columns(pool)

    all_elems = [e for r in ROLE_ORDER for e in ELEMENTS_BY_ROLE[r]]
    used_hex = {assignments[e]["hex"] for e in assignments if "hex" in assignments[e]}

    base_L: Optional[float] = None
    if "base" in assignments and assignments["base"].get("L") is not None:
        try:
            base_L = float(assignments["base"]["L"])
        except Exception:
            base_L = None

    # two-pass: strict then relaxed
    for relax in [False, True]:
        for elem in all_elems:
            if elem in assignments:
                continue

            role = ROLE_BY_ELEMENT[elem]

            seed = pick_best_candidate(
                pool,
                role=role,
                used_hex=used_hex,
                pc=pc,
                relax=relax,
                base_L=base_L,
                cool_min_deltal=cool_min_deltal,
                cool_rank_floor=cool_rank_floor,
            )
            if seed is None:
                continue

            if any(k not in seed or pd.isna(seed[k]) for k in ["L", "a", "b"]):
                continue

            # Build row dict from pool seed
            row = {
                "R": int(seed.get("R", 0)) if not pd.isna(seed.get("R", np.nan)) else 0,
                "G": int(seed.get("G", 0)) if not pd.isna(seed.get("G", np.nan)) else 0,
                "B": int(seed.get("B", 0)) if not pd.isna(seed.get("B", np.nan)) else 0,
                "L": float(seed["L"]),
                "a": float(seed["a"]),
                "b": float(seed["b"]),
                "chroma": float(
                    seed.get(
                        "chroma",
                        lab_to_lch(
                            float(seed["L"]), float(seed["a"]), float(seed["b"])
                        )[1],
                    )
                ),
                "hue": float(
                    seed.get(
                        "hue",
                        lab_to_lch(
                            float(seed["L"]), float(seed["a"]), float(seed["b"])
                        )[2],
                    )
                ),
                "frequency": (
                    float(seed.get("frequency", 0.0))
                    if not pd.isna(seed.get("frequency", np.nan))
                    else 0.0
                ),
                "score": (
                    float(seed.get("score", 0.0))
                    if not pd.isna(seed.get("score", np.nan))
                    else 0.0
                ),
                "role": role,
                "seed_hex": str(seed.get("hex", "")),
                "hex": str(seed.get("hex", "")),
                "derived": False,  # IMPORTANT: do not mark pool picks as derived
            }

            # Ensure we at least align hue/chroma windows, but NEVER darken accents.
            if role in ACCENT_ROLES:
                min_L = None
                forbid_L_decrease = True
                lock_L = True

                if role == "accent_cool" and base_L is not None:
                    # enforce foreground-safe lightness for cool accents
                    min_L = float(base_L) + float(cool_min_deltal)
                    lock_L = False  # allow brightening upward if needed
                    forbid_L_decrease = True

                row2 = nudge_into_role(
                    row,
                    role,
                    pc,
                    relax=relax,
                    base_L=base_L,
                    cool_min_deltal=cool_min_deltal,
                    lock_L=lock_L,
                    min_L=min_L,
                    forbid_L_decrease=forbid_L_decrease,
                )

                # If nudging changed the hex, mark derived (but we still prevented darkening)
                if row2["hex"] != row["hex"]:
                    row2["derived"] = True
                row = row2

            else:
                # UI core elements: allow gentle chroma/hue nudge only; L handled later structurally
                row2 = nudge_into_role(row, role, pc, relax=relax, lock_L=True)
                if row2["hex"] != row["hex"]:
                    row2["derived"] = True
                row = row2

            # uniqueness: if collision, skip (we do NOT hue-perturb accents into garbage)
            if row["hex"] in used_hex:
                continue

            row["element"] = elem
            assignments[elem] = row
            used_hex.add(row["hex"])

        if all(e in assignments for e in all_elems):
            break

    # If still missing, fill from pool WITHOUT creating dark derived accents.
    missing = [e for e in all_elems if e not in assignments]
    if missing:
        for elem in missing:
            role = ROLE_BY_ELEMENT[elem]

            seed = pick_best_candidate(
                pool,
                role=role,
                used_hex=used_hex,
                pc=pc,
                relax=True,
                base_L=base_L,
                cool_min_deltal=cool_min_deltal,
                cool_rank_floor=max(0.25, cool_rank_floor - 0.25),
            )

            if seed is None or any(
                k not in seed or pd.isna(seed[k]) for k in ["L", "a", "b"]
            ):
                # last resort: neutral gray (only for UI core; for accents, leave missing)
                if role in ACCENT_ROLES:
                    continue
                seed = {
                    "L": 50.0,
                    "a": 0.0,
                    "b": 0.0,
                    "hex": lab_to_rgb_hex(50.0, 0.0, 0.0),
                    "role": role,
                }

            row = {
                "L": float(seed["L"]),
                "a": float(seed["a"]),
                "b": float(seed["b"]),
                "chroma": float(
                    seed.get(
                        "chroma",
                        lab_to_lch(
                            float(seed["L"]), float(seed["a"]), float(seed["b"])
                        )[1],
                    )
                ),
                "hue": float(
                    seed.get(
                        "hue",
                        lab_to_lch(
                            float(seed["L"]), float(seed["a"]), float(seed["b"])
                        )[2],
                    )
                ),
                "frequency": (
                    float(seed.get("frequency", 0.0))
                    if not pd.isna(seed.get("frequency", np.nan))
                    else 0.0
                ),
                "score": (
                    float(seed.get("score", 0.0))
                    if not pd.isna(seed.get("score", np.nan))
                    else 0.0
                ),
                "role": role,
                "seed_hex": str(seed.get("hex", "")),
                "hex": (
                    str(seed.get("hex", ""))
                    if isinstance(seed.get("hex", ""), str)
                    else lab_to_rgb_hex(
                        float(seed["L"]), float(seed["a"]), float(seed["b"])
                    )
                ),
                "derived": False,
                "element": elem,
            }

            # Enforce cool_min_deltal if we had to fallback
            if role == "accent_cool" and base_L is not None:
                if float(row["L"]) < float(base_L) + float(cool_min_deltal):
                    # refuse to create a too-dark cool accent
                    continue

            if row["hex"] in used_hex:
                continue

            assignments[elem] = row
            used_hex.add(row["hex"])

    # Best-effort structural enforcement after fill
    enforce_structural_L(assignments, pc)

    # Output
    out = {
        "palette": palette,
        "assigned": {k: v for k, v in assignments.items()},
        "missing": [e for e in all_elems if e not in assignments],
    }
    return out


# ============================================================
# CLI
# ============================================================


@click.command()
@click.option(
    "--assignments-json",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
)
@click.option(
    "--color-pool-csv",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
)
@click.option(
    "--constraints-json",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
)
@click.option(
    "--out-json",
    type=click.Path(dir_okay=False, path_type=Path),
    default=Path("assignments_polished.json"),
    show_default=True,
)
@click.option(
    "--out-lua", type=click.Path(dir_okay=False, path_type=Path), default=None
)
@click.option("--theme-name", default="painting", show_default=True)
@click.option(
    "--no-render", is_flag=True, default=False, help="Disable rich table output."
)
@click.option(
    "--cool-min-deltal",
    default=24.0,
    show_default=True,
    type=float,
    help="Minimum L* separation from base for accent_cool (enforces L >= base.L + this).",
)
@click.option(
    "--cool-rank-floor",
    default=0.60,
    show_default=True,
    type=float,
    help="Percentile floor for accent_cool ranks (deltaE_bg_rank / abs_deltaL_bg_rank) when available.",
)
def main(
    assignments_json: Path,
    color_pool_csv: Path,
    constraints_json: Path,
    out_json: Path,
    out_lua: Optional[Path],
    theme_name: str,
    no_render: bool,
    cool_min_deltal: float,
    cool_rank_floor: float,
):
    assignments_in = json.loads(assignments_json.read_text())
    pool = pd.read_csv(color_pool_csv)

    constraints_all = json.loads(constraints_json.read_text())
    palette = assignments_in.get("palette")
    if palette is None and "palette" in pool.columns:
        palette = str(pool["palette"].iloc[0])

    if palette is None:
        raise click.ClickException(
            "Could not determine palette from assignments.json or color_pool.csv"
        )

    pc = PaletteConstraints(
        deltaL=constraints_all["constraints"]["deltaL"][palette],
        chroma=constraints_all["constraints"]["chroma"][palette],
        hue=constraints_all["constraints"]["hue"][palette],
    )

    if "palette" in pool.columns:
        pool = pool[pool["palette"] == palette].copy()

    out = polish(
        assignments_in,
        pool,
        pc,
        cool_min_deltal=cool_min_deltal,
        cool_rank_floor=cool_rank_floor,
    )

    out_json.write_text(json.dumps(out, indent=2))

    if not no_render:
        render_table(out["assigned"], theme_name)

    if out_lua is not None:
        write_lua(out["assigned"], out_lua, theme_name)


if __name__ == "__main__":
    main()
