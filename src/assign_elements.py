import click
import numpy as np
import pandas as pd

CATPPUCCIN_ELEMENTS = {
    "background": ["crust", "mantle", "base"],
    "surface": ["surface0", "surface1", "surface2"],
    "overlay": ["overlay0", "overlay1", "overlay2"],
    "text": ["text", "subtext1", "subtext0"],
    "accent_cool": ["blue", "sky", "sapphire", "lavender"],
    "accent_warm": ["peach", "yellow", "green"],
    "accent_red": ["red", "maroon", "pink", "rosewater", "flamingo"],
    "accent_bridge": ["mauve"],
}


def rgb_to_hex(r, g, b):
    return f"#{int(r):02x}{int(g):02x}{int(b):02x}"


@click.command()
@click.argument("image_colors_csv", type=click.Path(exists=True))
@click.argument("role_assignment_csv", type=click.Path(exists=True))
@click.option("--out", default="theme_elements.csv")
def assign_elements(image_colors_csv, role_assignment_csv, out):
    """
    Assign concrete Catppuccin elements to colors.
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

    for cat_role, elems in CATPPUCCIN_ELEMENTS.items():
        sub = df[df.assigned_catppuccin_role == cat_role]
        if sub.empty:
            continue

        # sort by lightness (most Catppuccin roles rely on this)
        sub = sub.sort_values("L")

        if cat_role.startswith(("background", "surface", "overlay", "text")):
            # monotonic assignment
            picks = sub.head(len(elems))

        else:
            # accents: prefer frequency + spread
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
    out_df.to_csv(out, index=False)

    print("\nAssigned Catppuccin elements:\n")
    print(out_df)


if __name__ == "__main__":
    assign_elements()
