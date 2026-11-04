#!/bin/bash
#SBATCH --time=04:00:00
#SBATCH --job-name=new_delhi
#SBATCH --ntasks=16
#SBATCH --mem=32GB
#SBATCH --output=new_delhi_30d_24h_hourly_releases.log
#SBATCH --nodelist=jet14
#SBATCH --mail-type=ALL
#SBATCH --mail-user=georg.brack@univie.ac.at

export OMP_NUM_THREADS=16
export OMP_PLACES=cores
export OMP_PROC_BIND=true
ulimit -s unlimited

/usr/bin/time -v -o "resources_${SLURM_JOB_ID}.log" ./FLEXPART_ETA
