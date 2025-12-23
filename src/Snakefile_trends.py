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
    Build palette-level constraints (lightness, chroma, hue, polarity)
    learned from Catppuccin palettes.
    """
    input:
        deltaL = INT / "constraints/deltaL_margins.csv",
        chroma = INT / "constraints/chroma_role.csv",
        hue    = INT / "constraints/hue.csv",
    output:
        json = INT / "constraints/palette_constraints.json",
    shell:
        """
        python build_constraints.py \
            --deltal-csv {input.deltaL} \
            --chroma-csv {input.chroma} \
            --hue-csv {input.hue} \
            --out {output.json}
        """
