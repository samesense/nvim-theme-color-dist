#!/usr/bin/env sh

snakemake -s Snakefile.py \
  --use-docker \
  -j1 --rerun-triggers mtime \
  --rerun-incomplete \
  -n all
