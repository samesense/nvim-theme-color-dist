import re
import sys
from pathlib import Path

import click

PALETTE_LOCAL_RE = re.compile(
    r"""
    local\s+([a-zA-Z0-9_]+)\s*=\s*
    (\{\s*(?:.|\n)*?\})
    """,
    re.VERBOSE,
)


def extract_palette(lua_text: str):
    """
    Extract `local name = { ... }` from Lua source.
    """
    match = PALETTE_LOCAL_RE.search(lua_text)
    if not match:
        raise RuntimeError("No palette table found (expected `local name = { ... }`)")

    name = match.group(1)
    table = match.group(2).strip()
    return name, table


def write_palette(path: Path, table: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"return {table}\n", encoding="utf-8")


@click.command(context_settings=dict(help_option_names=["-h", "--help"]))
@click.option(
    "--in-lua",
    "in_lua",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
    help="Input Lua file containing a local palette table",
)
@click.option(
    "--out-palette",
    type=click.Path(dir_okay=False, path_type=Path),
    required=True,
    help="Output palette Lua module (return { ... })",
)
def main(in_lua: Path, out_palette: Path):
    """
    Extract a palette table and emit a palette-only Lua module.
    """

    try:
        lua_text = in_lua.read_text(encoding="utf-8")
    except Exception as e:
        click.echo(f"[split_theme] Failed to read input: {e}", err=True)
        sys.exit(1)

    try:
        name, table = extract_palette(lua_text)
    except RuntimeError as e:
        click.echo(f"[split_theme] ERROR: {e}", err=True)
        sys.exit(1)

    try:
        write_palette(out_palette, table)
    except Exception as e:
        click.echo(f"[split_theme] Failed to write output: {e}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
