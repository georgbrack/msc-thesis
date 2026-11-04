from pathlib import Path
import dask
import numpy as np
import pandas as pd
import xarray as xr
import sys

root = Path("/jetfs/scratch/gbrack/MSC/ERA5_FLEXPART_global_0.5deg_42vertlayers/2015")

months = ["05", "06"]

month = months[int(sys.argv[1]) - 5]

files = sorted((root / month).glob("radiation_fp_*.nc"))

start = pd.Timestamp(f"2015-{month}-01")
end = start + pd.offsets.MonthBegin(1)

if month == "06":
    end = pd.Timestamp("2015-06-30 23:00")

expected = pd.date_range(start, end, freq="1h", inclusive="left")
assert len(files) == len(expected), (len(files), len(expected))

target = root / f"radiation_fp_2015{month}.nc"
temp = target.with_suffix(".nc.part")

encoding = {
    name: {
        "dtype": "float32",
        "zlib": True,
        "complevel": 5,
        "shuffle": True,
        "chunksizes": (1, 6, 60, 120)
    } for name in ["sw_source", "lw_source"]
}

for name in ["time", "time_bounds"]:
    encoding[name]: {
        "units": "hours since 2015-01-01 00:00",
        "calendar": "proleptic_gregorian",
        "dtype": "int32"
    }

with xr.open_mfdataset(
    files,
    combine="nested",
    concat_dim="time",
    data_vars="minimal",
    coords="minimal",
    compat="equals",
    join="exact",
    chunks=-1
) as monthly:
    np.testing.assert_array_equal(monthly.time.values, expected.values)
    assert monthly.height_bounds.dims == ("height", "bounds")
    assert monthly.time_bounds.dims == ("time", "bounds")

    with dask.config.set(scheduler="single-threaded"):
        monthly.to_netcdf(temp, engine="netcdf4", encoding=encoding)


with xr.open_dataset(temp) as saved:
    np.testing.assert_array_equal(saved.time.values, expected.values)

    for index in [0, len(files) // 2, len(files) - 1]:
        with xr.open_dataset(files[index]) as hourly:
            for name in ["sw_source", "lw_source"]:
                np.testing.assert_array_equal(
                    saved[name].isel(time=index).values,
                    hourly[name].isel(time=0).values
                )

temp.replace(target)
print(f"{target.name}: {target.stat().st_size / 1e9:.1f} GB", flush=True)