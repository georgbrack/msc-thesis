#!/bin/bash
#SBATCH --time=03:00:00
#SBATCH --job-name=ud_ic
#SBATCH --ntasks=16
#SBATCH --mem=100GB
#SBATCH --output=ud_ic.log
#SBATCH --nodelist=jet14
#SBATCH --mail-type=ALL
#SBATCH --mail-user=georg.brack@univie.ac.at

export OMP_NUM_THREADS=16
export OMP_PLACES=cores
export OMP_PROC_BIND=true
ulimit -s unlimited
./FLEXPART_ETA