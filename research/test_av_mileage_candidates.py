import numpy as np
import pandas as pd
from build_av_mileage_candidates import pava, OUT


def test_monotone_fit_preserves_information_instead_of_clipping_increments():
    np.testing.assert_allclose(pava([0,3,2,5]),[0,2.5,2.5,5])
    np.testing.assert_allclose(pava([4,3,2,1]),[2.5]*4)


def test_all_candidates_cover_65_zones_and_five_years():
    d=pd.read_csv(OUT/'combined_zone_year_all_candidates.csv')
    assert len(d)==3250
    assert not d.duplicated(['candidate','scope','year','superzone_id']).any()
    assert d.groupby(['candidate','scope','year']).size().eq(65).all()
    assert np.isfinite(d.av_mileage_miles).all() and d.av_mileage_miles.gt(0).all()
    np.testing.assert_allclose(d.av_mileage_miles,d.testing_excluding_waymo_driverless+d.waymo_rider_only+d.cruise_commercial)


def test_waymo_driverless_testing_not_double_counted():
    d=pd.read_csv(OUT/'operator_zone_year_all_candidates.csv.gz')
    assert not ((d.operator=='WAYMO')&(d['mode']=='driverless')).any()
    assert set(d.loc[d.operator.eq('WAYMO'),'mode'])=={'drivered','rider_only_testing_plus_commercial'}
    sums=d.groupby(['candidate','scope','year','operator','mode']).agg(total=('av_mileage_miles','sum'),anchor=('stream_operator_total_miles','first'))
    np.testing.assert_allclose(sums.total,sums.anchor,atol=1e-6)


def test_december_forecast_separate_from_june_cutoff():
    monthly=pd.read_csv(OUT/'testing_operator_monthly_estimates.csv')
    for _,g in monthly[monthly.year.eq(2025)].groupby(['operator','mode']):
        np.testing.assert_allclose(g.loc[g.month.eq(12),'statewide_miles'].iloc[0],g.loc[g.month.isin([9,10,11]),'statewide_miles'].mean())
    totals=pd.read_csv(OUT/'testing_cruise_operator_period_totals.csv')
    early=totals[(totals.year==2025)&totals.scope.eq('through_june15_2025')]
    assert early.estimated_december_sf_miles.eq(0).all()
    assert early.window_end.eq('2025-06-15').all()


def test_raw_cruise_blanks_are_retained_not_called_observed_zero():
    d=pd.read_csv(OUT/'cruise_public_monthly_evidence.csv')
    dec=d[(d.year==2023)&(d.month==12)].iloc[0]
    assert pd.isna(dec.miles) and dec.cpuc_value_status=='blank_not_observed_zero'
    np.testing.assert_allclose(d[d.year.eq(2022)].miles.sum(),51702.38)
    np.testing.assert_allclose(d[d.year.eq(2023)].miles.sum(),373929.73)


def test_fitted_waymo_curves_monotone_and_adjustments_auditable():
    for geo in ['county_adjusted','legacy_labels']:
        d=pd.read_csv(OUT/f'waymo_cumulative_audit_{geo}.csv',dtype={'s2_cell':str})
        for _,g in d.groupby('s2_cell'):
            assert (np.diff(g.sort_values('snapshot').fitted_cumulative_miles)>=-1e-7).all()
        assert d.status.str.contains('missing_snapshot').any()
        np.testing.assert_allclose(d.adjustment_miles.dropna(),(d.fitted_cumulative_miles-d.reconciled_input_miles).dropna(),atol=1e-7)


def test_upper_scenario_and_matching_windows():
    d=pd.read_csv(OUT/'combined_zone_year_all_candidates.csv')
    a=d[d.candidate.eq('hybrid_hpms')].set_index(['scope','year','superzone_id'])
    b=d[d.candidate.eq('testing_sf_upper')].set_index(['scope','year','superzone_id'])
    assert (b.av_mileage_miles>=a.av_mileage_miles-1e-6).all()
    np.testing.assert_allclose(a.waymo_rider_only,b.waymo_rider_only)
    full=a.loc['calendar_year'].groupby('year').av_mileage_miles.sum()
    cut=a.loc['through_june15_2025'].groupby('year').av_mileage_miles.sum()
    np.testing.assert_allclose(full.loc[2021:2024],cut.loc[2021:2024])
    assert full.loc[2025]>cut.loc[2025]
