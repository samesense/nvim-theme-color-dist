import re
import sys
from pathlib import Path

import click

THEME_NAME_RE = re.compile(r"^[a-zA-Z0-9_]+$")


def infer_flavour(theme_name: str) -> str:
    """
    Infer Catppuccin flavour from theme name.
    """
    lname = theme_name.lower()
    if "latte" in lname:
        return "latte"
    return "mocha"


def lua_require_path(base_module: str, path: Path) -> str:
    return f"{base_module}.{path.stem}"


def write_registry(path: Path, entries: list[str]):
    path.write_text("return {\n" + "\n".join(entries) + "\n}\n", encoding="utf-8")


@click.command(context_settings=dict(help_option_names=["-h", "--help"]))
@click.option(
    "--palettes-dir",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    required=True,
    help="Directory containing palette lua files",
)
@click.option(
    "--out",
    "out_file",
    type=click.Path(dir_okay=False, path_type=Path),
    required=True,
    help="Output registry.lua file",
)
@click.option(
    "--module",
    default="yourthemes",
    show_default=True,
    help="Lua module root for require paths",
)
def main(
    palettes_dir: Path,
    out_file: Path,
    module: str,
):
    """
    Build theme registry with a shared highlight file.
    """

    palettes = sorted(palettes_dir.glob("*.lua"))

    if not palettes:
        click.echo("[build_registry] No palette files found", err=True)
        sys.exit(1)

    entries = []

    for palette in palettes:
        name = palette.stem

        if not THEME_NAME_RE.match(name):
            click.echo(f"[build_registry] Invalid theme name: {name}", err=True)
            sys.exit(1)

        flavour = infer_flavour(name)

        palette_req = lua_require_path(f"{module}.palettes", palette)

        entry = f'  ["{name}"] = {{\n'
        entry += f'    flavour = "{flavour}",\n'
        entry += f'    palette = require("{palette_req}"),\n'
        entry += "  },"

        entries.append(entry)

    out_file.parent.mkdir(parents=True, exist_ok=True)
    write_registry(out_file, entries)


if __name__ == "__main__":
    main()
