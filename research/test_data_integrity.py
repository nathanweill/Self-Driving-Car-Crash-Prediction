"""Tests for errors that would materially alter exposure or crash geography."""
import pandas as pd
import pytest
from build_waymo_exposure import unique_exposure, difference, s2_polygon, VARS
from build_sfcta_exposure import deduplicate_daily_volumes
from geocode_waymo import canonical


def snapshot(miles, cells=None):
    return pd.DataFrame({"S2 Cell": cells or ["9260949341382639616"] * len(miles),
                         "Location": ["SAN_FRANCISCO"] * len(miles),
                         VARS[0]: [100.] * len(miles), VARS[1]: miles})


def test_outcome_rows_count_mileage_once():
    assert unique_exposure(snapshot([12., 12., 12.]))[VARS[1]].sum() == 12.


def test_outcome_exposure_conflict_is_rejected():
    with pytest.raises(ValueError): unique_exposure(snapshot([12., 13.]))


def test_missing_cell_is_not_zero_mileage():
    d = difference(snapshot([12.], ["a"]), snapshot([13.], ["b"]))
    assert d.waymo_miles_increment.isna().all()
    assert set(d.status) == {"missing_end_snapshot", "missing_start_snapshot"}


def test_negative_release_revision_is_preserved():
    d = difference(snapshot([12.]), snapshot([9.]))
    assert d.iloc[0].status == "negative_revision"
    assert d.iloc[0].waymo_miles_increment == -3


def test_unsigned_64bit_s2_id_keeps_precision():
    p = s2_polygon("9260949341382639616")
    assert p.is_valid and -123 < p.centroid.x < -122 and 37 < p.centroid.y < 38


def test_daily_vmt_not_doubled_by_am_pm():
    d = pd.DataFrame({"cmp_segid": [1, 1], "date": ["2021-01"] * 2, "period": ["AM", "PM"], "imp_vol": [100, 100]})
    assert deduplicate_daily_volumes(d).imp_vol.sum() == 100
    d.loc[1, "imp_vol"] = 101
    with pytest.raises(ValueError): deduplicate_daily_volumes(d)


def test_duplicate_segment_period_rejected():
    d = pd.DataFrame({"cmp_segid": [1, 1], "date": ["2021-01"] * 2, "period": ["AM", "AM"], "imp_vol": [100, 100]})
    with pytest.raises(ValueError): deduplicate_daily_volumes(d)


def test_street_number_suffix_and_direction_preserved():
    assert canonical("03RD ST") == canonical("3rd Street")
    assert canonical("S. Van Ness Avenue") == "S VAN NESS AVE"
    assert canonical("3rd Street") != canonical("3rd Avenue")
    assert canonical("O’Farrell Street") == "OFARRELL ST"


def test_written_sf_street_variants():
    assert canonical("Bayshore Boulevard") == canonical("BAY SHORE BLVD")
    assert canonical("St. Germain Avenue") == canonical("SAINT GERMAIN AVE")
