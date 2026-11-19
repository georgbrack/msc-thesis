"""
Convert ERA5 hybrid levels to geometric heights and average fields onto FLEXPART layers.
"""

import eccodes
import numpy as np
from pathlib import Path
from typing import Iterable, Union
import xarray as xr

Rd = 287.06
g0 = 9.80665
earth_radius = 6371000.0


def read_hybrid_coefficients(filename: Union[str, Path]) -> tuple[np.ndarray, np.ndarray]:  # not used anymore
    """
    Read ERA5 hybrid-pressure coefficients from a GRIB temperature message.

    Parameters
    ----------
    filename : str or pathlib.Path
        Path to a GRIB file containing temperature on ERA5 model levels.

    Returns
    -------
    a_half, b_half : numpy.ndarray
        Arrays of 138 interface coefficients ordered from the model top to the surface. The A coefficients are in Pa and the B coefficients are dimensionless.
    """
    with open(filename, "rb") as file:
        while True:
            message = eccodes.codes_grib_new_from_file(file)

            if message is None:
                raise ValueError("Kein Temperaturfeld gefunden.")

            try:
                parameter = eccodes.codes_get(
                    message, "paramId"
                )

                if parameter == 130:
                    coefficients = np.asarray(
                        eccodes.codes_get_array(message, "pv"),
                        dtype="float"
                    )
                    break
            
            finally:
                eccodes.codes_release(message)

    assert coefficients.size == 276

    a_half = coefficients[:138]
    b_half = coefficients[138:]

    return a_half, b_half


def geometric_altitude(geopotential: Union[float, np.floating, np.ndarray]) -> Union[float, np.floating, np.ndarray]:
    """
    Convert geopotential to geometric altitude using a spherical Earth.

    Parameters
    ----------
    geopotential : float or numpy.ndarray
        Geopotential in m^2 s^-2

    Returns
    -------
    float or numpy.ndarray
        Geometric altitude in meters amsl, with the same shape as the input
    """
    geopotential_height = geopotential / g0

    return (earth_radius * geopotential_height) / (earth_radius - geopotential_height)


def calculate_geometry(met: xr.Dataset, a_half: np.ndarray, b_half: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """
    Compute ERA5 model-level and interface heights above ground.

    Parameters
    ----------
    met : xarray.Dataset
        Dataset for one time with temperature ``t`` (K) and specific humidity ``q`` (kg kg^-1) on 137 hybrid levels, plus surface pressure ``sp`` (Pa) and surface geopotential ``z`` (m^2 s^-2)
    a_half, b_half : numpy.ndarray
        Hybrid-pressure coefficients at the 138 interfaces from the model top to the surface. Interface pressure is ``a_half + b_half * sp``

    Returns
    -------
    height_full : numpy.ndarray
        Model-level heights in meters agl, with shape (137, n_latitude, n_longitude)
    height_half : numpy.ndarray
        Interface heights in meters agl, with shape (138, n_latitude, n_longitude). The top interface is represented by infinity and the surface interface by zero

    Notes
    -----
    Both arrays are ordered from the model top to the surface.
    """
    
    met = met.sortby("hybrid")

    temperature = met["t"].transpose(
        "hybrid", "latitude", "longitude"
    ).values.astype("float64")

    humidity = met["q"].transpose(
        "hybrid", "latitude", "longitude"
    ).values.astype("float64")

    surface_pressure = met["sp"].transpose(
        "latitude", "longitude"
    ).values.astype("float64")

    surface_geopotential = met["z"].transpose(
        "latitude", "longitude"
    ).values.astype("float64")

    virtual_temperature = temperature * (
        1.0 + 0.609133 * humidity
    )

    pressure_half = (
        a_half[:, None, None]
        + b_half[:, None, None] * surface_pressure
    )

    geopotential_full = np.empty_like(temperature)
    geopotential_half = np.empty_like(pressure_half)

    geopotential_half[137] = 0.0

    for level in range(137, 0, -1):
        p_lower = pressure_half[level]
        p_upper = pressure_half[level - 1]

        rt = Rd * virtual_temperature[level -1]

        if level == 1:
            dlog_p = np.log(p_lower / 0.1)
            alpha = np.log(2.0)
        else:
            dlog_p = np.log(p_lower / p_upper)

            alpha = 1.0 - (p_upper / (p_lower - p_upper) * dlog_p)

        geopotential_full[level - 1] = (geopotential_half[level] + rt * alpha)
        geopotential_half[level - 1] = (geopotential_half[level] + rt * dlog_p)

    geopotential_half[0] = np.inf

    ground_altitude = geometric_altitude(surface_geopotential)
    height_full = geometric_altitude(surface_geopotential + geopotential_full) - ground_altitude
    
    height_half = np.empty_like(geopotential_half)

    height_half[1:] = geometric_altitude(surface_geopotential + geopotential_half[1:]) - ground_altitude
    height_half[0] = np.inf

    return height_full, height_half


def average_to_flexpart_layers(source: np.ndarray, boundaries: np.ndarray, upper_bounds: Iterable[float]) -> np.ndarray:
    """
    Average a field onto FLEXPART layers by geometric overlap thickness.

    Parameters
    ----------
    source : numpy.ndarray
        Field on the source layers, ordered from top to bottom along the first axis. Values are treated as constant within each layer.
    boundaries : numpy.ndarray
        Source-layer interfaces in meters agl, ordered from top to bottom. The first axis has one more entry than ``source``
    upper_bounds : array-like
        FLEXPART layer tops in meters agl, in increasing order. The bottom of the first layer is zero

    Returns
    -------
    numpy.ndarray
        Thickness-weighted layer means in the same units as ``source``. The first axis follows ``upper_bounds`` and runs from the surface upward.

    Raises
    ------
    AssertionError
        If the source layers do not fully cover a target layer in any grid column, within the numerical tolerance.
    """

    layer_means = []
    bottom = 0.0

    for top in upper_bounds:
        overlap = np.maximum(
            0.0,
            np.minimum(boundaries[:-1], top) - np.maximum(boundaries[1:], bottom)
        )

        np.testing.assert_allclose(
            overlap.sum(axis=0),
            top - bottom,
            rtol=1e-8,
            atol=1e-6
        )

        layer_mean = (
            source * overlap
        ).sum(axis=0) / (top - bottom)

        layer_means.append(layer_mean)
        bottom = top

    return np.stack(layer_means)