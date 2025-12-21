import json
import re
from pathlib import Path

import click

# ------------------------------------------------------------
# Lua parsing
# ------------------------------------------------------------

LUA_KV_RE = re.compile(r"(\w+)\s*=\s*'(#?[0-9a-fA-F]{6})'")


def parse_lua_theme(path: Path) -> dict[str, str]:
    """
    Parse a Catppuccin-style Lua theme table into:
    { element: "#rrggbb" }
    """
    colors = {}
    text = path.read_text()

    for key, val in LUA_KV_RE.findall(text):
        if not val.startswith("#"):
            val = f"#{val}"
        colors[key] = val.lower()

    return colors


# ------------------------------------------------------------
# Normalization / structure
# ------------------------------------------------------------

CORE_UI_KEYS = [
    "base",
    "surface0",
    "surface1",
    "surface2",
    "overlay0",
    "overlay1",
    "overlay2",
    "text",
    "subtext1",
    "subtext0",
]

ACCENT_GROUPS = {
    "red": ["rosewater", "flamingo", "pink", "red", "maroon"],
    "warm": ["peach", "yellow", "green"],
    "cool": ["teal", "sky", "sapphire", "blue", "lavender"],
    "bridge": ["mauve"],
}


def normalize_theme(colors: dict[str, str]) -> dict:
    """
    Convert flat color dict into structured JSON:
    {
      core: { base, surface*, overlay*, text* },
      accents: { red[], warm[], cool[], bridge[] }
    }
    """
    core = {k: colors[k] for k in CORE_UI_KEYS if k in colors}

    accents = {}
    for group, keys in ACCENT_GROUPS.items():
        vals = [colors[k] for k in keys if k in colors]
        if vals:
            accents[group] = vals

    return {
        "core": core,
        "accents": accents,
    }


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
    default="../docs/themes.json",
    show_default=True,
    type=click.Path(path_type=Path),
)
def export_themes(theme_dir: Path, out: Path):
    """
    Export *_theme.lua files into a single themes.json
    for GitHub Pages rendering.
    """
    lua_files = sorted(theme_dir.glob("*.lua"))
    if not lua_files:
        raise click.ClickException("No .lua files found")

    data = {}

    for lua in lua_files:
        name = lua.stem.replace("_theme", "")
        raw = parse_lua_theme(lua)
        data[name] = normalize_theme(raw)

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=2))
    click.echo(f"✓ Wrote {out} ({len(data)} themes)")


if __name__ == "__main__":
    export_themes()
