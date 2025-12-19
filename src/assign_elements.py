import click
import pandas as pd

CATPPUCCIN_ELEMENTS = {
    "accent_red": ["rosewater", "flamingo", "pink", "red", "maroon"],
    "accent_warm": ["peach", "yellow", "green"],
    "accent_cool": ["teal", "sky", "sapphire", "blue", "lavender"],
    "accent_bridge": ["mauve"],
    "text": ["text", "subtext1", "subtext0"],
    "overlay": ["overlay2", "overlay1", "overlay0"],
    "surface": ["surface2", "surface1", "surface0"],
    "background": ["base", "mantle", "crust"],
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


def rgb_to_hex(r, g, b):
    return f"#{int(r):02x}{int(g):02x}{int(b):02x}"


@click.command()
@click.argument("image_colors_csv", type=click.Path(exists=True))
@click.argument("role_assignment_csv", type=click.Path(exists=True))
@click.option("--out-csv", default="theme_elements.csv", show_default=True)
@click.option("--out-lua", default="theme.lua", show_default=True)
@click.option("--theme-name", default="painting_light", show_default=True)
def assign_elements(
    image_colors_csv, role_assignment_csv, out_csv, out_lua, theme_name
):
    """
    Assign concrete Catppuccin elements to colors and emit a Lua theme file.
    """

    colors = pd.read_csv(image_colors_csv)
    roles = pd.read_csv(role_assignment_csv)

    # join image_role -> catppuccin_role
    df = colors.merge(
        roles,
        left_on="role",
        right_on="image_role",
        how="inner",
    )

    assignments = []

    for cat_role in ROLE_ORDER:
        elems = CATPPUCCIN_ELEMENTS.get(cat_role)
        if not elems:
            continue

        sub = df[df.assigned_catppuccin_role == cat_role]
        if sub.empty:
            continue

        # ordering logic
        if cat_role in {"background", "surface", "overlay", "text"}:
            # darker → lighter
            sub = sub.sort_values("L")
        else:
            # accents: prefer dominance
            sub = sub.sort_values("frequency", ascending=False)

        picks = sub.head(len(elems))

        for elem, (_, row) in zip(elems, picks.iterrows()):
            assignments.append(
                {
                    "element": elem,
                    "hex": rgb_to_hex(row.R, row.G, row.B),
                    "catppuccin_role": cat_role,
                }
            )

    out_df = pd.DataFrame(assignments)

    # ---- write CSV ----
    out_df.to_csv(out_csv, index=False)
    print(f"\n✔ Wrote CSV → {out_csv}\n")
    print(out_df)

    # ---- write Lua ----
    with open(out_lua, "w") as f:
        f.write(f"local {theme_name} = {{\n")

        for cat_role in ROLE_ORDER:
            elems = CATPPUCCIN_ELEMENTS.get(cat_role, [])
            for elem in elems:
                row = out_df[out_df.element == elem]
                if row.empty:
                    continue
                hexval = row.iloc[0].hex
                f.write(f"  {elem} = '{hexval}',\n")

            f.write("\n")

        f.write("}\n\n")
        f.write(f"return {theme_name}\n")

    print(f"\n✔ Wrote Lua theme → {out_lua}\n")


if __name__ == "__main__":
    assign_elements()
