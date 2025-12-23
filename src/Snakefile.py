include: "Snakefile_const.py"
include: "Snakefile_trends.py"
include: "Snakefile_theme.py"

PALETTE = "mocha"
CATPPUCCIN_DIST = "catppuccin/mocha.csv"
IMGS = ('abstractBoxes', 'blueMosqueCeil', 'industry',)
IMGS = ('couple', 'bull', 'witch',)
IMGS = ('blueMosqueCeil',)

# bad!!
# boxes
# witch
# bull
# ma
# forest
# couple
# industry

rule all:
    input:
        #expand(END / "{img}_theme.lua", img=IMGS),
        END / "figures/deltaL_margins.png",
        END / "figures/chroma_by_role.png",
        END / "figures/hue.png",
        expand(END / "{img}_theme.lua", img=IMGS),

onsuccess:
    shell('curl -d "colors done 🥳" ntfy.sh/perry-runs')
onerror:
    shell('curl -d "colors failed 😭" ntfy.sh/perry-runs')
