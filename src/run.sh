#!/usr/bin/env sh

snakemake -s Snakefile.py \
 --forcerun assign_roles \
  -j1 --rerun-triggers mtime --rerun-incomplete -k all
