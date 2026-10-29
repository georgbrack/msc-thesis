#!/bin/bash
#SBATCH --job-name=era5-jun+may
#SBATCH --partition=long
#SBATCH --array=5-6%1
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=2G
#SBATCH --time=0
#SBATCH --output=era5-%A-month%a.log
#SBATCH --mail-type=ALL
#SBATCH --mail-user=georg.brack@univie.ac.at

set -euo pipefail

PYTHON=/jetfs/jupyterhub/alpha/envs/magic/bin/python

exec "$PYTHON" -u download_rad_data.py \
    --year 2015 \
    --month "$SLURM_ARRAY_TASK_ID"