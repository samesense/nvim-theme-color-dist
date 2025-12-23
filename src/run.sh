#!/usr/bin/env sh

snakemake -s Snakefile.py \
  -j5 --rerun-triggers mtime \
  --rerun-incomplete -p all
