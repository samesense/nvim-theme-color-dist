include: "Snakefile_const.py"
include: "Snakefile_trends.py"
include: "Snakefile_theme.py"

PALETTE = "mocha"
CATPPUCCIN_DIST = "catppuccin/mocha.csv"
IMGS = ('abstractBoxes', 'blueMosqueCeil', 'industry',)
IMGS = ('forest', 'couple', 'bull', 'witch')
IMGS = ('forest',)

rule all:
    input:
        #expand(END / "{img}_theme.lua", img=IMGS),
        END / "figures/deltaL_margins.png",
        END / "figures/chroma_by_role.png",
        END / "figures/hue.png",
        expand(INT / "tmp/{img}_colors.csv", img=IMGS),
