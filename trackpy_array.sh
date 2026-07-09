#!/bin/bash
#SBATCH --job-name=trackpy_bin
#SBATCH --partition=day
#SBATCH --time=0-10:00:00
#SBATCH --ntasks=1
#SBATCH --nodes=1
#SBATCH --cpus-per-task=12
#SBATCH --mem=32G
#SBATCH --output=clusterOUT/trackpy_%a.out
#SBATCH --error=clusterOUT/trackpy_%a.err
#SBATCH --array=1-1   # overwritten by submit.sh

set -euo pipefail

module load miniconda
conda activate py3_env

BIN_PATH=$(sed -n "${SLURM_ARRAY_TASK_ID}p" bin_list.txt)

echo "SLURM_ARRAY_TASK_ID=${SLURM_ARRAY_TASK_ID}"
echo "BIN_PATH=${BIN_PATH}"

python track_one_bin.py --bin "${BIN_PATH}" --config config.json

conda deactivate