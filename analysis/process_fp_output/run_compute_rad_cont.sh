#!/bin/bash
#SBATCH --job-name=rad_cont
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=20G
#SBATCH --time=06:00:00
#SBATCH --output=rad_cont_%j.log

set -euo pipefail

cd "$SLURM_SUBMIT_DIR"

flexpart_output_dir="$(< pathnames)"
radiation_dir="/jetfs/scratch/gbrack/MSC/ERA5_FLEXPART_global_0.5deg_42vertlayers/2015"
python_bin="$HOME/.conda/envs/mscgb/bin/python"

export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1

exec "$python_bin" -u compute_radiation_contribution.py "$flexpart_output_dir" "$radiation_dir"/radiation_fp_2015{04,05,06}.nc