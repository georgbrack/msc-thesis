"""
Read hourly ERA5 meteorological fields from GRIB files.
"""

from pathlib import Path
from datetime import datetime
from typing import Union
import pandas as pd
import xarray as xr
import numpy as np

def read_met(time: Union[pd.Timestamp, datetime, str], met_dir: Union[str, Path]) -> xr.Dataset:
    """
    Load ERA5 meteorological fields and hybrid coefficients for one hour.

    Parameters
    ----------
    time : pandas.Timestamp, datetime.datetime or str
        ERA5 validity time in UTC, on the hour. STrings must be paresable by pandas.Timestamp
    met_dir : str or pathlib.Path
        Root directory of the hourly ERA5 archive. Files are expected at ``YYYY/MM/EAYYYYMMDDHH`` relative to this directory.

    Returns
    -------
    xarray.Dataset
        Air temperature ``t`` (K) and specific humidity ``q`` (kg kg^-1) on the hybrid model levels, plus surface pressure ``sp`` (Pa) and surface geopotential ``z`` (m^s s^-2)
        on the horizontal grid. The interface coefficients ``a_half`` (Pa) and ``b_half`` (dimensionless) are read from the temperature GRIB message and stored along ``hybrid_half``, from the model top to the surface.
    """
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

    met = xr.merge(fields, join="exact", compat="no_conflicts")

    pv = np.asarray(met["t"].attrs["GRIB_pv"], dtype=np.float64)
    n_half = met.sizes["hybrid"] + 1

    if pv.shape != (2 * n_half,):
        raise ValueError(f"Unexpected shape of hybrid coefficients: {pv.shape}")

    met["a_half"] = ("hybrid_half", pv[:n_half])
    met["b_half"] = ("hybrid_half", pv[n_half:])
    #met = met.assign_coords(longitude=((met.longitude + 180) % 360) - 180)

    return met.sortby(["hybrid", "latitude", "longitude"])