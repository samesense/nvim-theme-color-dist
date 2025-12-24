include: "Snakefile_const.py"
include: "Snakefile_trends.py"
include: "Snakefile_theme.py"

CATPPUCCIN_DIST = "catppuccin/mocha.csv"
IMGS = {'savitsky': ('abstractBoxes', 'industry', 'couple', 'bull', 'witch', 'camels',)}

rule all:
    input:
        #expand(END / "{img}_theme.lua", img=IMGS),
        END / "figures/deltaL_margins.png",
        END / "figures/chroma_by_role.png",
        END / "figures/hue.png",
        #expand(END / "{img}_theme.lua", img=IMGS),
        expand(END / "{theme_pack}_registry.lua", theme_pack=IMGS),

onsuccess:
    shell('curl -d "colors done 🥳" ntfy.sh/perry-runs')
onerror:
    shell('curl -d "colors failed 😭" ntfy.sh/perry-runs')
