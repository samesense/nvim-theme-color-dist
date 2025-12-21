#!/usr/bin/env python3
import re
from pathlib import Path

import click

# ------------------------------------------------------------
# Config
# ------------------------------------------------------------

ROLE_GROUPS = [
    ("Background", ["base", "mantle", "crust"]),
    ("Surface", ["surface0", "surface1", "surface2"]),
    ("Overlay", ["overlay0", "overlay1", "overlay2"]),
    ("Text", ["text", "subtext1", "subtext0"]),
    ("Accent Red", ["rosewater", "flamingo", "pink", "red", "maroon"]),
    ("Accent Warm", ["peach", "yellow", "green"]),
    ("Accent Cool", ["teal", "sky", "sapphire", "blue", "lavender"]),
    ("Accent Bridge", ["mauve"]),
]

LUA_KV_RE = re.compile(r"(\w+)\s*=\s*'(#?[0-9a-fA-F]{6})'")


# ------------------------------------------------------------
# Parsing
# ------------------------------------------------------------


def parse_lua_theme(path: Path) -> dict[str, str]:
    colors = {}
    for k, v in LUA_KV_RE.findall(path.read_text()):
        colors[k] = v.lower() if v.startswith("#") else f"#{v.lower()}"
    return colors


# ------------------------------------------------------------
# Rendering helpers
# ------------------------------------------------------------


def html_swatch(hex_color: str) -> str:
    return (
        f'<div style="'
        f"width: 3rem; "
        f"height: 1.2rem; "
        f"background: {hex_color}; "
        f"border-radius: 4px; "
        f"border: 1px solid #00000020;"
        f'"></div>'
    )


def render_role_table(title: str, elements: list[str], colors: dict[str, str]) -> str:
    rows = []

    for elem in elements:
        if elem not in colors:
            continue
        hex_color = colors[elem]
        rows.append(
            f"<tr>"
            f"<td><code>{elem}</code></td>"
            f"<td><code>{hex_color}</code></td>"
            f"<td>{html_swatch(hex_color)}</td>"
            f"</tr>"
        )

    if not rows:
        return ""

    return "\n".join(
        [
            f"### {title}",
            "",
            "<table>",
            "<thead>",
            "<tr><th>Element</th><th>Hex</th><th>Preview</th></tr>",
            "</thead>",
            "<tbody>",
            *rows,
            "</tbody>",
            "</table>",
            "",
        ]
    )


def render_theme(theme_name: str, colors: dict[str, str]) -> str:
    out = [f"## 🎨 {theme_name}", ""]

    for title, elems in ROLE_GROUPS:
        block = render_role_table(title, elems, colors)
        if block:
            out.append(block)

    return "\n".join(out)


# ------------------------------------------------------------
# CLI
# ------------------------------------------------------------


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
    """
    Render *_theme.lua files into a GitHub-friendly theme gallery
    using Catppuccin-style HTML tables.
    """
    lua_files = sorted(theme_dir.glob("*.lua"))
    if not lua_files:
        raise click.ClickException("No .lua files found")

    md = [
        "# Theme Gallery",
        "",
        f"_Auto-generated from `{theme_dir}`_",
        "",
    ]

    for lua in lua_files:
        colors = parse_lua_theme(lua)
        theme_name = lua.stem.replace("_theme", "")
        md.append(render_theme(theme_name, colors))

    out.write_text("\n".join(md))
    click.echo(f"✓ Wrote {out}")


if __name__ == "__main__":
    render_themes()
