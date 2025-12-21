include: "Snakefile_const.py"
include: "Snakefile_theme.py"

PALETTE = "mocha"
CATPPUCCIN_DIST = "catppuccin/mocha.csv"
IMGS = ('abstractBoxes', 'blueMosqueCeil', 'forest',)

rule all:
    input:
        expand(END / "{img}_theme.lua", img=IMGS),
