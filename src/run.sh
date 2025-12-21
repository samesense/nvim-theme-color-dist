#!/usr/bin/env sh

snakemake -s Snakefile.py \
 --forcerun extract_roles \
  -j1 --rerun-triggers mtime --rerun-incomplete -p all
