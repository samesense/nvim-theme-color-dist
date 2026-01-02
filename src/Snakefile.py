include: "Snakefile_const.py"
include: "Snakefile_trends.py"
include: "Snakefile_theme.py"

CATPPUCCIN_DIST = "catppuccin/mocha.csv"
#IMGS = {'savitsky': ('abstractBoxes', 'industry', 'couple', 'bull', 'witch', 'camels',)}
# bads: witch / couple
IMGS = {'savitsky': ('abstractBoxes', 'camels',)}
IMGS = {'savitsky': ( 'camels',)}

rule all:
    input:
        END / "figures/deltaL_margins.png",
        END / "figures/chroma_by_role.png",
        END / "figures/hue.png",
        expand(END / "savitsky/palettes/{img}.lua", img=IMGS['savitsky']),
        #expand(DOCS / 'demo/savitsky/{img}.png', img=IMGS['savitsky']),

onsuccess:
    shell('curl -d "colors done 🥳" ntfy.sh/perry-runs')
onerror:
    shell('curl -d "colors failed 😭" ntfy.sh/perry-runs')
