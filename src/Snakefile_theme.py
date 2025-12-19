rule extract_roles:
    '''get color clusters from png'''
    input:
        RAW / 'photos/{img}.png', 
    output:
        colors = INT / "tmp/{img}_colors.csv",
        dendrogram = INT / "tmp/{img}_dendrogram.png",
    params:
        out_prefix = INTs + "tmp/{img}",
        num_roles = 8,
    shell:
        """
        python role_clusters.py {input} \
            --roles {params.num_roles} \
            --out-prefix {params.out_prefix}
        """

rule assign_roles:
    input:
        colors = INT / "tmp/{img}_colors.csv",
        catppuccin=RAW / 'nvim/lua/catppuccin/palettes/mocha.csv',
    output:
        assignment= INT / "tmp/{img}_role_assignment.csv"
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
        assignment= INT / "tmp/{img}_role_assignment.csv"
    output:
        theme= END / "{img}_theme.csv"
    shell:
        """
        python assign_elements.py \
            {input.colors} \
            {input.assignment} \
            --out {output.theme}
        """
