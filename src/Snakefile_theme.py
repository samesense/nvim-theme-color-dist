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

rule split_theme_lua:
    """
    Split generated theme lua into palette and highlight modules
    """
    input:
        theme = END / "{img}_theme.lua",
    output:
        palette = END / "{theme_pack}/palettes/{img}.lua",
    shell:
        """
        python split_theme.py \
            --in-lua {input.theme} \
            --out-palette {output.palette} \
            && stylua {output.palette}
        """

def mk_palette_reg(wc):
    img_ls = IMGS[wc.theme_pack]
    return [END / f"{wc.theme_pack}/palettes/{img}.lua" for img in img_ls]

rule build_registry:
    """
    Generate theme registry for plugin consumption
    """
    input:
        palettes = mk_palette_reg, 
    output:
        registry = END / "{theme_pack}_registry.lua",
    shell:
        """
        python build_registry.py \
            --palettes-dir {END}/{wildcards.theme_pack}/palettes \
            --out {output.registry}
        """

rule render_screenshot:
    """
    Render Neovim UI screenshot for each theme
    """
    input:
        palette = END / "{theme_pack}/palettes/{img}.lua",
        registry = END / "{theme_pack}_registry.lua",
        highlights = RAW / "lua/{theme_pack}/highlights/default.lua",
    output:
        png = DOCS / "demo/{theme_pack}/{img}.png",
    params:
        theme = "{img}",
    shell:
        """
        nvim --headless \
        -u screenshot_init.lua \
        +"lua require('savitsky').load('{wildcards.img}')" \
        +"lua __codeshot_capture('{output}')" \
        +qa!
        """
#
# rule build_docs_index:
#     """
#     Regenerate docs index with palettes and UI screenshots
#     """
#     input:
#         registry = END / "registry.lua",
#         screenshots = expand(RAW / "photos/ui/{img}.png", img=IMGS),
#     output:
#         index = DOCS / "index.html",
#     shell:
#         """
#         python build_docs.py \
#             --registry {input.registry} \
#             --screenshots-dir {RAW}/photos/ui \
#             --out {output.index}
#         """
