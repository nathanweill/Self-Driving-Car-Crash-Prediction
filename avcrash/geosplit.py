"""East/west split of the zones for the spatial holdouts."""
from __future__ import annotations

import numpy as np
import pandas as pd


def split_regions(zones, center, angle_deg: float) -> pd.DataFrame:
    """Assign each zone to 'east' or 'west' of a line through ``center``.

    The line's normal makes ``angle_deg`` with the easting axis; a zone's side
    is the sign of the projection of its representative point on the normal.
    The side with the larger median easting is labeled 'east'.
    """
    pts = zones.geometry.representative_point()
    x, y = pts.x.to_numpy(float), pts.y.to_numpy(float)
    phi = np.radians(float(angle_deg))
    score = (x - center[0]) * np.cos(phi) + (y - center[1]) * np.sin(phi)
    pos = score > 0
    if pos.any() and (~pos).any() and np.median(x[pos]) < np.median(x[~pos]):
        pos = ~pos
    return pd.DataFrame({"superzone_id": zones["superzone_id"].to_numpy(),
                         "region": np.where(pos, "east", "west")})
