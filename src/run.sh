#!/usr/bin/env sh

snakemake -s Snakefile.py \
 --forcerun assign_elements \
  -j1 --rerun-triggers mtime --rerun-incomplete -p all
