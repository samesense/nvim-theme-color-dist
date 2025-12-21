include: "Snakefile_const.py"
include: "Snakefile_theme.py"

PALETTE = "mocha"
CATPPUCCIN_DIST = "catppuccin/mocha.csv"
IMGS = ('abstractBoxes', 'blueMosqueCeil', 'industry',)
IMGS = ('forest', 'man')
IMGS = ('camels', 'bull', 'couple', 'witch')

rule all:
    input:
        expand(END / "{img}_theme.lua", img=IMGS),
