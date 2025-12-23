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
            {input} \
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
    shell:
        """
        python compute_chroma_by_role.py \
            {input} {output.csv}
        """

rule plot_chroma_trend:
    input:
        csv = INT / "constraints/chroma_role.csv",
    output:
        png = END / "figures/chroma_by_role.png",
    shell:
        """
        python plot_chroma_by_role.py \
            {input} {output}
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
