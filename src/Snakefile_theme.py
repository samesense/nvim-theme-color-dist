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
            --constraints-json {input.cons}
        """

rule assign_roles:
    input:
        colors = INT / "tmp/{img}_colors.csv",
        catppuccin = RAW / 'nvim/lua/catppuccin/palettes/mocha.csv',
    output:
        assignment = INT / "tmp/{img}_role_assignment.csv"
    params:
        palette='mocha',
    shell:
        """
        python assign_roles.py \
            {input.colors} \
            {input.catppuccin} \
            {output} \
            --palette {params.palette}
        """

rule assign_elements:
    input:
        colors = INT / "tmp/{img}_colors.csv",
        assignment = INT / "tmp/{img}_role_assignment.csv",
        catppuccin = RAW / 'nvim/lua/catppuccin/palettes/mocha.csv',
    output:
        luaout = END / "{img}_theme.lua",
    params:
        tname = "{img}_theme",
    shell:
        """
        python assign_elements.py \
            {input.assignment} \
            --out-lua {output.luaout} \
            --theme-name {params.tname}
        """
