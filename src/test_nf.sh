#!/bin/bash
set -e

# Single image test
nextflow run theme.nf --img industry

# Batch test
#nextflow run theme.nf -entry batch --imgs 'industry,camels'
