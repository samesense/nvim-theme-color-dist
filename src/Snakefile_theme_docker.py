rule extract_roles:
    '''get color clusters from png'''
    input:
        png = RAW / 'photos/{img}.png', 
        cons = INT / "constraints/palette_constraints.json",
    output:
        colors = INT / "tmp/{img}_colors.csv",
    shell:
        """
        python extract_colors.py {input.png} \
            --constraints-json {input.cons} \
            --out-csv {output.colors} \
            --palette mocha \
        """

rule assign_elements:
    input:
        colors = INT / "tmp/{img}_colors.csv",
        cons = INT / "constraints/palette_constraints.json",
    output:
        json = INT / "assign/{img}.json",
        png = END / "figures/assign/{img}.png",
    params:
        tname = "{img}_theme",
    container:
        'docker://nvim-theme-tools:py311'
    shell:
        """
        python assign_elements.py \
            {input.colors} \
            --constraints-json {input.cons} \
            --theme-name {params.tname} \
            --out-json {output.json} \
            --out-image {output.png}
        """

rule fill_elements:
    input:
        colors = INT / "tmp/{img}_colors.csv",
        cons = INT / "constraints/palette_constraints.json",
        assign = INT / "assign/{img}.json",
    output:
        lua = END / "{img}_theme.lua",
        png = END / "figures/fill/{img}.png",
    params:
        tname = "{img}_theme",
    container:
        'docker://nvim-theme-tools:py311'
    shell:
        """
        python fill_gaps.py \
            --assignments-json {input.assign} \
            --color-pool-csv {input.colors} \
            --constraints-json {input.cons} \
            --out-lua {output.lua} \
            --out-image {output.png} \
            --theme-name {params.tname}
        """
