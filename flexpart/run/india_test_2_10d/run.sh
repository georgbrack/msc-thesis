#!/bin/bash
#SBATCH --time=01:00:00
#SBATCH --job-name=india_2_10d
#SBATCH --ntasks=16
#SBATCH --mem=20GB
#SBATCH --output=india_run.log
#SBATCH --nodelist=jet13
#SBATCH --mail-type=ALL
#SBATCH --mail-user=georg.brack@univie.ac.at

export OMP_NUM_THREADS=16
export OMP_PLACES=cores
export OMP_PROC_BIND=true
ulimit -s unlimited
./FLEXPART_ETA

