"""
Compute hourly radiative MSE contributions for a FLEXPART run
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
    if any(len(window) != n_hours for window in windows):
        raise ValueError("Expected the same backward duration for every release")

    valid_times = np.stack([window.values for window in windows])
    hours = np.unique(valid_times)

    grid_files = sorted(args.flexpart_output_dir.glob("grid_time_*.nc"))
    if len(grid_files) != 1:
        raise ValueError(f"Expected one grid_time file, found {len(grid_files)}")

    output_file = args.flexpart_output_dir / "radiation_maps.nc"
    partial_file = output_file.with_suffix(".partial.nc")
    spatial_dims = ("latitude", "longitude")
    output_dims = ("release", "hours_before_release", *spatial_dims)
    scheduler_options = {"scheduler": "threads", "num_workers": args.workers}

    print(f"Dask workers: {args.workers}", flush=True)
    print(f"Release: {len(windows)} | Hours per release: {n_hours} | UTC hours: {len(hours)}", flush=True)

    with xr.open_dataset(
        grid_files[0], chunks={"time": 1}
    ) as grid, xr.open_mfdataset(
        args.radiation_files,
        combine="by_coords",
        data_vars="minimal",
        coords="minimal",
        join="exact",
        chunks={"time": 1},
        compat="no_conflicts"
    ) as radiation:
        sensitivity = (grid.spec001_s22.isel(nageclass=0, drop=True).sel(time=hours))

        if sensitivity.sizes["pointspec"] != len(windows):
            raise ValueError("FLEXPART output pointspec count does not match release windows")

        grid_lon = sensitivity.longitude.values
        rad_lon = grid_lon.copy()
        available_lon = radiation.longitude.values
        if 180 not in available_lon and -180 in available_lon:
            rad_lon[rad_lon == 180] = -180

        sources = (
            radiation[["sw_source", "lw_source"]]
            .sel(
                time=hours,
                height=sensitivity.height.values,
                latitude=sensitivity.latitude.values,
                longitude=rad_lon
            )
            .assign_coords(longitude=grid_lon)
            .rename({"sw_source": "rad_sw", "lw_source": "rad_lw"})
        )
        sources, sensitivity = xr.align(sources, sensitivity, join="exact")

        metadata = xr.Dataset(
            coords={
                "release": np.arange(1, len(windows) + 1),
                "hours_before_release": np.arange(n_hours, 0, -1),
                "latitude": sensitivity.latitude.values,
                "longitude": grid_lon,
                "release_time": ("release", pd.DatetimeIndex(times_fin)),
                "valid_time": (output_dims[:2], valid_times),
            }
        )
        metadata.to_netcdf(partial_file, engine="netcdf4")

        reading_seconds = 0.0
        computing_seconds = 0.0
        writing_seconds = 0.0

        with Dataset(partial_file, mode="a") as out:
            variables = {}
            for name in ("rad_sw", "rad_lw"):
                variable = out.createVariable(
                    name,
                    "f4",
                    output_dims,
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

            for i, hour in enumerate(hours):
                hour_started = perf_counter()

                # Find the release and its relative hour for each output map
                release_rows, hour_slots = np.nonzero(valid_times == hour)
                weights = (
                    sensitivity.isel(time=i, pointspec=release_rows, drop=True)
                    .chunk({"pointspec": 4})
                )
                source = sources.isel(time=i, drop=True)

                source, weights = dask.persist(  # pyright: ignore[reportPrivateImportUsage]
                    source,
                    weights,
                    **scheduler_options
                )
                loaded = perf_counter()

                # Missing rdiation contributes zero where sensitivity is zero
                source = source.where(np.isfinite(source))
                maps = (
                    xr.where(weights == 0, 0.0, source * weights.astype(np.float64))
                    .sum("height", skipna=False)
                    .transpose("pointspec", *spatial_dims)
                    .astype(np.float32)
                    .compute(**scheduler_options)
                )
                computed = perf_counter()

                for name, variable in variables.items():
                    values = maps[name].values
                    for j, (release_row, hour_slot) in enumerate(zip(release_rows, hour_slots)):
                        variable[release_row, hour_slot, :, :] = values[j]

                written = perf_counter()
                del maps, values, source, weights

                reading_seconds += loaded - hour_started
                computing_seconds += computed - loaded
                writing_seconds += written - computed

                if (i + 1) % 12 == 0 or i + 1 == len(hours):
                    print(
                        f"Hour {i + 1}/{len(hours)} | "
                        f"Cumulative reading and rechunking: {reading_seconds:.1f} s | "
                        f"Computing: {computing_seconds:.1f} s | "
                        f"Writing: {writing_seconds:.1f} s",
                        flush=True
                    )

    partial_file.replace(output_file)
    elapsed = perf_counter() - started
    print(f"Saved: {output_file}", flush=True)
    print(f"Total run time: {elapsed:.1f} s ({elapsed / 60:.2f} min)", flush=True)


if __name__ == "__main__":
    main()