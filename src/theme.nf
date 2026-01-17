nextflow.enable.dsl=2

/*
 * Nvim theme generation pipeline
 * Converts source images into Catppuccin-style Neovim color themes
 */

params.img = null
params.raw = "${projectDir}/../data/raw"
params.interim = "${projectDir}/../data/interim"
params.end = "${projectDir}/../data/processed"
params.constraints = "${params.interim}/constraints/palette_constraints.json"
params.palette = "auto"

process extract_roles {
    /*
     * Extract color clusters from source image
     */
    container 'samesense/nvim-theme-tools:py311'

    input:
    tuple val(img), path(png), path(constraints)

    output:
    tuple val(img), path("${img}_colors.csv"), path(constraints)

    script:
    """
    extract_colors.py ${png} \\
        --constraints-json ${constraints} \\
        --out-csv ${img}_colors.csv \\
        --palette ${params.palette}
    """
}

process assign_elements {
    /*
     * Assign extracted colors to Catppuccin semantic roles
     */
    container 'samesense/nvim-theme-tools:py311'

    input:
    tuple val(img), path(colors), path(constraints)

    output:
    tuple val(img), path(colors), path(constraints), path("${img}.json"), path("${img}_assign.png")

    script:
    def theme_name = "${img}_theme"
    """
    assign_elements.py \\
        ${colors} \\
        --constraints-json ${constraints} \\
        --theme-name ${theme_name} \\
        --out-json ${img}.json \\
        --out-image ${img}_assign.png
    """
}

process fill_elements {
    /*
     * Fill missing elements and generate final theme
     */
    container 'samesense/nvim-theme-tools:py311'

    publishDir "${params.end}", pattern: "*_theme.lua", mode: 'copy'
    publishDir "${params.end}/figures/assign", pattern: "*_assign.png", mode: 'copy'
    publishDir "${params.end}/figures/fill", pattern: "*_fill.png", mode: 'copy'

    input:
    tuple val(img), path(colors), path(constraints), path(assign_json), path(assign_png)

    output:
    tuple val(img), path("${img}_theme.lua"), path(assign_png), path("${img}_fill.png")

    script:
    def theme_name = "${img}_theme"
    """
    fill_gaps.py \\
        --assignments-json ${assign_json} \\
        --color-pool-csv ${colors} \\
        --constraints-json ${constraints} \\
        --out-lua ${img}_theme.lua \\
        --out-image ${img}_fill.png \\
        --theme-name ${theme_name}
    """
}

workflow {
    // Validate input
    if (!params.img) {
        error "Please specify an image name with --img <name>"
    }

    // Create input channel
    img_ch = Channel.of(params.img)
        .map { img ->
            def png = file("${params.raw}/photos/${img}.png")
            def constraints = file(params.constraints)
            if (!png.exists()) {
                error "Image not found: ${png}"
            }
            if (!constraints.exists()) {
                error "Constraints not found: ${constraints}"
            }
            tuple(img, png, constraints)
        }

    // Run pipeline
    extract_roles(img_ch)
    | assign_elements
    | fill_elements
}

workflow batch {
    /*
     * Process multiple images
     * Usage: nextflow run theme.nf -entry batch --imgs 'img1,img2,img3'
     */
    if (!params.imgs) {
        error "Please specify image names with --imgs 'img1,img2,img3'"
    }

    imgs_ch = Channel.of(params.imgs.tokenize(','))
        .map { img ->
            def png = file("${params.raw}/photos/${img.trim()}.png")
            def constraints = file(params.constraints)
            tuple(img.trim(), png, constraints)
        }

    extract_roles(imgs_ch)
    | assign_elements
    | fill_elements
}
