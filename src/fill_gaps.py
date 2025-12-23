from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Tuple

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

PAIR_BG_TEXT = "background→text"
PAIR_BG_SURF = "background→surface"
PAIR_SURF_OVER = "surface→overlay"
PAIR_OVER_TEXT = "overlay→text"

# element -> role reverse map
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
    # lab2rgb expects shape (...,3) with L* in [0,100]
    lab = np.array([[[L, a, b]]], dtype=float)
    rgb = lab2rgb(lab)[0, 0, :]  # floats 0..1 (may slightly exceed)
    rgb = np.clip(rgb, 0.0, 1.0)
    r, g, bb = (rgb * 255.0 + 0.5).astype(int)
    return f"#{r:02x}{g:02x}{bb:02x}"


def delta_e_lab(r1: Dict[str, float], r2: Dict[str, float]) -> float:
    v1 = np.array([r1["L"], r1["a"], r1["b"]], dtype=float)
    v2 = np.array([r2["L"], r2["a"], r2["b"]], dtype=float)
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
    # assignments.json stores _asdict() from itertuples; ensure key names exist
    out = dict(d)
    # unify: allow L/a/b named or L_/a_/b_
    for k in ["L", "a", "b", "chroma", "hue", "frequency", "score", "R", "G", "B"]:
        if k not in out and k.capitalize() in out:
            out[k] = out[k.capitalize()]
    # ensure floats
    for k in ["L", "a", "b", "chroma", "hue", "frequency", "score"]:
        if k in out and out[k] is not None:
            out[k] = float(out[k])
    for k in ["R", "G", "B"]:
        if k in out and out[k] is not None:
            out[k] = int(out[k])
    return out


def element_hex(row: Dict[str, Any]) -> str:
    if "hex" in row and isinstance(row["hex"], str) and row["hex"].startswith("#"):
        return row["hex"]
    if all(k in row for k in ["R", "G", "B"]):
        return f"#{int(row['R']):02x}{int(row['G']):02x}{int(row['B']):02x}"
    # fall back: compute from Lab
    return lab_to_rgb_hex(float(row["L"]), float(row["a"]), float(row["b"]))


# ============================================================
# Nudge logic
# ============================================================


def nudge_into_role(
    row: Dict[str, Any],
    role: str,
    pc: PaletteConstraints,
    *,
    relax: bool,
) -> Dict[str, Any]:
    """
    Return a *new* row dict with Lab/hex nudged toward palette constraints for role.
    Operates in LCh for hue/chroma changes.
    """
    L0, a0, b0 = float(row["L"]), float(row["a"]), float(row["b"])
    L, C, h = lab_to_lch(L0, a0, b0)

    # --- chroma target band ---
    if role in pc.chroma:
        q25 = pc.chroma_q25(role)
        q75 = pc.chroma_q75(role)
        if relax:
            # widen band if we're desperate
            q25 = max(0.0, q25 - 8.0)
            q75 = q75 + 8.0

        if C < q25:
            C = q25
        elif C > q75:
            C = q75

    # --- hue window for accents only ---
    hc = pc.hue_center(role)
    hw = pc.hue_width(role)
    if hc is not None and hw is not None:
        half = (hw / 2.0) * (1.3 if relax else 1.0)
        if circ_dist_deg(h, hc) > half:
            # move hue to nearest edge of window (or center if relax)
            if relax:
                h = hc
            else:
                # snap to boundary in shortest direction
                # choose direction sign
                d = ((h - hc + 180) % 360) - 180  # signed in [-180,180)
                h = (hc + math.copysign(half, d)) % 360.0

    # keep L within sane bounds; do not constrain L to role here (handled by structural step)
    L = clamp(L, 0.0, 100.0)

    L2, a2, b2 = lch_to_lab(L, C, h)
    out = dict(row)
    out["L"], out["a"], out["b"] = float(L2), float(a2), float(b2)
    out["chroma"], out["hue"] = lab_to_lch(out["L"], out["a"], out["b"])[1:]
    out["hex"] = lab_to_rgb_hex(out["L"], out["a"], out["b"])
    out["derived"] = True
    return out


def pick_best_candidate(
    pool: pd.DataFrame,
    *,
    role: str,
    used_hex: set[str],
    pc: PaletteConstraints,
    relax: bool,
) -> Optional[Dict[str, Any]]:
    """
    Choose a seed extracted color (row) to use for the given role.
    If role-specific pool is empty, fall back to entire pool.
    """
    sub = pool[~pool["hex"].isin(used_hex)].copy()
    if sub.empty:
        return None

    # prefer same role, but allow fallback
    sub_role = sub[sub["role"] == role].copy()
    if not sub_role.empty:
        sub = sub_role

    # optional hue window preference for accents
    hc = pc.hue_center(role)
    hw = pc.hue_width(role)
    if hc is not None and hw is not None:
        half = (hw / 2.0) * (1.3 if relax else 1.0)
        sub["hue_dist"] = sub["hue"].apply(lambda x: circ_dist_deg(float(x), float(hc)))
        inwin = sub[sub["hue_dist"] <= half].copy()
        if not inwin.empty:
            sub = inwin

    # score: high frequency + high extractor score
    sort_cols = []
    if "frequency" in sub.columns:
        sort_cols.append("frequency")
    if "score" in sub.columns:
        sort_cols.append("score")

    if sort_cols:
        sub = sub.sort_values(sort_cols, ascending=[False] * len(sort_cols))

    return sub.iloc[0].to_dict()


# ============================================================
# Structural polish (best-effort)
# ============================================================


def enforce_structural_L(
    assign: Dict[str, Dict[str, Any]], pc: PaletteConstraints
) -> None:
    """
    Best-effort nudge of L* for base/surface1/overlay1/text to satisfy ordering + ΔL mins.
    Does not change hue/chroma except through Lab recompose at same a,b.
    """
    needed = ["base", "surface1", "overlay1", "text"]
    if not all(k in assign for k in needed):
        return

    base = assign["base"]
    surf = assign["surface1"]
    over = assign["overlay1"]
    text = assign["text"]

    # start from current L values
    Lb, Ls, Lo, Lt = (
        float(base["L"]),
        float(surf["L"]),
        float(over["L"]),
        float(text["L"]),
    )

    # enforce strict ordering with tiny gaps
    eps = 1.0
    Ls = max(Ls, Lb + eps)
    Lo = max(Lo, Ls + eps)
    Lt = max(Lt, Lo + eps)

    # enforce ΔL mins using palette constraints
    min_bt = pc.deltaL_min(PAIR_BG_TEXT)
    min_bs = pc.deltaL_min(PAIR_BG_SURF)
    min_so = pc.deltaL_min(PAIR_SURF_OVER)
    min_ot = pc.deltaL_min(PAIR_OVER_TEXT)

    # push upwards in a single pass
    if (Lt - Lb) < min_bt:
        Lt = Lb + min_bt
    if (Ls - Lb) < min_bs:
        Ls = Lb + min_bs
    if (Lo - Ls) < min_so:
        Lo = Ls + min_so
    if (Lt - Lo) < min_ot:
        Lt = Lo + min_ot

    # clamp
    Lb = clamp(Lb, 0.0, 100.0)
    Ls = clamp(Ls, 0.0, 100.0)
    Lo = clamp(Lo, 0.0, 100.0)
    Lt = clamp(Lt, 0.0, 100.0)

    # write back (keep a,b fixed)
    for key, newL in [("base", Lb), ("surface1", Ls), ("overlay1", Lo), ("text", Lt)]:
        r = assign[key]
        r["L"] = float(newL)
        r["hex"] = lab_to_rgb_hex(float(r["L"]), float(r["a"]), float(r["b"]))
        # refresh derived metrics
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
    # only write elements that exist
    lines = []
    lines.append(f"local {theme_name} = {{")
    for role in ROLE_ORDER[::-1]:  # background last in ROLE_ORDER; order not critical
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
) -> Dict[str, Any]:
    """
    Fill missing elements by selecting extracted colors and nudging them into constraint windows.
    Always returns a dict with 16 elements present (some may be derived).
    """
    assigned_raw = assignments_in.get("assigned", {})
    palette = assignments_in.get("palette")

    assignments: Dict[str, Dict[str, Any]] = {
        k: normalize_assignment_row(v) for k, v in assigned_raw.items()
    }
    # Ensure hex present for used tracking
    for k, v in assignments.items():
        v["hex"] = v.get("hex") or element_hex(v)
        v.setdefault("derived", bool(v.get("derived", False)))

    # pool normalization
    pool = pool.copy()
    if "hex" not in pool.columns:
        raise click.ClickException("color_pool.csv must contain a 'hex' column")
    if "role" not in pool.columns:
        raise click.ClickException("color_pool.csv must contain a 'role' column")
    for c in ["L", "a", "b", "chroma", "hue", "frequency", "score"]:
        if c in pool.columns:
            pool[c] = pd.to_numeric(pool[c], errors="coerce")

    # Fill missing elements in a stable order: core UI first then accents
    all_elems = [e for r in ROLE_ORDER for e in ELEMENTS_BY_ROLE[r]]
    used_hex = {assignments[e]["hex"] for e in assignments if "hex" in assignments[e]}

    # two-pass strategy: strict then relaxed
    for relax in [False, True]:
        for elem in all_elems:
            if elem in assignments:
                continue
            role = ROLE_BY_ELEMENT[elem]

            seed = pick_best_candidate(
                pool, role=role, used_hex=used_hex, pc=pc, relax=relax
            )
            if seed is None:
                continue

            # Ensure seed has Lab fields
            need = ["L", "a", "b"]
            if any(k not in seed or pd.isna(seed[k]) for k in need):
                continue

            # Create derived color nudged into role constraints
            seed_row = {
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
                "seed_hex": str(seed.get("hex")),
            }
            nudged = nudge_into_role(seed_row, role, pc, relax=relax)

            # uniqueness: if collision, perturb hue slightly in relaxed pass
            if nudged["hex"] in used_hex and relax:
                L, C, h = lab_to_lch(nudged["L"], nudged["a"], nudged["b"])
                for dh in [8, -8, 16, -16, 24, -24]:
                    L2, a2, b2 = lch_to_lab(L, C, (h + dh) % 360.0)
                    hx = lab_to_rgb_hex(L2, a2, b2)
                    if hx not in used_hex:
                        nudged["L"], nudged["a"], nudged["b"] = L2, a2, b2
                        nudged["hex"] = hx
                        nudged["chroma"], nudged["hue"] = lab_to_lch(L2, a2, b2)[1:]
                        break

            if nudged["hex"] in used_hex:
                continue

            nudged["element"] = elem
            assignments[elem] = nudged
            used_hex.add(nudged["hex"])

        # If we completed all, stop
        if all(e in assignments for e in all_elems):
            break

    # If still missing, derive from closest assigned element in Lab and force-fill
    missing = [e for e in all_elems if e not in assignments]
    if missing:
        # choose reference set among existing assignments
        assigned_list = list(assignments.items())
        for elem in missing:
            role = ROLE_BY_ELEMENT[elem]
            # pick closest in Lab (or just first)
            if assigned_list:
                ref_elem, ref = min(
                    assigned_list,
                    key=lambda kv: delta_e_lab(
                        kv[1], kv[1]
                    ),  # placeholder to satisfy typing
                )
                # actually choose by similarity to role center is complex; we just use highest frequency assigned
                ref = max(
                    (v for _, v in assigned_list),
                    key=lambda v: float(v.get("frequency", 0.0)),
                )
            else:
                # last resort: neutral gray
                ref = {"L": 50.0, "a": 0.0, "b": 0.0, "frequency": 0.0, "score": 0.0}

            base = dict(ref)
            base["role"] = role
            base["seed_hex"] = base.get("hex", "")
            base = nudge_into_role(base, role, pc, relax=True)

            # ensure uniqueness by hue perturb
            if base["hex"] in used_hex:
                L, C, h = lab_to_lch(base["L"], base["a"], base["b"])
                for dh in range(15, 181, 15):
                    for sign in [1, -1]:
                        hh = (h + sign * dh) % 360.0
                        L2, a2, b2 = lch_to_lab(L, C, hh)
                        hx = lab_to_rgb_hex(L2, a2, b2)
                        if hx not in used_hex:
                            base["L"], base["a"], base["b"] = L2, a2, b2
                            base["hex"] = hx
                            base["chroma"], base["hue"] = lab_to_lch(L2, a2, b2)[1:]
                            break
                    if base["hex"] not in used_hex:
                        break

            base["element"] = elem
            base["derived"] = True
            assignments[elem] = base
            used_hex.add(base["hex"])

    # Best-effort structural enforcement after fill
    enforce_structural_L(assignments, pc)

    # output payload
    out = {
        "palette": palette,
        "assigned": {k: v for k, v in assignments.items()},
        "missing": [],
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
def main(
    assignments_json: Path,
    color_pool_csv: Path,
    constraints_json: Path,
    out_json: Path,
    out_lua: Optional[Path],
    theme_name: str,
    no_render: bool,
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

    # ensure pool has palette-consistent rows
    if "palette" in pool.columns:
        pool = pool[pool["palette"] == palette].copy()

    out = polish(assignments_in, pool, pc)
    out_json.write_text(json.dumps(out, indent=2))

    if not no_render:
        render_table(out["assigned"], theme_name)

    if out_lua is not None:
        write_lua(out["assigned"], out_lua, theme_name)


if __name__ == "__main__":
    main()
