#!/bin/bash
#SBATCH --job-name=era5_fp
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=16G
#SBATCH --time=24:00:00
#SBATCH --output=era5_fp_%j.log
#SBATCH --mail-type=ALL
#SBATCH --mail-user=georg.brack@univie.ac.at

set -euo pipefail

cd /jetfs/home/gbrack/MSC_Thesis/ERA5_to_FLEXPART_levels

export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1

/jetfs/home/gbrack/envs/bscgb/bin/python -u prepare_era5_fp.py