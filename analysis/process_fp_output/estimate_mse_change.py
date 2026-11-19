import argparse
import numpy as np
import pandas as pd
import xarray as xr
from pathlib import Path
from typing import cast

from fp_ana_tools.era5_io import read_met
from fp_ana_tools.era5_vertical import average_to_flexpart_layers, calculate_geometry, geometric_altitude
from fp_ana_tools.read_binary import read_gridini, read_namelists
from fp_ana_tools.release_io import read_release_points


CP  = 1004.6
LV = 2501000.0
G = 9.81


def calculate_initial_mse(sensitivity: xr.DataArray, initial_time: pd.Timestamp, met_dir: Path) -> dict[str, float]:
    """
    Calculate sensitivity-weighted initial MSE for one release in J/kg
    """
    sensitivity = sensitivity.transpose("height", "latitude", "longitude")
    weights = sensitivity.to_numpy()
    weight_sum = float(weights.sum())

    if not np.isfinite(weight_sum) or weight_sum <= 0:
        raise ValueError(f"Invalid initial sensitivity sum at {initial_time}: {weight_sum}")

    met = read_met(initial_time, met_dir).sel(
        latitude=sensitivity.latitude.values,
        longitude=sensitivity.longitude.values
    ).transpose("hybrid", "latitude", "longitude", "hybrid_half")

    height_full, height_half = calculate_geometry(
        met, met.a_half.values, met.b_half.values
    )
    ground_altitude = geometric_altitude(met.z.values)

    energy_fields = {
        "cpT_ini_raw": CP * met.t.values.astype("float64"),
        "Lvq_ini_raw": LV * met.q.values.astype("float64"),
        "gh_ini_raw": G * (height_full + ground_altitude)
    }

    result = {}
    for name, field in energy_fields.items():
        layer_mean = average_to_flexpart_layers(
            field, height_half, sensitivity.height.values
        )
        result[name] = float((weights * layer_mean).sum())

    mse_raw = sum(result.values())
    result["weight_sum"] = weight_sum
    result["mse_ini_raw"] = mse_raw
    result["mse_ini_normalized"] = mse_raw / weight_sum
    return result


def calculate_target_mse(
        release_time: pd.Timestamp,
        met_dir: Path,
        latitude: float,
        longitude: float,
        height_agl: float
) -> dict[str, float]:
    """
    Calculate MSE at a point recepter at release time in J/kg
    """
    met = read_met(release_time, met_dir).interp(
        latitude=[latitude],
        longitude=[longitude],
    ).sortby("hybrid")

    height_full, _ = calculate_geometry(
        met, met.a_half.values, met.b_half.values
    )
    heights_agl = height_full[:, 0, 0][::-1]

    if not heights_agl[0] <= height_agl <= heights_agl[-1]:
        raise ValueError(f"Receptor height outside ERA5 profile at {release_time}")

    temperature = met.t.transpose("hybrid", "latitude", "longitude").values
    humidity = met.q.transpose("hybrid", "latitude", "longitude").values

    cpT = float(CP * np.interp(height_agl, heights_agl, temperature[::-1, 0, 0]))
    Lvq = float(LV * np.interp(height_agl, heights_agl, humidity[::-1, 0, 0]))
    ground_altitude = float(geometric_altitude(float(met.z.item())))
    gh = G * (ground_altitude + height_agl)

    return {"cpT_end": cpT, "Lvq_end": Lvq, "gh_end": gh, "mse_end": cpT + Lvq + gh}


def main():
    parser = argparse.ArgumentParser(
        description="Calculate initial MSE for all releases in a FLEXPART run."
    )
    parser.add_argument("flexpart_output_dir", type=Path, help="FLEXPART output directory")
    parser.add_argument("met_dir", type=Path, help="Root of the hourly ERA5 archive on disk")
    args = parser.parse_args()

    print(f"FLEXPART Output directory: {args.flexpart_output_dir}", flush=True)

    times_ini, times_fin, heights, lat, lon, _ = read_namelists(args.flexpart_output_dir)
    ds_ini = read_gridini(args.flexpart_output_dir, times_ini, heights, lat, lon)
    receptors = read_release_points(args.flexpart_output_dir)

    if not pd.DatetimeIndex(receptors["release_time"]).equals(pd.DatetimeIndex(times_fin)):
        raise ValueError(
            "Release times differ between RELEASES.namelist and the FLEXPART grid."
        )

    rows = []
    for i, (initial_time, release_time) in enumerate(zip(times_ini, times_fin)):
        release = i + 1

        initial = calculate_initial_mse(
            ds_ini.sensitivity.isel(valid_time=i, drop=True),
            pd.Timestamp(initial_time),
            args.met_dir
        )

        target = calculate_target_mse(
            pd.Timestamp(release_time),
            args.met_dir,
            latitude=cast(float, receptors.at[release, "latitude"]),
            longitude=cast(float, receptors.at[release, "longitude"]),
            height_agl=cast(float, receptors.at[release, "height_agl"])
        )

        rows.append({
            "release": release,
            "initial_time": initial_time,
            "release_time": release_time,
            **initial,
            **target,
            "delta_mse_est": target["mse_end"] - initial["mse_ini_normalized"]
        })
        print(f"Calculation of estimated MSE change for release {i+1}/{len(times_fin)} done", flush=True)

    output_file = args.flexpart_output_dir / "estimated_mse_change.csv"
    pd.DataFrame(rows).to_csv(output_file, index=False)
    print(f"Saved: {output_file}", flush=True)

if __name__ == "__main__":
    main()