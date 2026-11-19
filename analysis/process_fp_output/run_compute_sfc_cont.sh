#!/bin/bash
#SBATCH --job-name=sfc_contr
#SBATCH --nodes=1
#SBTACH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=12G
#SBATCH --time=02:00:00
#SBATCH --output=sfc_contr_%j.log

set -euo pipefail

cd "$SLURM_SUBMIT_DIR"

flexpart_output_dir="$(< pathnames)"
surface_file="/jetfs/scratch/gbrack/MSC/ERA_SHF_LHF_2015_04_05_06.nc"
python_bin="$HOME/.conda/envs/mscgb/bin/python"

export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1

exec "$python_bin" -u compute_surface_contributions.py "$flexpart_output_dir" "$surface_file"