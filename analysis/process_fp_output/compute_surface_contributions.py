"""
Compute hourly surface flux contributions for a FLEXPART run.
"""

import argparse
import os
from pathlib import Path
from time import perf_counter
import dask

import numpy as np
import pandas as pd
import xarray as xr
from netCDF4 import Dataset

from fp_ana_tools.read_binary import read_namelists


def main() -> None:
    """
    Read the input files, calculate the hourly maps and report timings.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("flexpart_output_dir", type=Path)
    parser.add_argument("surface_file", type=Path)
    parser.add_argument(
        "--workers",
        type=int,
        default=int(os.environ.get("SLURM_CPUS_PER_TASK", "1")),
        help="Number of Dask threads. Defaults to the SLURM CPU allocation or 1."
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
        raise ValueError("no hourly release windows found")

    n_hours = len(windows[0])
    if any(len(window) != n_hours for window in windows):
        raise ValueError("Expected the same backward duration for every release")

    grid_files = sorted(args.flexpart_output_dir.glob("grid_time_*.nc"))
    if len(grid_files) != 1:
        raise ValueError(f"Expected one grid_time file, found {len(grid_files)}")

    output_file = args.flexpart_output_dir / "surface_maps.nc"
    partial_file = output_file.with_suffix(".partial.nc")

    print(f"Dask workers: {args.workers}", flush=True)
    print(f"Releases: {len(windows)} | Hours per release: {n_hours}", flush=True)

    with xr.open_dataset(grid_files[0], chunks={"time": 1}) as grid, xr.open_dataset(args.surface_file, chunks={}) as surface:
        layer_top = float(grid.height.min().item())
        sensitivity = (
            grid.spec001_mr.isel(nageclass=0, drop=True).sel(height=layer_top, drop=True)
        )

        surface = surface[["sshf", "slhf"]]
        if "valid_time" in surface.dims:
            surface = surface.rename({"valid_time": "time"})

        # ERA5 timestamps markieren das ende jeder stunde
        surface = surface.assign_coords(
            time=surface.time - pd.Timedelta(hours=1),
            longitude=(surface.longitude + 180) % 360 - 180,
        )

        grid_lon = sensitivity.longitude.values
        surface = surface.sel(
            latitude=sensitivity.latitude.values,
            longitude=(grid_lon + 180) % 360 - 180
        ).assign_coords(longitude=grid_lon)

        # Konvertiere akkumulierte J/m^2 zu J/m^3/s, positive upward
        sources = surface.rename({
            "sshf": "sfc_sensible",
            "slhf": "sfc_latent"
        })

        dims = ("release", "hours_before_release", "latitude", "longitude")
        metadata = xr.Dataset(
            coords = {
                "release": np.arange(1, len(windows) + 1),
                "hours_before_release": np.arange(n_hours, 0, -1),
                "latitude": sensitivity.latitude.values,
                "longitude": grid_lon,
                "release_time": ("release", pd.DatetimeIndex(times_fin)),
                "valid_time": (
                    dims[:2],
                    np.stack([window.values for window in windows])
                )
            }
        )
        metadata.to_netcdf(partial_file, engine="netcdf4")

        with Dataset(partial_file, mode="a") as out:
            variables = {}
            for name in ("sfc_sensible", "sfc_latent"):
                variable = out.createVariable(
                    name,
                    "f4",
                    dims,
                    zlib=True,
                    complevel=2,
                    chunksizes=(
                        1, 1,
                        sensitivity.sizes["latitude"],
                        sensitivity.sizes["longitude"]
                    ),
                    fill_value=np.float32(np.nan)
                )
                variable.units = "J kg-1"
                variable.coordinates = "release_time valid_time"
                variables[name] = variable
            
            chunks = {"time": 24, "latitude": -1, "longitude": -1}

            for i, hours in enumerate(windows):
                release_started = perf_counter()

                weights = sensitivity.isel(pointspec=i, drop=True).sel(time=hours)
                source, weights = xr.align(
                    sources.sel(time=hours), weights, join="exact"
                )
                source, weights = dask.persist(  # pyright: ignore[reportPrivateImportUsage]   - das ist irgendwie notwendig dass pylance nicht herumschreit
                    source.chunk(chunks),
                    weights.chunk(chunks),
                    scheduler="threads",
                    num_workers=args.workers
                )
                loaded = perf_counter()

                source = -source / (3600 * layer_top)
                maps = (
                    xr.where(weights == 0, 0.0, source * weights)
                    .transpose("time", "latitude", "longitude")
                    .astype(np.float32)
                    .compute(scheduler="threads", num_workers=args.workers)
                )
                computed = perf_counter()

                for name, variable in variables.items():
                    variable[i, :, :, :] = maps [name].values

                written = perf_counter()
                del maps, source, weights

                print(
                    f"Release {i + 1}/{len(windows)} | "
                    f"Reading and Rechunking: {loaded - release_started:.1f} s | "
                    f"Computing: {computed - loaded:.1f} s | "
                    f"Writing: {written - computed:.1f} s | "
                    f"Total: {written - release_started:.1f} s",
                    flush=True
                )
        
    partial_file.replace(output_file)
    elapsed = perf_counter() - started
    print(f"Saved: {output_file}", flush=True)
    print(f"Total run time: {elapsed:.1f} s ({elapsed / 60:.2f} min)", flush=True)

if __name__ == "__main__":
    main()