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
