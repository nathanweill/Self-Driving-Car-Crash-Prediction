import json
import numpy as np
import pandas as pd
from refine_waymo_geocoding import OUT, ROOT, normalize_public_coordinate


def test_source_rows_preserved_and_48_accounted_for():
    original=pd.read_csv(ROOT/'outputs/waymo_sf_geocoding.csv')
    refined=pd.read_csv(OUT/'waymo_sf_geocoding_refined.csv')
    assert len(refined)==757 and refined.source_csv_row.equals(original.source_csv_row)
    assert refined['SGO Report ID'].equals(original['SGO Report ID'])
    assert refined['Location Address / Description'].equals(original['Location Address / Description'])
    np.testing.assert_allclose(refined.original_longitude,original.longitude,equal_nan=True)
    audit=pd.read_csv(OUT/'original_48_resolution_audit.csv')
    assert len(audit)==48
    assert audit.longitude.notna().sum()==40
    assert (audit.longitude.isna()&audit.candidate_point_count.gt(0)).sum()==1
    assert (~audit.sf_scope_candidate).sum()==1
    assert (audit.sf_scope_candidate&audit.candidate_point_count.eq(0)).sum()==6


def test_public_axis_swap_is_narrow_and_audited():
    p,status=normalize_public_coordinate(37.78758,-122.39524)
    q,ok=normalize_public_coordinate(-122.39524,37.78758)
    assert status=='latitude_longitude_swapped' and ok=='as_published' and p.distance(q)<1e-8
    assert normalize_public_coordinate(-84.35,33.77)[0] is None
    d=pd.read_csv(OUT/'waymo_sf_geocoding_refined.csv')
    row=d[d['SGO Report ID'].eq('30270-15559')].iloc[0]
    assert row.tims_coordinate_status=='latitude_longitude_swapped'
    assert row.geocode_method=='tims_public_coordinate_axis_corrected'


def test_conflicting_source_coordinates_do_not_replace_descriptions():
    c=pd.read_csv(OUT/'public_coordinate_conflicts.csv')
    assert len(c)==15 and c.public_description_distance_m.min()>300
    np.testing.assert_allclose(c.longitude,c.original_longitude)
    np.testing.assert_allclose(c.latitude,c.original_latitude)
    np.testing.assert_allclose(c.point_zone_id,c.original_point_zone_id)


def test_allocations_conserve_supported_records_and_exclude_atlanta():
    d=pd.read_csv(OUT/'waymo_sf_geocoding_refined.csv')
    weights=pd.read_csv(OUT/'zone_allocation_sensitivities.csv')
    for col in ['equal_candidate_weight','buffer_area_weight']:
        np.testing.assert_allclose(weights.groupby(['source_csv_row','scenario'])[col].sum(),1)
    assert weights.groupby('scenario').source_csv_row.nunique().eq(750).all()
    excluded=d[d['SGO Report ID'].eq('30270-15497')].iloc[0]
    assert not excluded.sf_scope_candidate and pd.isna(excluded.longitude)
    assert excluded.source_csv_row not in set(weights.source_csv_row)
    unresolved=set(pd.read_csv(OUT/'unresolved_locations.csv').source_csv_row)
    assert not unresolved & set(weights.source_csv_row)


def test_multiple_junctions_are_not_averaged_into_a_fake_point():
    d=pd.read_csv(OUT/'waymo_sf_geocoding_refined.csv')
    r=d[d['SGO Report ID'].eq('30270-11362')].iloc[0]
    assert r.candidate_point_count==2 and pd.isna(r.longitude)
    assert r.geocode_method=='multiple_junction_candidates'
    assert isinstance(r.zone_candidates,str) and len(r.zone_candidates)>0


def test_h1_comparison_preserves_selected_events_and_point_assignments():
    d=pd.read_csv(OUT/'h1_injury_allocation_comparison.csv')
    assert len(d)==65
    cols=['original_point_count','refined_point_count','original_equal_candidate_count','refined_equal_candidate_count','refined_buffer_area_count']
    np.testing.assert_allclose(d[cols].sum(),8)
    np.testing.assert_allclose(d.original_point_count,d.refined_point_count)
    assert not np.allclose(d.original_equal_candidate_count,d.refined_equal_candidate_count)
