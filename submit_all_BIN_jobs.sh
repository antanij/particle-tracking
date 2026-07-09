#!/bin/bash
set -euo pipefail

mkdir -p clusterOUT

find . -type f -name "*.bin" | sort > bin_list.txt
N=$(wc -l < bin_list.txt)

if [ "${N}" -eq 0 ]; then
  echo "No .bin files found."
  exit 1
fi

echo "Found ${N} .bin files."
echo "Submitting SLURM array..."

sbatch --array=1-"${N}"%200 trackpy_array.sh