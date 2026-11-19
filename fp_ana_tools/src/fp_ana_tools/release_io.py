"""
Read FLEXPART release metadata from namelist files.
"""

from pathlib import Path
import f90nml
import pandas as pd
from typing import Union

def read_release_points(flexpart_output_dir: Union[str, Path]) -> pd.DataFrame:
    """
    Read point receptors with heights above ground from a RELEASES namelist.

    Parameters
    ----------
    flexpart_output_dir : str or pathlib.Path
        Path to the FLEXPART output directory containing ``RELEASES.namelist``
    
    Returns
    -------
    pandas.DataFrame
        One row per release, in namelist order. The index is named ``release`` and starts at 1. The columns are
        ``release_time`` (release start in UTC),  ``longitude`` and ``latitude`` (degrees), and ``height_agl`` (meters agl)

    Raises
    ------
    FileNotFoundError
        If ``RELEASES.namelist`` is missing from the output directory
    ValueError
        If a release covers a horizontal or a height range, or if its height reference is not meters agl (ZKIND=1)
    """
    releases_file = Path(flexpart_output_dir) / "RELEASES.namelist"
    blocks = f90nml.read(str(releases_file))["release"]

    if isinstance(blocks, f90nml.Namelist):
        blocks = [blocks]

    rows = []
    for release, block in enumerate(blocks, start=1):
        lower = (block["lon1"], block["lat1"], block["z1"])
        upper = (block["lon2"], block["lat2"], block["z2"])

        if lower != upper or block.get("zkind", 1) != 1:
            raise ValueError(f"Release {release}: expected a point receptor with height AGL")

        longitude, latitude, height_agl = lower
        release_time = pd.to_datetime(f"{block['idate1']:08d}{block['itime1']:06d}", format="%Y%m%d%H%M%S")

        rows.append({
            "release": release,
            "release_time": release_time,
            "longitude": longitude,
            "latitude": latitude,
            "height_agl": height_agl
        })

    return pd.DataFrame(rows).set_index("release")