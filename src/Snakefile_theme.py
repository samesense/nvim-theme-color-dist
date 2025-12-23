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
            --out-csv {output.colors}
        """

# rule assign_roles:
#     input:
#         colors = INT / "tmp/{img}_colors.csv",
#         catppuccin = RAW / 'nvim/lua/catppuccin/palettes/mocha.csv',
#     output:
#         assignment = INT / "tmp/{img}_role_assignment.csv"
#     params:
#         palette='mocha',
#     shell:
#         """
#         python assign_roles.py \
#             {input.colors} \
#             {input.catppuccin} \
#             {output} \
#             --palette {params.palette}
#         """

rule assign_elements:
    input:
        colors = INT / "tmp/{img}_colors.csv",
        cons = INT / "constraints/palette_constraints.json",
    output:
        INT / "assign/{img}.json",
    params:
        tname = "{img}_theme",
    shell:
        """
        python assign_elements.py \
            {input.colors} \
            --constraints-json {input.cons} \
            --theme-name {params.tname} \
            --out-json {output}
        """

rule fill_elements:
    input:
        colors = INT / "tmp/{img}_colors.csv",
        cons = INT / "constraints/palette_constraints.json",
        filled = INT / "assign/{img}.json",
    output:
        luaout = END / "{img}_theme.lua",
    params:
        tname = "{img}_theme",
    shell:
        """
        python fill_gaps.py \
            --assignments-json {input.filled} \
            --color-pool-csv {input.colors} \
            --constraints-json {input.cons} \
            --out-lua {output} \
            --theme-name {params.tname}
        """
