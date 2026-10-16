"""Readers for the raw inputs and small parsing helpers."""
from __future__ import annotations

import re
from typing import Dict

import geopandas as gpd
import pandas as pd
from shapely import wkt
from shapely.geometry import Point

# TIMS/SWITRS code -> label
LIGHTING = {"A": "daylight", "B": "dusk_dawn", "C": "dark_street_lights", "D": "dark_no_street_lights"}
WEATHER = {"A": "clear", "B": "cloudy", "C": "raining", "E": "fog_visibility", "F": "other"}
ROAD_SURFACE = {"A": "dry", "B": "wet", "C": "snow_ice", "D": "slippery", "H": "other", "Q": "other"}
# SWITRS/TIMS collision severity (worst injury in the crash). TIMS has no code 0 (no injury /
# property damage only): every HV crash in the data is an injury or fatal crash.
SEVERITY = {"1": "fatal", "2": "severe_injury", "3": "other_injury", "4": "pain"}  # 4 = complaint of pain


def map_codes(s: pd.Series, mapping: Dict[str, str]) -> pd.Series:
    """Map single-letter codes to labels; anything else (missing, '-') is 'not_reported'."""
    return s.astype(str).str.strip().map(mapping).fillna("not_reported")


def bool_indicator(s: pd.Series) -> pd.Series:
    return s.astype(str).str.strip().str.lower().isin(["true", "t", "1", "yes", "y"]).astype(float)


def yn_indicator(s: pd.Series) -> pd.Series:
    return s.astype(str).str.strip().str.upper().map({"Y": 1.0, "N": 0.0}).fillna(0.0)


def category_tokens(s: pd.Series) -> pd.Series:
    """Lower-case category labels as safe column-name tokens ('unknown' for missing)."""
    x = s.astype(str).str.strip().str.lower()
    x = x.replace({"": "unknown", "nan": "unknown", "none": "unknown", "null": "unknown", "<na>": "unknown"})

    def tok(v: str) -> str:
        t = re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", v)).strip("_")
        return t or "unknown"

    return x.map(tok)


def numeric(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s.astype(str).str.replace(",", "", regex=True), errors="coerce")


def time_of_day(val) -> str:
    """'day' 7:00-18:59, 'night' 19:00-4:59, 'dawn_dusk' otherwise (time as HHMM or HH:MM)."""
    if pd.isna(val):
        return "unknown"
    s = str(val).strip()
    try:
        if ":" in s:
            h = int(s.split(":")[0]) % 24
        else:
            digits = "".join(ch for ch in s if ch.isdigit())
            if not digits:
                return "unknown"
            h = (int(digits) if len(digits) <= 2 else int(digits[:-2])) % 24
    except ValueError:
        return "unknown"
    if 7 <= h < 19:
        return "day"
    if h >= 19 or h < 5:
        return "night"
    return "dawn_dusk"


def points(df: pd.DataFrame, crs: str) -> gpd.GeoDataFrame:
    geom = [Point(xy) for xy in zip(df["lon"].astype(float), df["lat"].astype(float))]
    return gpd.GeoDataFrame(df, geometry=geom, crs="EPSG:4326").to_crs(crs)


def read_taz(cfg) -> gpd.GeoDataFrame:
    taz = gpd.read_file(cfg.files["taz_shapefile"]).rename(columns={"TAZ": "taz_id"})
    return taz.to_crs(cfg.crs)[["taz_id", "geometry"]].copy()


def read_land_use(cfg, crs: str) -> gpd.GeoDataFrame:
    lu = pd.read_csv(cfg.files["land_use_csv"], low_memory=False)
    lu = gpd.GeoDataFrame(lu, geometry=lu["the_geom"].apply(wkt.loads), crs="EPSG:4326").to_crs(crs)
    for c in ["res", "cie", "med", "mips", "retail", "pdr", "visitor", "total", "intersection_density"]:
        lu[c] = numeric(lu[c])
    return lu


def read_segments(cfg, crs: str) -> gpd.GeoDataFrame:
    seg = pd.read_csv(cfg.files["segments_csv"], low_memory=False)
    geom = seg["geometry_wkt"].apply(lambda s: wkt.loads(s) if isinstance(s, str) and s else None)
    seg = seg[geom.notna()].copy()
    return gpd.GeoDataFrame(seg, geometry=geom[geom.notna()], crs="EPSG:4326").to_crs(crs)


def read_hv_crashes(cfg, years) -> gpd.GeoDataFrame:
    hv = pd.read_csv(cfg.files["hv_crashes_csv"])
    hv = hv[hv["city"].astype(str).str.strip().str.upper() == cfg.city].copy()
    hv["year"] = hv["year"].astype(int)
    hv = hv[hv["year"].isin(list(years))].copy()
    return points(hv, cfg.crs)


def read_av_crashes(cfg, years=None) -> gpd.GeoDataFrame:
    av = pd.read_csv(cfg.files["av_crashes_csv"])
    av = av[av["city"].astype(str).str.strip().str.upper() == cfg.city]
    av = av[av["av_mode"].astype(str).str.upper() == cfg.av_mode].copy()
    av["year"] = av["year"].astype(int)
    if years is not None:
        av = av[av["year"].isin(list(years))].copy()
    return points(av, cfg.crs)


def sjoin_zones(pts: gpd.GeoDataFrame, zones: gpd.GeoDataFrame, key: str = "superzone_id") -> gpd.GeoDataFrame:
    out = gpd.sjoin(pts, zones[[key, "geometry"]], how="inner", predicate="intersects")
    return out.drop(columns=["index_right"], errors="ignore")
