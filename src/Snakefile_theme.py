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

def mk_repo_json(wc):
    if wc.theme_pack == 'savitsky':
        # /Users/perry/projects/savitsky.nvim/docs/themes.json
        return pathlib.Path('/Users/perry/projects/savitsky.nvim/docs/themes.json')

rule split_theme_lua:
    """
    Cp generated theme lua into plugin repo and test palette dirs
    """
    input:
        lua = END / "{img}_theme.lua",
    output:
        palette = SRC / 'lua/{theme_pack}/palettes/{img}.lua',
    params:
        pub_lua = get_repo_pal,
    shell:
        """
        python split_theme.py \
            --in-lua {input.lua} \
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
+'lua run_screenshot([[{wildcards.img}]], [[/Users/perry/projects/nvim-theme-color-dist/src/bin/extract_colors.py]], 82, [[/Users/perry/projects/nvim-theme-color-dist/docs/demo/{wildcards.theme_pack}/{wildcards.img}.png]])' && cp /Users/perry/projects/nvim-theme-color-dist/docs/demo/{wildcards.theme_pack}/{wildcards.img}.png {params.repo_png}
        """

rule gh_pages_theme_json:
    input:
        palettes = mk_palette_reg, 
    output:
        DOCS / "{theme_pack}_themes.json",
    params:
        site_json = mk_repo_json,
    shell:
        'python mk_theme_json.py {SRC}/lua/{wildcards.theme_pack}/palettes --out {output} && cp {output} {params.site_json}'
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
