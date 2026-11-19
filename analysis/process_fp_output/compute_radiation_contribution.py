"""
Compute hourly radiative MSE contributions for a FLEXPART run
"""

import argparse
import os
from pathlib import Path
from time import perf_counter()

import dask
import numpy as np
import pandas as pd
import xarray as xr
from netCDF4 import Dataset

from fp_ana_tools.read_binary import read_namelists

def integrate_radiation(weights: np.ndarray, field: np.ndarray) -> np.ndarray:
    """
    Multiply sensitivity by radiative heating and sum over height.
    """
    missing = ~np.isfinite(field)

    if missing.any():
        field = np.where(missing, 0.0, field)
        maps = np.einsum("rhyx,hyx->ryx", weights, field, dtype=np.float64)

        for release_map, release_weights in zip(maps, weights):
            affected = ((release_weights != 0) & missing).any(axis=0)
            release_map[affected] = np.nan

    else:
        maps = np.einsum("rhyx,hyx->ryx", weights, field, dtype=np.float64)

    return maps.astype(np.float32)


def main() -> None:
    """
    Read FLEXPART and radiation fields and write hourly contribution maps.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("flexpart_output_dir", type=Path)
    parser.add_argument("radiation_files", type=Path, nargs="+")
    parser.add_argument(
        "--workers",
        type=int,
        default=int(os.environ.get("SLURM_CPUS_PER_TASK", "1")),
        help="Number of Dask threads for reading and computing"
    )
    args = parser.parse_args()

    if args.workers < 1:
        parser.error("--workers must be at least 1")

    started = perf_counter()

    times_ini, times_fin, *_ = read_namelists(args.flexpart_output_dir)
    windows = [
        pd.date_range(start, end, freq="h", inclusive="left")
        for start, end in zip(times_ini, times_fin)
    ]

    if not windows or len(windows[0]) == 0:
        raise ValueError("No hourly release windows found")

    n_hours = len(windows[0])
    if any(len(windows) != n_hours for window in windows):
        raise ValueError("Expected the same backward duration for every release")
    