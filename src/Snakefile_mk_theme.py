rule mk_theme_nf:
    input:
        png = RAW / 'photos/{img}.png', 
        cons = INT / "constraints/palette_constraints.json",
    output:
        assign_png = END / "figures/assign/{img}_assign.png",
        lua = END / "{img}_theme.lua",
        fill_png = END / "figures/fill/{img}_fill.png",
    shell:
        'nextflow run theme.nf --img {wildcards.img}'
