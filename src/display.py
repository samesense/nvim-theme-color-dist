import re
import urllib.parse
from pathlib import Path

import click

# ============================================================
# Grouping
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


def render_source_image(
    theme_name: str,
    out_file: Path,
    photos_dir: Path = Path("data/raw/photos"),
) -> str:
    img_path = photos_dir / f"{theme_name}.png"
    if not img_path.exists():
        return "_Source image not found._"

    # Compute path relative to docs/themes.md
    rel = img_path.relative_to(out_file.parent.resolve())

    return (
        "<div>"
        f"<img src='{rel.as_posix()}' "
        "alt='Source image' "
        "style='max-width: 640px; width: 100%; border-radius: 6px;' />"
        "</div>"
    )


def parse_lua_theme(path: Path) -> dict[str, str]:
    colors = {}
    for k, v in LUA_KV_RE.findall(path.read_text()):
        colors[k] = v.lower() if v.startswith("#") else f"#{v.lower()}"
    return colors


# ============================================================
# SVG swatch (GitHub-proof)
# ============================================================


def svg_swatch(hex_color: str) -> str:
    svg = f"""
<svg xmlns='http://www.w3.org/2000/svg' width='48' height='16'>
  <rect width='48' height='16' rx='4' ry='4' fill='{hex_color}' />
</svg>
""".strip()

    encoded = urllib.parse.quote(svg)
    return f'<img src="data:image/svg+xml;utf8,{encoded}" />'


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
            f"<td>{svg_swatch(colors[key])}</td>"
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
            f"<td>{svg_swatch(colors[elem])}</td>"
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


def render_theme(name: str, colors: dict[str, str], out_file: Path) -> str:
    return "\n".join(
        [
            f"## 🎨 {name}",
            "",
            "### Source image",
            "",
            render_source_image(name, out_file),
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
        "_Auto-generated. GitHub-safe SVG swatches._",
        "",
    ]

    for lua in lua_files:
        colors = parse_lua_theme(lua)
        name = lua.stem.replace("_theme", "")
        md.append(render_theme(name, colors, out))

    out.write_text("\n".join(md))
    click.echo(f"✓ Wrote {out}")


if __name__ == "__main__":
    render_themes()
