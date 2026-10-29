"""Source checks, conservation, missingness, and temporal coverage invariants."""
import json
import numpy as np
import pandas as pd

from build_service_activity import ROOT, OUT


def test_tract_codes_and_vintages_are_valid_and_unambiguous():
    d = pd.read_csv(OUT/'cpuc_sf_tract_month_records.csv.gz', dtype={'tract_geoid': str})
    assert d.tract_geoid.str.fullmatch(r'06075\d{6}').all()
    assert not d.duplicated(['operator', 'mode', 'date', 'tract_geoid']).any()
    assert not d.unmatched_tract_code.any()
    assert d.vintage_status.eq('identified_by_valid_tract_codes').all()
    assert set(d[d.operator.eq('Cruise')].tract_vintage) == {2020}
    assert set(d[d.operator.eq('Waymo') & d.date.eq('2024-12')].tract_vintage) == {2010}
    assert set(d[d.operator.eq('Waymo') & d.date.eq('2026-06')].tract_vintage) == {2020}


def test_public_trip_benchmarks_and_month_interpretation():
    raw = pd.read_csv(OUT/'cpuc_sf_tract_month_records.csv.gz')
    ca = pd.read_csv(OUT/'cpuc_california_monthly_trips.csv').set_index(['operator', 'date'])
    dec = raw[raw.operator.eq('Waymo') & raw.date.eq('2024-12')]
    assert dec.TripsStart_numeric.sum() == 400731
    assert ca.loc[('Waymo', '2024-12'), 'total_trips_ca'] == 541378
    assert ca.loc[('Waymo', '2026-06'), 'total_trips_ca'] == 1348926
    assert raw[raw.operator.eq('Cruise')].date.nunique() == 17
    assert raw[raw.operator.eq('Waymo') & raw.TripsStart_numeric.notna()].date.nunique() == 32


def test_tract_allocation_preserves_unassigned_geography():
    w = pd.read_csv(OUT/'tract_to_zone_weights.csv')
    for allocation in ['centerline', 'area']:
        totals = w.groupby(['tract_vintage', 'tract_geoid'])[allocation+'_weight'].sum()
        assert totals.ge(0).all() and totals.le(1+1e-7).all()
        assert totals.lt(.99).any(), 'Outside-zone geography must not be normalized into the study'
    c = pd.read_csv(OUT/'cpuc_monthly_coverage.csv')
    valid = c[c.all_reported_counts_numeric]
    assert (valid.zone_starts_sum <= valid.sf_trip_starts_sum+1e-6).all()
    assert (valid.zone_ends_sum <= valid.sf_trip_ends_sum+1e-6).all()
    z = pd.read_csv(OUT/'cpuc_zone_month_trip_activity.csv')
    summed = z.groupby(['operator', 'mode', 'date', 'allocation']).trip_starts_allocated.sum(min_count=1)
    reported = c.set_index(['operator', 'mode', 'date', 'allocation']).zone_starts_sum.reindex(summed.index)
    np.testing.assert_allclose(summed, reported, equal_nan=True)


def test_redactions_and_absent_reports_never_become_reported_zero():
    for allocation in ['centerline', 'area']:
        d = pd.read_csv(OUT/f'zone_month_covariates_{allocation}.csv')
        recent = d[d.date.ge('2025-01')]
        assert recent.waymo_reported_trip_starts_allocated.isna().all()
        assert recent.waymo_reported_trip_ends_allocated.isna().all()
        assert recent.waymo_trip_count_status.eq('redacted_or_missing_counts').all()
        assert d[d.date.isin(['2023-06', '2023-07'])].waymo_reported_trip_starts_allocated.isna().all()
        assert d[d.date.ge('2023-11')].cruise_reported_trip_starts_allocated.isna().all()
        assert d[d.date.lt('2024-08')].waymo_ro_month_miles.isna().all()


def test_mileage_intervals_and_month_splits_conserve_fitted_miles():
    cells = pd.read_csv(OUT/'waymo_cell_activity_intervals.csv', dtype={'s2_cell': str})
    fitted = pd.read_csv(ROOT/'outputs/av_mileage_candidates/waymo_cumulative_audit_county_adjusted.csv', dtype={'s2_cell': str})
    curve = fitted.pivot(index='s2_cell', columns='snapshot', values='fitted_cumulative_miles')
    summed = cells.groupby('s2_cell').interval_miles.sum().reindex(curve.index)
    np.testing.assert_allclose(summed, curve[202606]-curve[202407], atol=1e-6)
    monthly = pd.read_csv(OUT/'waymo_zone_month_activity.csv')
    interval = pd.read_csv(OUT/'waymo_zone_activity_intervals.csv')
    keys = ['allocation', 'superzone_id', 'interval_start', 'interval_end_exclusive']
    z = monthly.groupby(keys).waymo_ro_month_miles.sum()
    np.testing.assert_allclose(z, interval.set_index(keys).waymo_ro_interval_miles.reindex(z.index))
    a = pd.read_csv(OUT/'waymo_activity_interval_audit.csv')
    np.testing.assert_allclose(a.study_zone_interval_miles+a.unallocated_miles, a.sf_reconciled_interval_miles)
    assert a.unallocated_miles.ge(-1e-6).all()
    assert set(monthly.date) == set(pd.period_range('2024-08', '2026-06', freq='M').astype(str))


def test_activity_support_never_calls_imputed_or_revised_endpoint_observed():
    c = pd.read_csv(OUT/'waymo_cell_activity_intervals.csv')
    published = c[c.published_positive_cell]
    assert published.raw_input_delta.gt(0).all()
    assert not published.endpoint_imputed.any() and not published.endpoint_monotone_adjusted.any()
    d = pd.read_csv(OUT/'waymo_zone_month_activity.csv')
    for col in [c for c in d if c.endswith('_road_fraction')]:
        assert d[col].between(-1e-9, 1+1e-9).all()
    assert (d.waymo_100mi_daily_cell_road_fraction <= d.waymo_positive_mileage_cell_road_fraction+1e-9).all()
    assert (d.waymo_published_positive_cell_road_fraction <= d.waymo_positive_mileage_cell_road_fraction+1e-9).all()
    assert d.waymo_endpoint_imputation_road_fraction.gt(0).any()
    assert d.waymo_endpoint_revision_road_fraction.gt(0).any()


def test_monthly_traffic_matches_city_anchor_and_retains_imputation():
    d = pd.read_csv(OUT/'zone_month_traffic_context.csv')
    for _, g in d.groupby('date'):
        np.testing.assert_allclose(g.traffic_vmt_estimate.sum(), g.citywide_daily_vmt_million.iloc[0]*1e6*g.days.iloc[0])
    assert d[d.superzone_id.eq(31)].traffic_whole_zone_imputed.all()
    assert d.traffic_vmt_estimate.gt(0).all()
    assert d.traffic_segment_month_imputation.any()
    for _, g in d[d.date.str.startswith('2024')].groupby('superzone_id'):
        np.testing.assert_allclose(np.average(g.traffic_daily_index_2024_mean, weights=g.days), 1)


def test_ca_scaled_trip_candidate_preserves_december_pattern_and_anchor():
    d = pd.read_csv(OUT/'waymo_recent_trip_estimates.csv')
    ca = pd.read_csv(OUT/'cpuc_california_monthly_trips.csv')
    ca = ca[ca.operator.eq('Waymo')].set_index('date').total_trips_ca
    trips = pd.read_csv(OUT/'cpuc_zone_month_trip_activity.csv')
    for audit in json.loads((OUT/'trip_estimation_calibration.json').read_text()):
        allocation = audit['allocation']
        dec = trips[trips.operator.eq('Waymo') & trips.allocation.eq(allocation) & trips.date.eq('2024-12')].set_index('superzone_id').trip_starts_allocated
        for date, g in d[d.allocation.eq(allocation)].groupby('date'):
            s = g.set_index('superzone_id').waymo_trips_estimate_ca_scaled_static.reindex(dec.index)
            np.testing.assert_allclose(s.sum(), ca.loc[date]*audit['dec_2024_study_to_ca_trip_ratio'])
            np.testing.assert_allclose(s/s.sum(), dec/dec.sum())


def test_mileage_scaled_trip_candidate_tracks_current_mileage_distribution():
    d = pd.read_csv(OUT/'waymo_recent_trip_estimates.csv')
    m = pd.read_csv(OUT/'waymo_zone_month_activity.csv')
    assert d.date.nunique() == 18 and d.date.min() == '2025-01' and d.date.max() == '2026-06'
    for audit in json.loads((OUT/'trip_estimation_calibration.json').read_text()):
        allocation = audit['allocation']
        for date, g in d[d.allocation.eq(allocation)].groupby('date'):
            q = m[m.allocation.eq(allocation) & m.date.eq(date)].set_index('superzone_id')
            s = g.set_index('superzone_id').waymo_trips_estimate_ro_scaled_dynamic.reindex(q.index)
            np.testing.assert_allclose(s.sum(), q.sf_reconciled_month_miles.iloc[0]*audit['study_trips_per_sf_ro_mile'])
            np.testing.assert_allclose(s/s.sum(), q.waymo_ro_study_zone_share)
    assert not np.allclose(d.waymo_trips_estimate_ca_scaled_static, d.waymo_trips_estimate_ro_scaled_dynamic)


def test_authority_windows_respect_effective_dates_at_day_resolution():
    d = pd.read_csv(OUT/'service_authority_month_calendar.csv').set_index('date')
    np.testing.assert_allclose(d.loc['2022-06', 'cruise_2022_23_paid_authority_window_day_fraction'], 29/30)
    np.testing.assert_allclose(d.loc['2023-08', 'waymo_post_expanded_authority_day_fraction'], 22/31)
    np.testing.assert_allclose(d.loc['2023-10', 'cruise_2023_expanded_authority_window_day_fraction'], 23/31)
    np.testing.assert_allclose(d.loc['2023-10', 'cruise_post_2023_suspension_day_fraction'], 8/31)
    assert d.loc['2023-11', 'cruise_2022_23_paid_authority_window_day_fraction'] == 0


def test_all_joinable_keys_are_complete_and_numeric_values_are_finite():
    for allocation in ['centerline', 'area']:
        d = pd.read_csv(OUT/f'zone_month_covariates_{allocation}.csv')
        assert len(d) == 4290 and d.superzone_id.nunique() == 65
        assert not d.duplicated(['superzone_id', 'date']).any()
        assert d.groupby('date').size().eq(65).all()
        for col in d.select_dtypes('number'):
            assert np.isfinite(d[col].dropna()).all()
        annual = pd.read_csv(OUT/f'zone_year_covariates_{allocation}.csv')
        h1 = pd.read_csv(OUT/f'zone_2026_h1_covariates_{allocation}.csv')
        assert len(annual) == 325 and not annual.duplicated(['superzone_id', 'year']).any()
        assert annual.period_months.eq(12).all()
        assert len(h1) == 65 and h1.period_months.eq(6).all() and h1.period_days.eq(181).all()


def test_partial_year_coverage_is_not_mislabeled_as_full_year_observation():
    for allocation in ['centerline', 'area']:
        d = pd.read_csv(OUT/f'zone_year_covariates_{allocation}.csv')
        y24 = d[d.year.eq(2024)]
        assert y24.waymo_ro_month_miles_available_months.eq(5).all()
        assert y24.waymo_ro_daily_miles_available_days.eq(153).all()
        assert y24.waymo_reported_trip_starts_allocated_available_months.eq(12).all()
        y23 = d[d.year.eq(2023)]
        assert y23.waymo_reported_trip_starts_allocated_available_months.eq(10).all()
        assert y23.cruise_reported_trip_starts_allocated_available_months.eq(10).all()
        y21 = d[d.year.eq(2021)]
        assert y21.waymo_reported_trip_starts_allocated_sum_available_months.isna().all()
        assert y21.waymo_reported_trip_starts_allocated_available_months.eq(0).all()
