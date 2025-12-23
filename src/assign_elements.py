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


def pick_accents(pool, assignments, constraints):
    used = {hex_from_row(v) for v in assignments.values()}

    for role in ACCENT_ROLES:
        elems = ELEMENTS_BY_ROLE[role]
        sub = pool[(pool.role == role) & (~pool.hex.isin(used))].copy()

        if sub.empty:
            continue  # optional role

        h0 = hue_center(constraints, role)
        w = hue_width(constraints, role)

        # compute hue distance
        sub["hue_dist"] = sub.hue.apply(lambda h: circ_dist(h, h0))

        # strict window first
        cand = sub[sub.hue_dist <= w / 2]

        # relax if empty
        if cand.empty:
            cand = sub

        cand = cand.sort_values(["frequency", "score"], ascending=[False, False])

        for elem in elems:
            if cand.empty:
                break

            row = cand.iloc[0]
            assignments[elem] = row
            used.add(row.hex)

            cand = cand[cand.hex != row.hex]

    return assignments


def render(assignments, name):
    console = Console()
    table = Table(title=name)

    table.add_column("Element")
    table.add_column("Hex")
    table.add_column(" ")
    table.add_column("L*")
    table.add_column("C*")
    table.add_column("Hue")

    for role in ROLE_ORDER:
        for elem in ELEMENTS_BY_ROLE[role]:
            r = assignments.get(elem)
            if r is None:
                table.add_row(elem, "[dim]—[/dim]", "", "", "", "")
                continue

            h = hex_from_row(r)
            table.add_row(
                elem,
                h,
                Text("   ", style=Style(bgcolor=h)),
                f"{r.L:.1f}",
                f"{r.chroma:.1f}",
                f"{r.hue:.0f}°",
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
def main(color_pool_csv, constraints_json, theme_name, out_json):
    pool = pd.read_csv(color_pool_csv)
    pool["hex"] = pool.apply(hex_from_row, axis=1)

    constraints_all = json.loads(Path(constraints_json).read_text())
    palette = pool.palette.iloc[0]

    constraints = {
        "deltaL": constraints_all["constraints"]["deltaL"][palette],
        "chroma": constraints_all["constraints"]["chroma"][palette],
        "hue": constraints_all["constraints"]["hue"][palette],
    }

    assignments = pick_structural(pool, constraints)
    assignments = fill_ui(pool, assignments)
    assignments = pick_accents(pool, assignments, constraints)

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
