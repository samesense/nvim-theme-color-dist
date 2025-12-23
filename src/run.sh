#!/usr/bin/env sh

snakemake -s Snakefile.py \
 --forcerun build_palette_constraints \
  -j1 --rerun-triggers mtime \
  --rerun-incomplete -p all
