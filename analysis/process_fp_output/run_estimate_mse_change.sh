#!/bin/bash
#SBATCH --job-name=est_mse_chg
#SBATCH --nodes=1
#SBTACH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=12G
#SBATCH --time=00:30:00
#SBATCH --output=estimate_mse_change_%j.log

set -euo pipefail

cd "$SLURM_SUBMIT_DIR"

flexpart_output_dir="$(< pathnames)"
met_dir="/jetfs/shared-data/ECMWF/ERA5_glob_0.5deg_1h"
python_bin="$HOME/.conda/envs/mscgb/bin/python"

export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1

exec "$python_bin" -u estimate_mse_change.py "$flexpart_output_dir" "$met_dir"