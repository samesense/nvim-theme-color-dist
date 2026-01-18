rule parse_cap_themes:
    output:
        INT / 'cap_colors.csv',
    shell:
        'python parse_cap.py {output}'
 
rule deltaL_margins:
    """
    Compute ΔL* margins between semantic role pairs
    across Catppuccin palettes.
    """
    input:
        INT / 'cap_colors.csv',
    output:
        csv = INT / "constraints/deltaL_margins.csv"
    shell:
        """
        python compute_deltaL_margins.py \
            --colors-csv {input} \
            --out {output.csv}
        """

rule plot_deltaL_margins:
    """
    Plot ΔL* margin distributions as PNG.
    """
    input:
        csv = INT / "constraints/deltaL_margins.csv",
    output:
        png = END / "figures/deltaL_margins.png",
    shell:
        """
        python plot_deltaL_margins.py \
            {input.csv} \
            --out {output.png}
        """

rule chroma_trend:
    input:
        INT / 'cap_colors.csv',
    output:
        csv = INT / "constraints/chroma_role.csv",
        sumcsv = INT / "constraints/chroma_summary.csv",
    shell:
        """
        python compute_chroma_by_role.py \
            --lab-csv {input} --out-csv {output.csv} \
            --summary-csv {output.sumcsv}
        """

rule plot_chroma_trend:
    input:
        csv = INT / "constraints/chroma_role.csv",
    output:
        png = END / "figures/chroma_by_role.png",
    shell:
        """
        python plot_chroma_by_role.py \
            --csv {input} --out {output}
        """

rule hue_trend_data:
    input:
        INT / 'cap_colors.csv',
    output:
        INT / "constraints/hue.csv",
    shell:
        """
        python hue_trend.py \
            {input} {output}
        """

rule text_contrast_bands:
    """
    Compute base-to-text/subtext contrast bands.
    """
    input:
        INT / 'cap_colors.csv',
    output:
        csv = INT / "constraints/text_contrast.csv",
    shell:
        """
        python compute_text_contrast_bands.py \
            --colors-csv {input} \
            --out {output.csv}
        """

rule accent_text_separation:
    """
    Compute accent-to-text separation (L* and dE).
    """
    input:
        INT / 'cap_colors.csv',
    output:
        csv = INT / "constraints/accent_text_separation.csv",
    shell:
        """
        python compute_accent_text_separation.py \
            --colors-csv {input} \
            --out {output.csv}
        """

rule ui_hue_coherence:
    """
    Compute background/surface/overlay/text hue coherence.
    """
    input:
        INT / 'cap_colors.csv',
    output:
        csv = INT / "constraints/ui_hue_coherence.csv",
    shell:
        """
        python compute_ui_hue_coherence.py \
            --colors-csv {input} \
            --out {output.csv}
        """

rule element_offsets:
    """
    Compute L* offsets between element variants within each role.
    Replaces hardcoded +4, -4, +6, -6, -12 magic numbers.
    """
    input:
        INT / 'cap_colors.csv',
    output:
        csv = INT / "constraints/element_offsets.csv",
    shell:
        """
        python compute_element_offsets.py \
            --lab-csv {input} \
            --out-csv {output.csv}
        """

rule accent_separation:
    """
    Compute accent-to-background L* separation by polarity.
    Replaces hardcoded cool_min_deltal and accent_min_deltal.
    """
    input:
        INT / 'cap_colors.csv',
    output:
        csv = INT / "constraints/accent_separation.csv",
    shell:
        """
        python compute_accent_separation.py \
            --lab-csv {input} \
            --out-csv {output.csv}
        """

rule plot_hue_trend_data:
    input:
        csv = INT / "constraints/hue.csv",
    output:
        png = END / "figures/hue.png",
    shell:
        """
        python plot_hue_trend.py \
            {input} {output}
        """

rule build_palette_constraints:
    """
    Build palette-level constraints (lightness, chroma, hue, polarity,
    element offsets, accent separation) learned from Catppuccin palettes.
    """
    input:
        colors = INT / 'cap_colors.csv',
        deltaL = INT / "constraints/deltaL_margins.csv",
        chroma = INT / "constraints/chroma_role.csv",
        hue    = INT / "constraints/hue.csv",
        text_contrast = INT / "constraints/text_contrast.csv",
        accent_text = INT / "constraints/accent_text_separation.csv",
        ui_hue = INT / "constraints/ui_hue_coherence.csv",
        offsets = INT / "constraints/element_offsets.csv",
        separation = INT / "constraints/accent_separation.csv",
    output:
        json = INT / "constraints/palette_constraints.json",
    shell:
        """
        python build_constraints.py \
            --cap-colors-csv {input.colors} \
            --deltal-csv {input.deltaL} \
            --chroma-csv {input.chroma} \
            --hue-csv {input.hue} \
            --text-contrast-csv {input.text_contrast} \
            --accent-text-sep-csv {input.accent_text} \
            --ui-hue-coherence-csv {input.ui_hue} \
            --element-offsets-csv {input.offsets} \
            --accent-separation-csv {input.separation} \
            --out {output.json}
        """
