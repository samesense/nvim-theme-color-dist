#!/usr/bin/env sh

snakemake -s Snakefile.py \                                                                                                                                                           
          --use-conda \                                                                                                                                                                                                                                           
          -j10 \                                                                                                                                                                      
          --rerun-triggers mtime \                                                                                                                                                    
          --rerun-incomplete \                                                                                                                                                        
          -n all
