"""
With this script, the ERA5 data is brought to the same vertical levels as my FLEXPART output. So we are going from ERA5 model-levels to the 42 heights specified in the COMMAND file.
The output are hourly .nc files for the whole globe on the 42 heights.
"""

from pathlib import Path
import eccodes
import numpy as np
import pandas as pd
import xarray as xr
import sys
from era5_vertical import read_hybrid_coefficients, geometric_altitude, calculate_geometry, average_to_flexpart_layers

# Time scale (end exclusive)
periods = [
    ("2015-04-01 00:00", "2015-05-01 00:00"),
    ("2015-05-01 00:00", "2015-06-01 00:00"),
    ("2015-06-01 00:00", "2015-06-30 23:00")
]

start, end = periods[int(sys.argv[1]) - 4]
start_time = pd.Timestamp(start)
end_time = pd.Timestamp(end)

print(f"Berechne {start} bis {end} UTC (Ende exklusiv)")

times = pd.date_range(start=start_time, end=end_time, freq="1h", inclusive="left")

# paths to data
met_dir = Path("/jetfs/shared-data/ECMWF/ERA5_glob_0.5deg_1h")
radiation_dir = Path("/jetfs/scratch/gbrack/MSC/rad_data/2015")

# we need to know the 42 layers from the FLEXPART COMMAND file, we can also use an arbitrary output for that
grid_file = Path("/jetfs/scratch/gbrack/flexpart_output/new_delhi_10d_24h_hourly_releases/grid_time_20150526000000.nc")

# output
output_dir = Path("/jetfs/scratch/gbrack/MSC/ERA5_FLEXPART_global_0.5deg_42vertlayers")
output_dir.mkdir(parents=True, exist_ok=True)

# get upper bounds of the 42 layers from the FLEXPART output grid file
with xr.open_dataset(grid_file) as grid:
    upper_bounds = grid.height.values.astype("float64")

lower_bounds = np.concatenate(([0.0], upper_bounds[:-1]))

del grid

#print("Number of Layers:", len(upper_bounds))
#print("Upper bounds (AGL):", upper_bounds)

# set constants
cp = 1004.6
Lv = 2501000.0
g = 9.81
Rd = 287.06
g0 = 9.80665
earth_radius = 6371000.0

def read_met(time):
    """
    Read needed ERA5 data for a given time and return it as an xarray Dataset.
    """

    time = pd.Timestamp(time)
    met_file = met_dir / time.strftime("%Y/%m/EA%Y%m%d%H")

    fields = []

    for param_id in [130, 133, 134, 129]:
        with xr.open_dataset(
            met_file,
            engine="cfgrib",
            backend_kwargs={"filter_by_keys": {"paramId": param_id}, "indexpath": ""},
        ) as ds:
            ds = ds.assign_coords(longitude=((ds.longitude + 180) % 360 - 180)).sortby("longitude").sortby("latitude")

            fields.append(ds.drop_vars("surface", errors="ignore").load())

    met = xr.merge(fields, join="exact").sortby("hybrid")

    return met

radiation = None
opened_month = None

for time in times:
    interval_end = time + pd.Timedelta(hours=1)

    # If something is already calculated, skip that hour
    month_dir = output_dir / time.strftime("%Y/%m")
    month_dir.mkdir(parents=True, exist_ok=True)

    output_file = month_dir / f"radiation_fp_{time:%Y%m%d%H}.nc"

    if output_file.exists():
        print(f"Already exists: {output_file}", flush=True)
        continue

    # open new radiation data only for new months
    required_month = interval_end.strftime("%Y/%m")

    if required_month != opened_month:
        if radiation is not None:
            radiation.close()

        radiation_month_dir = radiation_dir.parent / required_month
        radiation_files = sorted(radiation_month_dir.glob("TMTTRAD_*.nc"))

        if not radiation_files:
            raise FileNotFoundError(f"No radiation files found in {radiation_month_dir}")

        radiation = xr.open_mfdataset(
            radiation_files,
            combine="by_coords"
        ).sortby("model_level")

    # radiation data of the right month
    radiation_month_dir = radiation_dir.parent / interval_end.strftime("%Y/%m")
    radiation_files = sorted(radiation_month_dir.glob("TMTTRAD_*.nc"))

    # raise error if no radiation files are found
    if not radiation_files:
        raise FileNotFoundError(f"No radiation files found in {radiation_month_dir}")

    # open radiation files
    radiation = xr.open_mfdataset(radiation_files, combine="by_coords").sortby("model_level")

    # get radiation data for the current hour
    radiation_hour = radiation[["avg_ttswr", "avg_ttlwr"]].sel(valid_time=interval_end.to_datetime64())
    radiation_hour = radiation_hour.assign_coords(longitude=((radiation_hour.longitude + 180) % 360 - 180)).sortby("longitude").sortby("latitude").load()

    # height geometry at the end of the radiation interval
    met_end = read_met(interval_end)

    np.testing.assert_array_equal(radiation_hour.longitude.values, met_end.longitude.values)
    np.testing.assert_array_equal(radiation_hour.latitude.values, met_end.latitude.values)
    np.testing.assert_array_equal(radiation_hour.model_level.values, met_end.hybrid.values)

    met_file = met_dir / interval_end.strftime("%Y/%m/EA%Y%m%d%H")
    a_half, b_half = read_hybrid_coefficients(met_file)

    height_full_end, height_half_end = calculate_geometry(met_end, a_half, b_half)

    # average radiation source to the 42 FLEXPART layers
    prepared_fields = {}

    for name, source in [("sw_source", "avg_ttswr"), ("lw_source", "avg_ttlwr")]:
        values = cp * radiation_hour[source].transpose(
            "model_level", "latitude", "longitude"
        ).values.astype("float64")

        prepared_fields[name] = (
            ("height", "latitude", "longitude"),
            average_to_flexpart_layers(values, height_half_end, upper_bounds)
        )

    del values

    prepared = xr.Dataset(
        prepared_fields,
        coords={
            "height": upper_bounds,
            "latitude": met_end.latitude.values,
            "longitude": met_end.longitude.values
        }
    ).expand_dims(time=[time])

    field_names = ["sw_source", "lw_source"]

    for name in field_names:
        prepared[name].attrs.update(
            units="J kg-1 s-1",
            cell_methods="time: mean height: mean"
        )

    prepared["height_bounds"] = (
        ("height", "bounds"),
        np.column_stack([lower_bounds, upper_bounds])
    )

    prepared.height.attrs.update(
        units="m",
        long_name="Layer upper boundary above ground",
        bounds="height_bounds"
    )
    prepared.height_bounds.attrs["units"] = "m"

    prepared["time_bounds"] = (
        ("time", "bounds"),
        np.array([[
            time.to_datetime64(),
            interval_end.to_datetime64()
        ]])
    )

    prepared.time.attrs.update(
        bounds="time_bounds",
        long_name="Radiation interval start (UTC)"
    )

    prepared.attrs.update(
        vertical_method=(
            "Geometric-thickness-weighted mean,"
            "constant values within ERA5 model layers"
        ),
        geometry_time="Radiation interval end",
        cp=cp
    )

    for name in field_names:
        assert np.isfinite(prepared[name].values).all(), name

    temporary_file = output_file.with_suffix(".nc.part")

    encoding = {
        name: {
            "dtype": "float32",
            "zlib": True,
            "complevel": 5,
            "shuffle": True,
            "chunksizes": (1, 6, 60, 120)
        } for name in field_names
    }

    for name in ["time", "time_bounds"]:
        encoding[name] = {
            "units": "hours since 2015-01-01 00:00:00",
            "calendar": "proleptic_gregorian",
            "dtype": "int32"
        }

    prepared.to_netcdf(
        temporary_file,
        engine="netcdf4",
        encoding=encoding
    )
    temporary_file.replace(output_file)

    print(f"Finished: {output_file}", flush=True)

    del (
        radiation_hour,
        met_end,
        height_full_end,
        height_half_end,
        prepared_fields,
        prepared
    )

if radiation is not None:
    radiation.close()