include: "Snakefile_const.py"
include: "Snakefile_theme.py"

#IMAGE = "images/blue_mosque_ceil.jpeg"
PALETTE = "mocha"
CATPPUCCIN_DIST = "catppuccin/mocha.csv"
IMGS = ('abstractBoxes',)

rule all:
    input:
        expand(END / "{img}_theme.lua", img=IMGS),
