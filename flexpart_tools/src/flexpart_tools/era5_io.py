from pathlib import Path
import pandas as pd
import xarray as xr
import numpy as np

def read_met(time, met_dir):
    """Load global hourly ERA5 fields t, q, sp, and z."""
    time = pd.Timestamp(time)
    met_file = Path(met_dir) / time.strftime("%Y/%m/EA%Y%m%d%H")
    fields = []

    for param_id in [130, 133, 134, 129]:
        backend_kwargs = {
            "filter_by_keys": {"paramId": param_id},
            "indexpath": ""
        }
        if param_id == 130:
            backend_kwargs["read_keys"] = ["pv"]
        
        with xr.open_dataset(met_file, engine="cfgrib", backend_kwargs=backend_kwargs) as ds:
            fields.append(ds.drop_vars("surface", errors="ignore").load())

    met = xr.merge(fields, join="exact")

    pv = np.asarray(met["t"].attrs["GRIB_pv"], dtype=np.float64)
    n_half = met.sizes["hybrid"] + 1

    if pv.shape != (2 * n_half,):
        raise ValueError(f"Unexpected shape of hybrid coefficients: {pv.shape}")

    met["a_half"] = ("hybrid_half", pv[:n_half])
    met["b_half"] = ("hybrid_half", pv[n_half:])
    met = met.assign_coords(longitude=((met.longitude + 180) % 360) - 180)

    return met.sortby(["hybrid", "latitude", "longitude"])