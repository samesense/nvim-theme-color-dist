import re
from pathlib import Path

import click

# ============================================================
# Catppuccin-style grouping
# ============================================================

CORE_UI = [
    ("Background", "base"),
    ("Surface", "surface1"),
    ("Overlay", "overlay1"),
    ("Text", "text"),
]

ACCENTS = [
    ("rosewater", "Accent Red"),
    ("flamingo", "Accent Red"),
    ("pink", "Accent Red"),
    ("red", "Accent Red"),
    ("maroon", "Accent Red"),
    ("peach", "Accent Warm"),
    ("yellow", "Accent Warm"),
    ("green", "Accent Warm"),
    ("teal", "Accent Cool"),
    ("sky", "Accent Cool"),
    ("sapphire", "Accent Cool"),
    ("blue", "Accent Cool"),
    ("lavender", "Accent Cool"),
    ("mauve", "Accent Bridge"),
]

LUA_KV_RE = re.compile(r"(\w+)\s*=\s*'(#?[0-9a-fA-F]{6})'")

# ============================================================
# Parsing
# ============================================================


def parse_lua_theme(path: Path) -> dict[str, str]:
    colors = {}
    for k, v in LUA_KV_RE.findall(path.read_text()):
        colors[k] = v.lower() if v.startswith("#") else f"#{v.lower()}"
    return colors


# ============================================================
# GitHub-safe HTML helpers (THIS IS THE KEY)
# ============================================================


def swatch_td(hex_color: str) -> str:
    """
    GitHub-safe:
    - uses bgcolor attribute (NOT CSS)
    - non-empty cell
    - padding for size
    """
    return (
        f'<td bgcolor="{hex_color}" '
        f'style="padding:0.6rem 1.2rem; border-radius:4px; border:1px solid #00000020;">'
        f"&nbsp;</td>"
    )


def palette_strip(colors: dict[str, str]) -> str:
    blocks = []
    for hex_color in colors.values():
        blocks.append(
            f"<span "
            f'style="display:inline-block; width:16px; height:16px; '
            f"background:{hex_color}; border-radius:3px; "
            f'border:1px solid #00000020; margin-right:4px;"></span>'
        )
    return "".join(blocks)


# ============================================================
# Rendering
# ============================================================


def render_core_table(colors: dict[str, str]) -> str:
    rows = []
    for label, key in CORE_UI:
        if key not in colors:
            continue
        rows.append(
            "<tr>"
            f"<td><code>{label}</code></td>"
            f"<td><code>{colors[key]}</code></td>"
            f"{swatch_td(colors[key])}"
            "</tr>"
        )

    return "\n".join(
        [
            "<table>",
            "<thead>",
            "<tr><th>Role</th><th>Hex</th><th>Preview</th></tr>",
            "</thead>",
            "<tbody>",
            *rows,
            "</tbody>",
            "</table>",
        ]
    )


def render_accent_table(colors: dict[str, str]) -> str:
    rows = []
    for elem, group in ACCENTS:
        if elem not in colors:
            continue
        rows.append(
            "<tr>"
            f"<td><code>{elem}</code></td>"
            f"<td>{group}</td>"
            f"<td><code>{colors[elem]}</code></td>"
            f"{swatch_td(colors[elem])}"
            "</tr>"
        )

    return "\n".join(
        [
            "<table>",
            "<thead>",
            "<tr><th>Element</th><th>Group</th><th>Hex</th><th>Preview</th></tr>",
            "</thead>",
            "<tbody>",
            *rows,
            "</tbody>",
            "</table>",
        ]
    )


def render_theme(name: str, colors: dict[str, str]) -> str:
    return "\n".join(
        [
            f"## 🎨 {name}",
            "",
            palette_strip(colors),
            "",
            "### Core UI",
            "",
            render_core_table(colors),
            "",
            "### Accents",
            "",
            render_accent_table(colors),
            "",
        ]
    )


# ============================================================
# CLI
# ============================================================


@click.command()
@click.argument(
    "theme_dir",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
)
@click.option(
    "--out",
    default="themes.md",
    show_default=True,
    type=click.Path(path_type=Path),
)
def render_themes(theme_dir: Path, out: Path):
    lua_files = sorted(theme_dir.glob("*.lua"))
    if not lua_files:
        raise click.ClickException("No .lua files found")

    md = [
        "# Theme Gallery",
        "",
        "_Auto-generated. GitHub-first rendering (Catppuccin style)._",
        "",
    ]

    for lua in lua_files:
        colors = parse_lua_theme(lua)
        name = lua.stem.replace("_theme", "")
        md.append(render_theme(name, colors))

    out.write_text("\n".join(md))
    click.echo(f"✓ Wrote {out}")


if __name__ == "__main__":
    render_themes()
