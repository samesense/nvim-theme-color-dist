#!/usr/local/bin/python
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


def norm_hex(h: str) -> str:
    return str(h).strip().lower()


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
    return f"#{r:02x}{g:02x}{bb:02x}".lower()


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
    lightness: Dict[str, Dict[str, float]]
    chroma: Dict[str, Dict[str, float]]
    hue: Dict[str, Dict[str, float]]
    polarity: Optional[str] = None
    element_offsets: Dict[str, Dict[str, float]] = None
    accent_separation: Dict[str, Dict[str, Dict[str, float]]] = (
        None  # polarity -> role -> stats
    )

    def deltaL_min(self, pair: str) -> float:
        return float(self.deltaL[pair]["q25"])

    def deltaL_target(self, pair: str) -> float:
        return float(self.deltaL[pair]["median"])

    def chroma_q25(self, role: str) -> float:
        return float(self.chroma[role]["q25"])

    def chroma_q75(self, role: str) -> float:
        return float(self.chroma[role]["q75"])

    def chroma_relax_delta(self, role: str, fallback: float = 8.0) -> float:
        """Get learned chroma relaxation delta for a role."""
        x = self.chroma.get(role)
        if x and "relax_delta" in x:
            return float(x["relax_delta"])
        return fallback

    def lightness_q25(self, role: str) -> Optional[float]:
        x = self.lightness.get(role)
        return float(x["q25"]) if x and "q25" in x else None

    def lightness_q75(self, role: str) -> Optional[float]:
        x = self.lightness.get(role)
        return float(x["q75"]) if x and "q75" in x else None

    def lightness_relax_delta(self, role: str, fallback: float = 10.0) -> float:
        x = self.lightness.get(role)
        if x and "relax_delta" in x:
            return float(x["relax_delta"])
        return fallback

    def hue_center(self, role: str) -> Optional[float]:
        x = self.hue.get(role)
        return float(x["center"]) if x and "center" in x else None

    def hue_width(self, role: str) -> Optional[float]:
        x = self.hue.get(role)
        return float(x["width"]) if x and "width" in x else None

    def hue_relax_mult(self, role: str, fallback: float = 1.3) -> float:
        """Get learned hue window relaxation multiplier for a role."""
        x = self.hue.get(role)
        if x and "relax_mult" in x:
            return float(x["relax_mult"])
        return fallback

    def accent_min_deltal(
        self, role: str, polarity: str, fallback: float = 43.0
    ) -> float:
        """Get learned minimum L* separation for an accent role."""
        if self.accent_separation is None:
            return fallback
        pol_sep = self.accent_separation.get(polarity, {})
        role_sep = pol_sep.get(role, {})
        return abs(role_sep.get("min", fallback))


# ============================================================
# IO normalization
# ============================================================


def normalize_assignment_row(d: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(d)
    for k in [
        "L",
        "a",
        "b",
        "chroma",
        "hue",
        "frequency",
        "score",
        "R",
        "G",
        "B",
        "hex",
    ]:
        if k not in out and k.capitalize() in out:
            out[k] = out[k.capitalize()]
    for k in ["L", "a", "b", "chroma", "hue", "frequency", "score"]:
        if k in out and out[k] is not None:
            out[k] = float(out[k])
    for k in ["R", "G", "B"]:
        if k in out and out[k] is not None:
            out[k] = int(out[k])
    if "hex" in out and out["hex"] is not None:
        out["hex"] = norm_hex(out["hex"])
    return out


def element_hex(row: Dict[str, Any]) -> str:
    if "hex" in row and isinstance(row["hex"], str) and row["hex"].startswith("#"):
        return norm_hex(row["hex"])
    if all(k in row for k in ["R", "G", "B"]):
        return f"#{int(row['R']):02x}{int(row['G']):02x}{int(row['B']):02x}".lower()
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

    # lightness band (keep roles in their expected L* range)
    q25 = pc.lightness_q25(role)
    q75 = pc.lightness_q75(role)
    if q25 is not None and q75 is not None:
        if relax:
            relax_delta = pc.lightness_relax_delta(role)
            q25 = max(0.0, q25 - relax_delta)
            q75 = min(100.0, q75 + relax_delta)
        if L < q25:
            L = q25
        elif L > q75:
            L = q75

    # chroma target band (use learned relax_delta)
    if role in pc.chroma:
        q25 = pc.chroma_q25(role)
        q75 = pc.chroma_q75(role)
        if relax:
            relax_delta = pc.chroma_relax_delta(role)
            q25 = max(0.0, q25 - relax_delta)
            q75 = q75 + relax_delta

        if C < q25:
            C = q25
        elif C > q75:
            C = q75

    # hue window for accents only (use learned relax_mult)
    hc = pc.hue_center(role)
    hw = pc.hue_width(role)
    if hc is not None and hw is not None:
        relax_mult = pc.hue_relax_mult(role) if relax else 1.0
        half = (hw / 2.0) * relax_mult
        if circ_dist_deg(h, hc) > half:
            if relax:
                h = hc
            else:
                d = ((h - hc + 180) % 360) - 180
                h = (hc + math.copysign(half, d)) % 360.0

    L = clamp(L, 0.0, 100.0)

    L2, a2, b2 = lch_to_lab(L, C, h)
    out = dict(row)
    out["L"], out["a"], out["b"] = float(L2), float(a2), float(b2)
    _, C2, h2 = lab_to_lch(out["L"], out["a"], out["b"])
    out["chroma"], out["hue"] = float(C2), float(h2)
    out["hex"] = lab_to_rgb_hex(out["L"], out["a"], out["b"])
    out["derived"] = True
    return out


# ============================================================
# Foreground-safety vs background (NEW)
# ============================================================


def _base_is_dark(assignments: Dict[str, Dict[str, Any]]) -> Optional[bool]:
    if "base" not in assignments:
        return None
    return float(assignments["base"]["L"]) < 50.0


def enforce_accent_foreground_deltaL(
    assignments: Dict[str, Dict[str, Any]],
    pc: PaletteConstraints,
    *,
    roles: Tuple[str, ...] = ("accent_cool", "accent_bridge"),
    min_deltal_override: Optional[float] = None,
) -> None:
    """
    Prevent "dark blues relative to the background" (and similar) by forcing
    accent roles that are commonly used as foreground to be directionally separated
    from base in L*.

    Uses learned accent_separation constraints from PaletteConstraints, or
    min_deltal_override if provided.

    Dark theme:  accent L >= base_L + min_deltal
    Light theme: accent L <= base_L - min_deltal

    Adjusts L only; keeps a,b constant.
    """
    if "base" not in assignments:
        return
    base_L = float(assignments["base"]["L"])
    is_dark = base_L < 50.0
    polarity = "dark" if is_dark else "light"

    for role in roles:
        # Get role-specific min separation (learned or override)
        if min_deltal_override is not None:
            min_deltal = min_deltal_override
        else:
            min_deltal = pc.accent_min_deltal(role, polarity)

        for elem in ELEMENTS_BY_ROLE[role]:
            if elem not in assignments:
                continue
            r = assignments[elem]
            L = float(r["L"])
            if is_dark:
                target = base_L + min_deltal
                if L < target:
                    r["L"] = clamp(target, 0.0, 100.0)
            else:
                target = base_L - min_deltal
                if L > target:
                    r["L"] = clamp(target, 0.0, 100.0)

            r["hex"] = lab_to_rgb_hex(float(r["L"]), float(r["a"]), float(r["b"]))
            _, C, h = lab_to_lch(float(r["L"]), float(r["a"]), float(r["b"]))
            r["chroma"], r["hue"] = float(C), float(h)


# ============================================================
# Candidate selection (UPDATED)
# ============================================================


def pick_best_candidate(
    pool: pd.DataFrame,
    *,
    role: str,
    elem: str,
    used_hex: set[str],
    pc: PaletteConstraints,
    relax: bool,
    base_L: Optional[float],
    is_dark: Optional[bool],
    fg_roles: Tuple[str, ...],
    fg_min_deltal: Optional[float],
) -> Optional[Dict[str, Any]]:
    """
    Choose a seed extracted color (row) to use for the given role/element.

    New:
      - honors used_hex strictly (no duplicates)
      - for "foreground-ish" accent roles, prevents picking colors that are too close to
        (or darker than) the background in the wrong direction.
    """
    sub = pool[~pool["hex"].isin(used_hex)].copy()
    if sub.empty:
        return None

    # prefer same role, but allow fallback
    sub_role = sub[sub["role"] == role].copy()
    if not sub_role.empty:
        sub = sub_role

    # Hue window preference for accents
    hc = pc.hue_center(role)
    hw = pc.hue_width(role)
    if hc is not None and hw is not None:
        half = (hw / 2.0) * (1.3 if relax else 1.0)
        sub["hue_dist"] = sub["hue"].apply(lambda x: circ_dist_deg(float(x), float(hc)))
        inwin = sub[sub["hue_dist"] <= half].copy()
        if not inwin.empty:
            sub = inwin

    # Foreground-safety gate for accent_cool / accent_bridge (and any roles you pass)
    if (
        base_L is not None
        and is_dark is not None
        and role in fg_roles
        and "L" in sub.columns
    ):
        # Use learned value if fg_min_deltal not provided
        polarity = "dark" if is_dark else "light"
        min_deltal = (
            fg_min_deltal
            if fg_min_deltal is not None
            else pc.accent_min_deltal(role, polarity)
        )

        if is_dark:
            strict = sub[sub["L"] >= (base_L + min_deltal)].copy()
            if strict.empty and relax:
                # relaxed: at least not darker than base
                strict = sub[sub["L"] >= base_L].copy()
            if not strict.empty:
                sub = strict
        else:
            strict = sub[sub["L"] <= (base_L - min_deltal)].copy()
            if strict.empty and relax:
                strict = sub[sub["L"] <= base_L].copy()
            if not strict.empty:
                sub = strict

    # score: high frequency + high extractor score
    sort_cols = [c for c in ["frequency", "score"] if c in sub.columns]
    if sort_cols:
        sub = sub.sort_values(sort_cols, ascending=[False] * len(sort_cols))

    return sub.iloc[0].to_dict()


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

    is_dark = True
    if pc.polarity is not None:
        is_dark = pc.polarity != "light"
    else:
        is_dark = Lb < 50.0

    eps = 1.0
    min_bt = pc.deltaL_min(PAIR_BG_TEXT)
    min_bs = pc.deltaL_min(PAIR_BG_SURF)
    min_so = pc.deltaL_min(PAIR_SURF_OVER)
    min_ot = pc.deltaL_min(PAIR_OVER_TEXT)

    if is_dark:
        Ls = max(Ls, Lb + eps)
        Lo = max(Lo, Ls + eps)
        Lt = max(Lt, Lo + eps)

        if (Lt - Lb) < min_bt:
            Lt = Lb + min_bt
        if (Ls - Lb) < min_bs:
            Ls = Lb + min_bs
        if (Lo - Ls) < min_so:
            Lo = Ls + min_so
        if (Lt - Lo) < min_ot:
            Lt = Lo + min_ot
    else:
        Ls = min(Ls, Lb - eps)
        Lo = min(Lo, Ls - eps)
        Lt = min(Lt, Lo - eps)

        if (Lb - Lt) < min_bt:
            Lt = Lb - min_bt
        if (Lb - Ls) < min_bs:
            Ls = Lb - min_bs
        if (Ls - Lo) < min_so:
            Lo = Ls - min_so
        if (Lo - Lt) < min_ot:
            Lt = Lo - min_ot

    Lb, Ls, Lo, Lt = map(lambda x: clamp(x, 0.0, 100.0), [Lb, Ls, Lo, Lt])

    for key, newL in [("base", Lb), ("surface1", Ls), ("overlay1", Lo), ("text", Lt)]:
        r = assign[key]
        r["L"] = float(newL)
        r["hex"] = lab_to_rgb_hex(float(r["L"]), float(r["a"]), float(r["b"]))
        _, C, h = lab_to_lch(float(r["L"]), float(r["a"]), float(r["b"]))
        r["chroma"], r["hue"] = float(C), float(h)


def enforce_text_offsets(assign: Dict[str, Dict[str, Any]], pc: PaletteConstraints) -> None:
    if "text" not in assign:
        return

    offsets = pc.element_offsets or {}
    text = assign["text"]

    for elem, fallback in [("subtext1", -7.0), ("subtext0", -15.0)]:
        if elem not in assign:
            continue
        offset = offsets.get(f"{elem}_from_text", {}).get("value", fallback)
        target = float(text["L"]) + float(offset)
        target = clamp(target, 0.0, 100.0)
        r = assign[elem]
        r["L"] = float(target)
        r["hex"] = lab_to_rgb_hex(float(r["L"]), float(r["a"]), float(r["b"]))
        _, C, h = lab_to_lch(float(r["L"]), float(r["a"]), float(r["b"]))
        r["chroma"], r["hue"] = float(C), float(h)


# ============================================================
# Rendering
# ============================================================


def _build_table(assignments: Dict[str, Dict[str, Any]], theme_name: str) -> Table:
    """Build a Rich Table for the assignments."""
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

    return table


def render_table(assignments: Dict[str, Dict[str, Any]], theme_name: str) -> None:
    """Print table to terminal."""
    console = Console()
    table = _build_table(assignments, theme_name)
    console.print(table)


def save_table_image(
    assignments: Dict[str, Dict[str, Any]],
    theme_name: str,
    out_path: Path,
) -> None:
    """
    Save table as SVG or PNG image.

    - .svg: Native Rich export
    - .png: Requires cairosvg (pip install cairosvg)
    """
    table = _build_table(assignments, theme_name)

    # Record output to SVG
    console = Console(record=True, width=80, force_terminal=True)
    console.print(table)

    svg_content = console.export_svg(title=theme_name)

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
    fg_min_deltal: Optional[float],
    fg_roles: Tuple[str, ...],
    enforce_after_fill: bool,
) -> Dict[str, Any]:
    assigned_raw = assignments_in.get("assigned", {})
    palette = assignments_in.get("palette")

    assignments: Dict[str, Dict[str, Any]] = {
        k: normalize_assignment_row(v) for k, v in assigned_raw.items()
    }
    for v in assignments.values():
        v["hex"] = v.get("hex") or element_hex(v)
        v["hex"] = norm_hex(v["hex"])
        v.setdefault("derived", bool(v.get("derived", False)))

    pool = pool.copy()
    if "hex" not in pool.columns:
        raise click.ClickException("color_pool.csv must contain a 'hex' column")
    if "role" not in pool.columns:
        raise click.ClickException("color_pool.csv must contain a 'role' column")
    pool["hex"] = pool["hex"].map(norm_hex)

    for c in ["L", "a", "b", "chroma", "hue", "frequency", "score"]:
        if c in pool.columns:
            pool[c] = pd.to_numeric(pool[c], errors="coerce")

    # Optional: dedupe pool by hex to avoid duplicate visible colors
    sort_cols = [c for c in ["frequency", "score"] if c in pool.columns]
    if sort_cols:
        pool = pool.sort_values(sort_cols, ascending=[False] * len(sort_cols))
    pool = pool.drop_duplicates(subset=["hex"], keep="first").reset_index(drop=True)

    all_elems = [e for r in ROLE_ORDER for e in ELEMENTS_BY_ROLE[r]]
    used_hex = {
        norm_hex(assignments[e]["hex"]) for e in assignments if "hex" in assignments[e]
    }

    base_L = float(assignments["base"]["L"]) if "base" in assignments else None
    is_dark = (base_L < 50.0) if base_L is not None else None

    # two-pass strategy: strict then relaxed
    for relax in [False, True]:
        for elem in all_elems:
            if elem in assignments:
                continue
            role = ROLE_BY_ELEMENT[elem]

            seed = pick_best_candidate(
                pool,
                role=role,
                elem=elem,
                used_hex=used_hex,
                pc=pc,
                relax=relax,
                base_L=base_L,
                is_dark=is_dark,
                fg_roles=fg_roles,
                fg_min_deltal=fg_min_deltal,
            )
            if seed is None:
                continue

            need = ["L", "a", "b"]
            if any(k not in seed or pd.isna(seed[k]) for k in need):
                continue

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

            # Foreground-safety also applied to derived colors (important!)
            if base_L is not None and is_dark is not None and role in fg_roles:
                polarity = "dark" if is_dark else "light"
                min_deltal = (
                    fg_min_deltal
                    if fg_min_deltal is not None
                    else pc.accent_min_deltal(role, polarity)
                )

                Lm = float(nudged["L"])
                if is_dark:
                    target = base_L + min_deltal
                    if Lm < target:
                        nudged["L"] = clamp(target, 0.0, 100.0)
                else:
                    target = base_L - min_deltal
                    if Lm > target:
                        nudged["L"] = clamp(target, 0.0, 100.0)

                nudged["hex"] = lab_to_rgb_hex(
                    float(nudged["L"]), float(nudged["a"]), float(nudged["b"])
                )
                _, C2, h2 = lab_to_lch(
                    float(nudged["L"]), float(nudged["a"]), float(nudged["b"])
                )
                nudged["chroma"], nudged["hue"] = float(C2), float(h2)

            # uniqueness: if collision, perturb hue slightly in relaxed pass
            if norm_hex(nudged["hex"]) in used_hex and relax:
                L, C, h = lab_to_lch(nudged["L"], nudged["a"], nudged["b"])
                for dh in [8, -8, 16, -16, 24, -24, 32, -32]:
                    L2, a2, b2 = lch_to_lab(L, C, (h + dh) % 360.0)
                    hx = lab_to_rgb_hex(L2, a2, b2)
                    if norm_hex(hx) not in used_hex:
                        nudged["L"], nudged["a"], nudged["b"] = (
                            float(L2),
                            float(a2),
                            float(b2),
                        )
                        nudged["hex"] = norm_hex(hx)
                        _, C2, h2 = lab_to_lch(float(L2), float(a2), float(b2))
                        nudged["chroma"], nudged["hue"] = float(C2), float(h2)
                        break

            if norm_hex(nudged["hex"]) in used_hex:
                continue

            nudged["element"] = elem
            nudged["hex"] = norm_hex(nudged["hex"])
            assignments[elem] = nudged
            used_hex.add(norm_hex(nudged["hex"]))

        if all(e in assignments for e in all_elems):
            break

    enforce_structural_L(assignments, pc)
    enforce_text_offsets(assignments, pc)

    if enforce_after_fill:
        enforce_accent_foreground_deltaL(
            assignments,
            pc,
            roles=fg_roles,
            min_deltal_override=fg_min_deltal,
        )

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
@click.option(
    "--out-image",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Save table as image (.svg or .png). PNG requires cairosvg.",
)
@click.option("--theme-name", default="painting", show_default=True)
@click.option(
    "--no-render", is_flag=True, default=False, help="Disable rich table output."
)
@click.option(
    "--fg-min-deltal",
    default=None,
    type=float,
    help="Override learned minimum L* separation for foreground accents (default: use learned constraint).",
)
@click.option(
    "--fg-roles",
    default="accent_cool,accent_bridge",
    show_default=True,
    help="Comma-separated roles to treat as foreground-ish and enforce fg-min-deltal against base.",
)
@click.option(
    "--enforce-after-fill/--no-enforce-after-fill",
    default=True,
    show_default=True,
    help="Apply fg readability enforcement after gap filling (in addition to during selection).",
)
def main(
    assignments_json: Path,
    color_pool_csv: Path,
    constraints_json: Path,
    out_json: Path,
    out_lua: Optional[Path],
    out_image: Optional[Path],
    theme_name: str,
    no_render: bool,
    fg_min_deltal: Optional[float],
    fg_roles: str,
    enforce_after_fill: bool,
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
        lightness=constraints_all["constraints"].get("lightness", {}).get(palette, {}),
        chroma=constraints_all["constraints"]["chroma"][palette],
        hue=constraints_all["constraints"]["hue"][palette],
        polarity=constraints_all.get("polarity", {}).get(palette),
        element_offsets=constraints_all["constraints"]
        .get("element_offsets", {})
        .get(palette, {}),
        accent_separation=constraints_all["constraints"].get("accent_separation", {}),
    )

    if "palette" in pool.columns:
        pool = pool[pool["palette"] == palette].copy()

    roles_tuple = tuple(r.strip() for r in fg_roles.split(",") if r.strip())
    out = polish(
        assignments_in,
        pool,
        pc,
        fg_min_deltal=fg_min_deltal,
        fg_roles=roles_tuple,
        enforce_after_fill=enforce_after_fill,
    )
    out_json.write_text(json.dumps(out, indent=2))

    if not no_render:
        render_table(out["assigned"], theme_name)

    if out_image is not None:
        save_table_image(out["assigned"], theme_name, out_image)

    if out_lua is not None:
        write_lua(out["assigned"], out_lua, theme_name)


if __name__ == "__main__":
    main()
