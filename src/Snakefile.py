include: "Snakefile_const.py"
include: "Snakefile_trends.py"
include: "Snakefile_mk_theme.py"
include: "Snakefile_theme.py"

CATPPUCCIN_DIST = "catppuccin/mocha.csv"
# bads: witch / couple
IMGS = {'savitsky': ('abstractBoxes', 'camels', 'bull', 'industry', 'man', 'forest', 'witch', 'couple',)}
#IMGS = {'savitsky': ('forest', 'witch', 'couple',)}
#IMGS = {'savitsky': ('witch',)}

rule all:
    input:
        #END / "figures/deltaL_margins.png",
        #END / "figures/chroma_by_role.png",
        #END / "figures/hue.png",
        #SRC / "lua/savitsky/registry.lua",
        #expand(END / "savitsky/palettes/{img}.lua", img=IMGS['savitsky']),
        expand(DOCS / "{theme_pack}_themes.json", theme_pack=('savitsky',)),
        expand(DOCS / 'demo/savitsky/{img}.png', img=IMGS['savitsky']),
        expand(END / "figures/fill/{img}_fill.png", img=IMGS['savitsky']),

onsuccess:
    shell('curl -d "colors done 🥳" ntfy.sh/perry-runs')
onerror:
    shell('curl -d "colors failed 😭" ntfy.sh/perry-runs')
