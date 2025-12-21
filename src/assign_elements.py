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

STRUCTURAL_ROLES = ["background", "surface", "overlay", "text"]
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

MIN_TEXT_BG_DELTA = 35.0

ACCENT_TEXT_GAP = 20.0  # must be below text
ACCENT_IDEAL_OFFSET = 30.0  # ideal L* below text
ACCENT_SOFT_WIDTH = 12.0  # softness of band
ACCENT_SOFT_WEIGHT = 0.5  # strength of pull


# ============================================================
# Geometry helpers
# ============================================================


def lab(row):
    return np.array([row["L"], row["a"], row["b"]])


def delta_e(a, b):
    return np.linalg.norm(lab(a) - lab(b))


# ============================================================
# Structural assignment
# ============================================================


def pick_structural(df):
    """
    Deterministic structural selection:
    darkest background, brightest text,
    midpoint surface/overlay.
    """
    out = {}

    bg = (
        df[df.assigned_catppuccin_role == "background"]
        .sort_values("L")
        .iloc[0]
        .to_dict()
    )

    text = (
        df[df.assigned_catppuccin_role == "text"]
        .sort_values("L", ascending=False)
        .iloc[0]
        .to_dict()
    )

    if abs(text["L"] - bg["L"]) < MIN_TEXT_BG_DELTA:
        raise RuntimeError("Text/background contrast too low after pruning")

    surface = (
        df[df.assigned_catppuccin_role == "surface"]
        .iloc[
            (
                df[df.assigned_catppuccin_role == "surface"]["L"]
                - (bg["L"] + text["L"]) / 2
            )
            .abs()
            .argsort()
        ]
        .iloc[0]
        .to_dict()
    )

    overlay = (
        df[df.assigned_catppuccin_role == "overlay"]
        .iloc[
            (
                df[df.assigned_catppuccin_role == "overlay"]["L"]
                - (surface["L"] + text["L"]) / 2
            )
            .abs()
            .argsort()
        ]
        .iloc[0]
        .to_dict()
    )

    out.update(
        {
            "base": bg,
            "surface1": surface,
            "overlay1": overlay,
            "text": text,
        }
    )

    return out


# ============================================================
# Accent assignment (with soft target band)
# ============================================================


def pick_accents(df, assignments):
    text_L = assignments["text"]["L"]
    overlay_L = assignments["overlay1"]["L"]
    ideal_L = text_L - ACCENT_IDEAL_OFFSET

    for role in ACCENT_ROLES:
        sub = df[df.assigned_catppuccin_role == role]
        if sub.empty:
            continue

        elems = CATPPUCCIN_ELEMENTS[role]
        sub = sub.sort_values("frequency", ascending=False).head(50)

        best = None
        best_score = -np.inf

        for rows in itertools.combinations(sub.to_dict("records"), len(elems)):
            # hard feasibility
            if any(r["L"] > text_L - 5 or r["L"] < overlay_L + 5 for r in rows):
                continue

            score = 0.0

            # separation inside role
            for a, b in itertools.combinations(rows, 2):
                score += delta_e(a, b)

            for r in rows:
                score -= 0.3 * delta_e(r, assignments["text"])
                score -= 0.2 * delta_e(r, assignments["base"])

                # hard guard
                if r["L"] > text_L - ACCENT_TEXT_GAP:
                    score -= 100

                # soft target band (KEY FIX)
                dist = abs(r["L"] - ideal_L)
                score -= (dist / ACCENT_SOFT_WIDTH) ** 2 * ACCENT_SOFT_WEIGHT

            if score > best_score:
                best_score = score
                best = rows

        if best:
            assignments.update(dict(zip(elems, best)))

    return assignments


# ============================================================
# Rich display
# ============================================================


def render_elements(assignments):
    console = Console()
    table = Table(show_header=True, header_style="bold")

    table.add_column("Element", style="cyan")
    table.add_column("Hex")
    table.add_column("L*")
    table.add_column("Preview")

    for elem, row in assignments.items():
        hexc = f"#{int(row['R']):02x}{int(row['G']):02x}{int(row['B']):02x}"
        swatch = Text("      ", style=Style(bgcolor=hexc))
        table.add_row(elem, hexc, f"{row['L']:.1f}", swatch)

    console.print("\n[bold]Chosen Catppuccin Elements[/bold]\n")
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

    required = {"R", "G", "B", "L", "a", "b", "frequency", "assigned_catppuccin_role"}
    missing = required - set(df.columns)
    if missing:
        raise RuntimeError(f"Missing required columns: {missing}")

    assignments = pick_structural(df)
    assignments = pick_accents(df, assignments)

    render_elements(assignments)

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
