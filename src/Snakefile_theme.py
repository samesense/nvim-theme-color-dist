            # --cool-min-deltae 30 --cool-min-abs-deltal 18 --cool-soft-min-deltal 26
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
            --cool-min-deltae 24
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

def get_repo_pal(wc):
    if wc.theme_pack == 'savitsky':
        return pathlib.Path('/Users/perry/projects/savitsky.nvim/lua/savitsky/palettes/') / f"{wc.img}.lua"

def mk_repo_reg(wc):
    if wc.theme_pack == 'savitsky':
        return pathlib.Path('/Users/perry/projects/savitsky.nvim/lua/savitsky/registry.lua')

def mk_repo_demo(wc):
    if wc.theme_pack == 'savitsky':
        return pathlib.Path('/Users/perry/projects/savitsky.nvim/lua/savitsky/registry.lua')

def mk_repo_png(wc):
    if wc.theme_pack == 'savitsky':
        return pathlib.Path('/Users/perry/projects/savitsky.nvim/docs/demo/') / f'{wc.img}.png'

rule split_theme_lua:
    """
    Cp generated theme lua into plugin repo and test palette dirs 
    """
    input:
        theme = END / "{img}_theme.lua",
    output:
        palette = SRC / 'lua/{theme_pack}/palettes/{img}.lua',
    params:
        pub_lua = get_repo_pal,
    shell:
        """
        python split_theme.py \
            --in-lua {input.theme} \
            --out-palette {output.palette} \
            && stylua {output.palette} \
            && cp {output.palette} {params.pub_lua}
        """

def mk_palette_reg(wc):
    img_ls = IMGS[wc.theme_pack]
    return [SRC / f"lua/{wc.theme_pack}/palettes/{img}.lua" for img in img_ls]

rule build_registry:
    """
    Generate theme registry for plugin consumption
    """
    input:
        palettes = mk_palette_reg, 
    output:
        registry = SRC / "lua/{theme_pack}/registry.lua",
    params:
        plug_registry = mk_repo_reg,
    shell:
        """
        python build_registry.py \
            --palettes-dir {SRC}/lua/{wildcards.theme_pack}/palettes \
            --out {output.registry} && cp {output.registry} {params.plug_registry}
        """

rule render_screenshot:
    """
    Render Neovim UI screenshot for each theme
    """
    input:
        palette = SRC / "lua/{theme_pack}/palettes/{img}.lua",
        registry = SRC / "lua/{theme_pack}/registry.lua",
    output:
        png = DOCS / "demo/{theme_pack}/{img}.png",
    params:
        theme = "{img}",
        repo_png = mk_repo_png,
    shell:
        """
        RUST_BACKTRACE=1 neovide --log /tmp/neovide.log -- \
  -u "/Users/perry/projects/nvim-theme-color-dist/src/screenshot_init.lua" \
  +'lua run_screenshot([[industry]], [[/Users/perry/projects/nvim-theme-color-dist/src/extract_colors.py]], 82, [[/Users/perry/projects/nvim-theme-color-dist/docs/demo/savitsky/industry.png]])'
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
