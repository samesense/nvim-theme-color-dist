#!/usr/bin/env python3
import re
from pathlib import Path

import click

# ------------------------------------------------------------
# Config
# ------------------------------------------------------------

ROLE_ORDER = [
    "background",
    "surface",
    "overlay",
    "text",
    "accent_red",
    "accent_warm",
    "accent_cool",
    "accent_bridge",
]

ROLE_ELEMENTS = {
    "background": ["base", "mantle", "crust"],
    "surface": ["surface0", "surface1", "surface2"],
    "overlay": ["overlay0", "overlay1", "overlay2"],
    "text": ["text", "subtext1", "subtext0"],
    "accent_red": ["rosewater", "flamingo", "pink", "red", "maroon"],
    "accent_warm": ["peach", "yellow", "green"],
    "accent_cool": ["teal", "sky", "sapphire", "blue", "lavender"],
    "accent_bridge": ["mauve"],
}

LUA_KV_RE = re.compile(r"(\w+)\s*=\s*'(#?[0-9a-fA-F]{6})'")

# Unicode blocks render well in Glow + GitHub
SWATCH = "██████"


# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------


def parse_lua_theme(path: Path) -> dict[str, str]:
    text = path.read_text()
    out = {}
    for k, v in LUA_KV_RE.findall(text):
        if not v.startswith("#"):
            v = f"#{v}"
        out[k] = v.lower()
    return out


def render_color_line(name: str, hex_color: str) -> str:
    return f"`{name:<10}` {SWATCH} `{hex_color}`"


def render_role(role: str, colors: dict[str, str]) -> str:
    elems = ROLE_ELEMENTS[role]
    lines = []

    for e in elems:
        if e in colors:
            lines.append(render_color_line(e, colors[e]))

    if not lines:
        return ""

    title = role.replace("_", " ").title()
    return "\n".join([f"### {title}", *lines, ""])


def render_theme(theme_name: str, colors: dict[str, str]) -> str:
    blocks = [f"## 🎨 {theme_name}", ""]

    for role in ROLE_ORDER:
        block = render_role(role, colors)
        if block:
            blocks.append(block)

    return "\n".join(blocks)


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
    Render *_theme.lua files into a Markdown theme gallery.
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
