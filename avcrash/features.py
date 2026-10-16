"""Zone-year panel: AV and HV crash counts, exposure and covariates.

One row per (superzone_id, year). Columns:
  n_av, n_hv            AV crashes (autonomous mode) and HV crashes in the zone-year
  N_A, N_H              AV and HV vehicle miles traveled in SF that year (millions)
  CANDIDATES            the covariates of the paper's feature table
  STREETVIEW            the Street View covariates (only with streetview=True)
  helper columns        n_hv and night_share (parents of product terms)
"""
from __future__ import annotations

from typing import List

import geopandas as gpd
import numpy as np
import pandas as pd

from . import io

LAND_USE = ["res", "cie", "med", "mips", "retail", "pdr", "visitor"]

# Covariates of the paper's feature table (before screening).
CANDIDATES: List[str] = [
    # land use
    "res_share", "cie_share", "med_share", "mips_share", "retail_share", "pdr_share",
    "intersection_density_mean",
    # ride-hailing demand
    "uber_pickups_mean_per_km2", "uber_dropoffs_mean_per_km2", "uber_total_mean_per_km2",
    # HV crash composition
    "day_share", "dawn_dusk_share",
    "lighting_daylight_share", "lighting_dusk_dawn_share",
    "lighting_dark_street_lights_share", "lighting_dark_no_street_lights_share",
    "weather1_clear_share", "weather1_cloudy_share", "weather1_raining_share",
    "weather1_fog_visibility_share", "weather1_other_share",
    "road_surface_dry_share", "road_surface_wet_share", "road_surface_snow_ice_share",
    "road_surface_slippery_share", "road_surface_other_share",
    "at_intersection_share", "ped_accident_share", "bike_accident_share", "weekend_share",
    # HV severity
    "n_fatal_crashes", "fatal_crash_share", "total_killed", "avg_killed_per_crash",
    "collision_severity_fatal_share", "collision_severity_severe_injury_share",
    "collision_severity_other_injury_share", "collision_severity_pain_share",  # pain = complaint of pain
    # products
    "hv_x_intersection_share", "night_x_dark_streetlights", "night_x_dark_no_lights",
]

# Street View (VLM) consensus covariates, length-weighted over road segments.
STREETVIEW: List[str] = [
    "lanes_len_weighted_mean", "bus_lane_len_share", "bike_lane_len_share", "crosswalk_len_share",
    "street_parking_len_share", "median_sep_len_share",
    "pavement_asphalt_len_share", "pavement_concrete_len_share", "pavement_cobblestone_len_share",
    "land_use_mixed_use_len_share", "land_use_park_len_share",
    "road_slope_flat_len_share", "road_slope_slight_len_share",
    "road_slope_moderate_len_share", "road_slope_steep_len_share",
    "bus_len_x_intersection_share", "ped_x_crosswalk_len_share", "bike_x_bikelane_len_share",
]


# --------------------------------------------------------------------------- static covariates
def land_use_features(cfg, zones: gpd.GeoDataFrame) -> pd.DataFrame:
    """Floor-area shares of parcels intersecting each zone, and mean intersection density."""
    lu = io.read_land_use(cfg, zones.crs)
    j = io.sjoin_zones(lu, zones)
    agg = j.groupby("superzone_id")[LAND_USE + ["total"]].sum()
    total = (agg["total"] + agg["res"]).replace(0, np.nan)
    out = pd.DataFrame({f"{c}_share": (agg[c] / total).fillna(0.0) for c in LAND_USE})
    out["intersection_density_mean"] = j.groupby("superzone_id")["intersection_density"].mean()
    return out


def uber_features(cfg, taz_z: pd.DataFrame) -> pd.DataFrame:
    """Sum over the zone's TAZs of the mean (over day x hour cells) pickups / dropoffs."""
    ub = pd.read_csv(cfg.files["uber_csv"]).rename(columns={"taz": "taz_id"})
    for c in ("pickups", "dropoffs"):
        ub[c] = pd.to_numeric(ub[c], errors="coerce").fillna(0.0)
    taz = ub.groupby("taz_id").agg(uber_pickups_mean=("pickups", "mean"), uber_dropoffs_mean=("dropoffs", "mean"))
    taz["uber_total_mean"] = taz["uber_pickups_mean"] + taz["uber_dropoffs_mean"]
    m = taz_z[["taz_id", "superzone_id"]].drop_duplicates().merge(taz.reset_index(), on="taz_id", how="left")
    cols = ["uber_pickups_mean", "uber_dropoffs_mean", "uber_total_mean"]
    m[cols] = m[cols].fillna(0.0)
    return m.groupby("superzone_id")[cols].sum()


def streetview_features(cfg, zones: gpd.GeoDataFrame) -> pd.DataFrame:
    """Length-weighted Street View consensus labels of the road segments intersecting each zone."""
    seg = io.read_segments(cfg, zones.crs)
    seg["seg_len_m"] = seg.geometry.length
    seg["total_lane_count"] = io.numeric(seg["total_lane_count"]).fillna(0.0)
    j = io.sjoin_zones(seg, zones).copy()
    g = j.groupby("superzone_id")
    length = g["seg_len_m"].sum()
    denom = length.replace(0, np.nan)
    out = pd.DataFrame(index=length.index)
    for src, name in [("has_bus_lane", "bus_lane"), ("has_bike_lane", "bike_lane"), ("has_crosswalks", "crosswalk"),
                      ("has_street_parking", "street_parking"), ("has_median_separation", "median_sep")]:
        j["__w"] = io.bool_indicator(j[src]) * j["seg_len_m"]
        out[f"{name}_len_share"] = (j.groupby("superzone_id")["__w"].sum() / denom).fillna(0.0)
    j["__w"] = j["total_lane_count"] * j["seg_len_m"]
    out["lanes_len_weighted_mean"] = (j.groupby("superzone_id")["__w"].sum() / denom).fillna(0.0)
    for src, prefix in [("pavement_type", "pavement"), ("land_use_type", "land_use"), ("road_slope", "road_slope")]:
        c_len = j.assign(__cat=io.category_tokens(j[src])).pivot_table(
            index="superzone_id", columns="__cat", values="seg_len_m", aggfunc="sum", fill_value=0.0)
        shares = c_len.div(c_len.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
        shares.columns = [f"{prefix}_{c}_len_share" for c in shares.columns]
        out = out.join(shares, how="left")
    base = [c for c in STREETVIEW if "_x_" not in c]
    for c in base:
        if c not in out.columns:
            out[c] = 0.0
    return out[base].fillna(0.0)


# --------------------------------------------------------------------------- HV / AV crashes
def hv_features(cfg, zones: gpd.GeoDataFrame, years) -> pd.DataFrame:
    """HV crash count and composition shares per zone-year (zone-years without crashes: 0)."""
    hv = io.sjoin_zones(io.read_hv_crashes(cfg, years), zones)
    key = ["superzone_id", "year"]
    g = hv.groupby(key)
    out = g.size().rename("n_hv").to_frame()

    def shares(labels: pd.Series, prefix: str, suffix: str = "_share") -> pd.DataFrame:
        counts = hv.assign(__c=labels).groupby(key + ["__c"]).size().unstack("__c", fill_value=0)
        s = counts.div(counts.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
        s.columns = [f"{prefix}{c}{suffix}" for c in s.columns]
        return s

    out = out.join(shares(hv["time"].apply(io.time_of_day), ""))
    out = out.join(shares(io.map_codes(hv["lighting"], io.LIGHTING), "lighting_"))
    out = out.join(shares(io.map_codes(hv["weather_1"], io.WEATHER), "weather1_"))
    out["at_intersection_share"] = hv.assign(v=io.yn_indicator(hv["at_intersection"])).groupby(key)["v"].mean()
    out["ped_accident_share"] = hv.assign(v=io.bool_indicator(hv["ped_accident"])).groupby(key)["v"].mean()
    out["bike_accident_share"] = hv.assign(v=io.bool_indicator(hv["bike_accident"])).groupby(key)["v"].mean()
    out = out.join(shares(io.map_codes(hv["road_surface"], io.ROAD_SURFACE), "road_surface_"))
    out = out.join(shares(io.map_codes(hv["collision_severity"], io.SEVERITY), "collision_severity_"))
    weekend = (pd.to_datetime(hv["date"], errors="coerce").dt.dayofweek >= 5).astype(float)
    out["weekend_share"] = hv.assign(v=weekend).groupby(key)["v"].mean()

    fatal = io.numeric(hv["is_fatal"]).fillna(0).astype(int)
    killed = io.numeric(hv["number_killed"]).fillna(0)
    sev = pd.DataFrame({"n_fatal_crashes": hv[fatal == 1].groupby(key).size()})
    sev = out[["n_hv"]].join(sev).join(hv.assign(k=killed).groupby(key)["k"].sum().rename("total_killed"))
    out["n_fatal_crashes"] = sev["n_fatal_crashes"]
    out["total_killed"] = sev["total_killed"]
    out["fatal_crash_share"] = (sev["n_fatal_crashes"] / sev["n_hv"]).fillna(0.0)
    out["avg_killed_per_crash"] = (sev["total_killed"] / sev["n_hv"]).fillna(0.0)

    idx = pd.MultiIndex.from_product([zones["superzone_id"].unique(), list(years)], names=key)
    return out.reindex(idx).fillna(0.0)


def av_counts(cfg, zones: gpd.GeoDataFrame, years) -> pd.Series:
    av = io.sjoin_zones(io.read_av_crashes(cfg, years), zones)
    return av.groupby(["superzone_id", "year"]).size().rename("n_av")


# --------------------------------------------------------------------------- panel
def build_panel(cfg, taz_z, zones, years, streetview: bool = False) -> pd.DataFrame:
    years = [int(y) for y in years]
    static = land_use_features(cfg, zones).join(uber_features(cfg, taz_z), how="outer").fillna(0.0)
    if streetview:
        sv = streetview_features(cfg, zones)
        assert set(sv.index) == set(zones["superzone_id"]), "every zone must contain road segments"
        static = static.join(sv, how="outer")
    static = static.join(zones.set_index("superzone_id")[["area_km2"]], how="left")
    for c in ("uber_pickups_mean", "uber_dropoffs_mean", "uber_total_mean"):
        static[f"{c}_per_km2"] = static[c] / static["area_km2"].replace(0, np.nan)

    hv = hv_features(cfg, zones, years)
    panel = hv[["n_hv"]].join(av_counts(cfg, zones, years), how="left")
    panel["n_av"] = panel["n_av"].fillna(0.0)
    panel = panel.reset_index().merge(static.reset_index(), on="superzone_id", how="left")
    panel = panel.merge(hv.drop(columns="n_hv").reset_index(), on=["superzone_id", "year"], how="left")
    exp = pd.DataFrame([{"year": y, **cfg.exposure[y]} for y in years])
    panel = panel.merge(exp, on="year", how="left")
    for c in panel.columns:
        if c not in ("superzone_id", "year"):
            panel[c] = panel[c].fillna(0.0)

    panel["hv_x_intersection_share"] = panel["n_hv"] * panel["at_intersection_share"]
    panel["night_x_dark_streetlights"] = panel["night_share"] * panel["lighting_dark_street_lights_share"]
    panel["night_x_dark_no_lights"] = panel["night_share"] * panel["lighting_dark_no_street_lights_share"]
    if streetview:
        panel["bus_len_x_intersection_share"] = panel["bus_lane_len_share"] * panel["at_intersection_share"]
        panel["ped_x_crosswalk_len_share"] = panel["ped_accident_share"] * panel["crosswalk_len_share"]
        panel["bike_x_bikelane_len_share"] = panel["bike_accident_share"] * panel["bike_lane_len_share"]

    for c in CANDIDATES + (STREETVIEW if streetview else []):
        if c not in panel.columns:  # category never observed in the data
            panel[c] = 0.0
    keep = ["superzone_id", "year", "n_av", "n_hv", "N_A", "N_H", "area_km2", "night_share"]
    keep += CANDIDATES + (STREETVIEW if streetview else [])
    return panel[keep].reset_index(drop=True)
