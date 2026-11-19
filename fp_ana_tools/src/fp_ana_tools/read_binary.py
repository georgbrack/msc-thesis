"""
Read FLEXPART release metadata and gridded initial-condition sensitivities
This part was writen by Marina Dütsch. Docstrings added by Georg Brack
"""

import numpy as np
import datetime
import f90nml
import xarray as xr
import glob
from pathlib import Path
from typing import Sequence, Union


def decode_binary(flxdir, ntim, nlev, nlat, nlon, linv=0):
    """
    I skipped writing a docstring because this function is only used be the other two functions.
    """
    if linv == 0:
        inipaths = [f'{flxdir}/grid_initial_001']
        len_dummy_entries = 20

    elif linv == 1:
        inipaths = sorted(glob.glob(f'{flxdir}/grid_initial*'))[::-1]
        len_dummy_entries = 3

    sparse_dump_i = []
    sparse_dump_r = []
    for inipath in inipaths:
        offset = 4*3
        while True:
            try:
                sp_count_i = np.fromfile(inipath, dtype='<i4', count=1, offset=offset+4*(len_dummy_entries+1))[0]
                sparse_dump_i.append(np.fromfile(inipath, dtype='<i4', count=sp_count_i, offset=offset+4*(len_dummy_entries+4)))
                sp_count_r = np.fromfile(inipath, dtype='<i4', count=1, offset=offset+4*(len_dummy_entries+4+sp_count_i+2))[0]
                sparse_dump_r.append(np.fromfile(inipath, dtype='<f4', count=sp_count_r, offset=offset+4*(len_dummy_entries+4+sp_count_i+5)))
                offset += 4*(len_dummy_entries+4+sp_count_i+5+sp_count_r+1)
            except (IndexError): # end of file
                break

    inisens_1d = np.zeros((ntim,nlon*nlat*nlev))

    for t in range(ntim):
        rind = 0
        for i in range(len(sparse_dump_i[t])):
            sign = np.sign(sparse_dump_r[t][rind])
            n = 0
            while rind+n < len(sparse_dump_r[t])-1 and sparse_dump_r[t][rind+n]*sign > 0:
                inisens_1d[t, sparse_dump_i[t][i] - nlon * nlat + n] = sign * sparse_dump_r[t][rind + n]
                n += 1
            rind += n

    inisens = inisens_1d.reshape((ntim,nlev,nlat,nlon))

    return inisens

def read_namelists(flxdir: Union[str, Path]) -> tuple[list[datetime.datetime], list[datetime.datetime], np.ndarray, np.ndarray, np.ndarray, int]:
    """
    Read release windows and output-grid coordinates from a FLEXPART run.

    Parameters
    ----------
    flxdir : str or pathlib.Path
        FLEXPART output directory containing the namelists and grid file.

    Returns
    -------
    times_ini, times_fin : list of datetime
        Start of the backward window and release time for each release (UTC).
    heights : numpy.ndarray
        Layer boundaries in meters agl, including zero at the surface.
    lat, lon : numpy.ndarray
        Output-grid cell centres in degrees.
    age : int
        Backward integration duration in seconds
    """
    nml = f90nml.read(f'{flxdir}/OUTGRID.namelist')

    nlon = nml['outgrid']['numxgrid']
    nlat = nml['outgrid']['numygrid']
    heights = np.concatenate([[0.],np.array(nml['outgrid']['outheights'])])
    nlev = len(heights) - 1

    lon0 = nml['outgrid']['outlon0']
    dx = nml['outgrid']['dxout']
    lat0 = nml['outgrid']['outlat0']
    dy = nml['outgrid']['dyout']

    lon = np.arange(lon0 + dx/2, lon0+nlon*dx, dx)
    lat = np.arange(lat0 + dy/2, lat0+nlat*dy, dy)

    nml = f90nml.read(f'{flxdir}/AGECLASSES.namelist')
    age = nml['ageclass']['lage']

    nml = f90nml.read(f'{flxdir}/COMMAND.namelist')
    bdate = datetime.datetime.strptime(f"{nml['command']['ibdate']:08d}{nml['command']['ibtime']:06d}",'%Y%m%d%H%M%S')
    edate = datetime.datetime.strptime(f"{nml['command']['iedate']:08d}{nml['command']['ietime']:06d}",'%Y%m%d%H%M%S')

    ds_grid = xr.open_dataset(f"{flxdir}/grid_time_{edate.strftime('%Y%m%d%H%M%S')}.nc", decode_timedelta=True)
    times_fin = [edate + datetime.timedelta(seconds=relst.item()//10**9) for relst in ds_grid.RELSTART]
    times_ini = [time_fin - datetime.timedelta(seconds=age) for time_fin in times_fin]

    return times_ini, times_fin, heights, lat, lon, age

def read_gridini(flxdir: Union[str, Path], times: Sequence[datetime.datetime], heights: Union[np.ndarray, Sequence[float]], lat: Union[np.ndarray, Sequence[float]], lon: Union[np.ndarray, Sequence[float]], linv: int=0) -> xr.Dataset:
    """
    Decode FLEXPART initial-condition sensitivities onto the output grid.

    Each entry on the valid_time axis describes one release at the start fo its backward window.

    Parameters
    ----------
    flxdir : str or pathlib.Path
        FLEXPART output directory containing the grid_initial files.
    times : sequence of datetime
        Initial times in UTC, one per release, in the order stored in the binary output.
    heights : array-like
        Layer boudnaries in meters agl, starting at zero.
    lat, lon : array-like
        Latitude and longitude of output-grid cell centers, in degrees.
    linv : int, default 0
        Binary layout selector. Use 0 for grid_initial_001 or 1 for the alternate layout with multiple grid_initial files.
    
    Returns
    -------
    xarray.Dataset
        Dataset containing sensitivity on (valid_time, height, latitude, longitude). The height coordinate gives layer tops in meters agl.
    """
    ntim = len(times)
    nlev = len(heights)-1
    nlat = len(lat)
    nlon = len(lon)

    inisens = decode_binary(flxdir, ntim, nlev, nlat, nlon, linv=linv)

    ds_ini = xr.Dataset(
        data_vars=dict(
            sensitivity=(['valid_time', 'height', 'latitude', 'longitude'], inisens),
        ),
        coords=dict(
            longitude=('longitude', lon),
            latitude=('latitude', lat),
            height=('height', heights[1:]),
            valid_time=('valid_time', times),
        ),
        attrs=dict(description='Sensitivity to initial conditions'),
    )

    return ds_ini