"""Retrospective service/activity covariates; never fit to crash outcomes.

Permission dates, reconstructed driving activity, allocated reported trips, and
estimated trips are distinct fields. None is a polygon of legal service access
or a count of requests/unmet demand. See SERVICE_ACTIVITY_DELIVERY.md.
"""
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from build_human_mileage_candidates import expand_network, calibrate

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'outputs/service_activity'
DATES = pd.period_range('2021-01', '2026-06', freq='M')


def next_month(snapshot):
    return (pd.Period(str(snapshot), freq='M') + 1).start_time


def activity(zones):
    """Difference fitted cumulative cell miles, then split by calendar days.

    Keep crosswalk losses instead of allocating outside-zone miles to the study
    area. Do not use the exposure pipeline's human-share regularization here:
    that would manufacture apparent activity where no positive cell exists.
    """
    d = pd.read_csv(ROOT/'outputs/av_mileage_candidates/waymo_cumulative_audit_county_adjusted.csv', dtype={'s2_cell': str})
    cross = pd.read_csv(ROOT/'outputs/s2_to_superzone_weights.csv', dtype={'S2 Cell': str}).rename(columns={'S2 Cell': 's2_cell'})
    snapshots = sorted(d.snapshot.unique())
    cells, intervals, months, totals = [], [], [], []
    for before, after in zip(snapshots[:-1], snapshots[1:]):
        a = d[d.snapshot.eq(before)].set_index('s2_cell')
        b = d[d.snapshot.eq(after)].set_index('s2_cell').reindex(a.index)
        start, end = next_month(before), next_month(after)
        days = (end-start).days
        c = pd.DataFrame({'s2_cell': a.index,
                          'interval_start': str(start.date()),
                          'interval_end_exclusive': str(end.date()),
                          'interval_days': days,
                          'from_snapshot': int(before), 'to_snapshot': int(after),
                          'interval_miles': (b.fitted_cumulative_miles-a.fitted_cumulative_miles).values,
                          'raw_input_delta': (b.reconciled_input_miles-a.reconciled_input_miles).values,
                          'endpoint_imputed': (a.reconciled_input_miles.isna() | b.reconciled_input_miles.isna()).values,
                          'endpoint_monotone_adjusted': (a.status.eq('monotone_adjusted') | b.status.eq('monotone_adjusted')).values})
        assert c.interval_miles.ge(-1e-7).all()
        c['cell_daily_miles'] = c.interval_miles/days
        c['positive_cell'] = c.interval_miles.gt(1e-7)
        c['high_activity_cell'] = c.cell_daily_miles.ge(100)
        c['published_positive_cell'] = c.raw_input_delta.gt(1e-7) & ~c.endpoint_imputed & ~c.endpoint_monotone_adjusted
        cells.append(c)
        h = cross.merge(c, on='s2_cell', validate='many_to_one')
        road_denominator = h.groupby('superzone_id').zone_cell_surface_centerline_m.sum().reindex(zones)
        road_features = {}
        for flag, column in [('positive_cell', 'waymo_positive_mileage_cell_road_fraction'),
                             ('high_activity_cell', 'waymo_100mi_daily_cell_road_fraction'),
                             ('published_positive_cell', 'waymo_published_positive_cell_road_fraction'),
                             ('endpoint_imputed', 'waymo_endpoint_imputation_road_fraction'),
                             ('endpoint_monotone_adjusted', 'waymo_endpoint_revision_road_fraction')]:
            numerator = (h.zone_cell_surface_centerline_m*h[flag]).groupby(h.superzone_id).sum().reindex(zones)
            road_features[column] = numerator/road_denominator.replace(0, np.nan)
        for allocation in ['centerline', 'area']:
            h['allocated_miles'] = h.interval_miles*h[allocation+'_weight']
            g = h.groupby('superzone_id').allocated_miles.sum().reindex(zones, fill_value=0)
            z = pd.DataFrame({'superzone_id': zones, 'allocation': allocation,
                              'interval_start': str(start.date()), 'interval_end_exclusive': str(end.date()),
                              'interval_days': days, 'waymo_ro_interval_miles': g.values,
                              'waymo_ro_daily_miles': g.values/days,
                              'waymo_ro_study_zone_share': (g/g.sum()).values,
                              'mapped_cell_road_length_m': road_denominator.values})
            for col, values in road_features.items(): z[col] = values.values
            intervals.append(z)
            totals.append({'allocation': allocation, 'interval_start': str(start.date()),
                           'interval_end_exclusive': str(end.date()), 'interval_days': days,
                           'sf_reconciled_interval_miles': float(c.interval_miles.sum()),
                           'study_zone_interval_miles': float(g.sum()),
                           'unallocated_miles': float(c.interval_miles.sum()-g.sum()),
                           'imputed_endpoint_cells': int(c.endpoint_imputed.sum()),
                           'revised_endpoint_cells': int(c.endpoint_monotone_adjusted.sum())})
            for period in pd.period_range(start, end-pd.Timedelta(days=1), freq='M'):
                m = z.drop(columns=['waymo_ro_interval_miles']).copy()
                m['date'] = str(period)
                m['waymo_ro_month_miles'] = m.waymo_ro_daily_miles*period.days_in_month
                m['sf_reconciled_month_miles'] = c.interval_miles.sum()*period.days_in_month/days
                m['waymo_activity_status'] = 'reconstructed_interval_miles_uniform_daily_split'
                months.append(m)
    pd.concat(cells, ignore_index=True).to_csv(OUT/'waymo_cell_activity_intervals.csv', index=False)
    pd.concat(intervals, ignore_index=True).to_csv(OUT/'waymo_zone_activity_intervals.csv', index=False)
    pd.DataFrame(totals).to_csv(OUT/'waymo_activity_interval_audit.csv', index=False)
    monthly = pd.concat(months, ignore_index=True)
    monthly.to_csv(OUT/'waymo_zone_month_activity.csv', index=False)
    return monthly


def traffic(zones):
    """Monthly application of Category 1 expansion, with monthly city anchors."""
    source = pd.read_csv(ROOT/'outputs/sfcta_zone_month_vmt_proxy.csv')
    coverage = pd.read_csv(ROOT/'outputs/sfcta_zone_road_coverage.csv')
    coverage26 = pd.read_csv(ROOT/'outputs/extension_2026_h1/sfcta_expansion_audit.csv')[['superzone_id', 'official_surface_centerline_m', 'surface_centerline_within_20m_cmp_m']]
    segment = pd.read_csv(ROOT/'outputs/extension_2026_h1/segment_month_volume_audit.csv')
    cross = pd.read_csv(ROOT/'outputs/sfcta_segment_to_zone.csv')
    joined = segment.merge(cross[['cmp_segid', 'superzone_id', 'allocated_source_length_miles']], on='cmp_segid', validate='many_to_many')
    joined['month_vmt'] = joined.imp_vol*joined.allocated_source_length_miles*joined.days
    source26 = joined.groupby(['superzone_id', 'date']).month_vmt.sum(min_count=1).rename('partial_network_month_vmt_proxy').reset_index()
    imputed26 = joined.groupby(['superzone_id', 'date']).volume_imputed.any()
    city = pd.read_json(ROOT/'raw/sfcta/citywide_vmt.json')
    city = city[city.fac_typ.eq('Citywide') & city.viz.eq('VMT')].copy()
    city['date'] = pd.to_datetime(city.date).dt.strftime('%Y-%m')
    assert city.groupby('date').metric.nunique().eq(1).all(), 'AM/PM rows must be identical, not summed'
    daily_million = city.groupby('date').metric.first()
    k = json.loads((ROOT/'outputs/human_mileage_candidates/validation.json').read_text())['shrinkage_length_m']
    rows = []
    for period in DATES:
        date = str(period)
        h1 = period.year == 2026
        src = source26 if h1 else source
        c = coverage26 if h1 else coverage
        p = src[src.date.eq(date)].set_index('superzone_id').partial_network_month_vmt_proxy.reindex(zones)
        frame = c.set_index('superzone_id').reindex(zones).copy()
        # This helper's legacy column name denotes the supplied period total.
        frame['partial_network_annual_vmt_proxy'] = p
        expanded = calibrate(expand_network(frame.reset_index(), .5, k), daily_million.loc[date]*period.days_in_month)
        expanded['date'] = date
        expanded['days'] = period.days_in_month
        expanded['traffic_vmt_estimate'] = expanded.human_mileage_miles
        expanded['traffic_daily_vmt_estimate'] = expanded.human_mileage_miles/period.days_in_month
        expanded['traffic_imputed_road_share'] = expanded.imputed_share_before_calibration
        expanded['traffic_whole_zone_imputed'] = expanded.source_missing
        expanded['traffic_segment_month_imputation'] = [bool(imputed26.get((zid, date), False)) if h1 else False for zid in expanded.superzone_id]
        expanded['citywide_daily_vmt_million'] = daily_million.loc[date]
        rows.append(expanded[['superzone_id', 'date', 'days', 'traffic_vmt_estimate', 'traffic_daily_vmt_estimate',
                              'traffic_imputed_road_share', 'traffic_whole_zone_imputed',
                              'traffic_segment_month_imputation', 'citywide_daily_vmt_million']])
    result = pd.concat(rows, ignore_index=True)
    base = result[result.date.str.startswith('2024')].groupby('superzone_id').agg(miles=('traffic_vmt_estimate', 'sum'), days=('days', 'sum'))
    result['traffic_daily_index_2024_mean'] = result.traffic_daily_vmt_estimate/result.superzone_id.map(base.miles/base.days)
    result['traffic_status'] = 'sfcta_expanded_city_calibrated_all_vehicle_proxy'
    result.to_csv(OUT/'zone_month_traffic_context.csv', index=False)
    return result


def day_fraction(period, start, end=None):
    a, b = period.start_time, (period+1).start_time
    lo = max(a, pd.Timestamp(start))
    hi = min(b, pd.Timestamp(end)) if end else b
    return max(0, (hi-lo).days)/period.days_in_month


def calendar():
    events = json.loads((ROOT/'inputs/service_authority_events.json').read_text())
    event_dates = {(x['operator'], x['event']): x['date'] for x in events}
    waymo = event_dates['Waymo', 'expanded_paid_driverless_authority']
    cruise = event_dates['Cruise', 'restricted_paid_driverless_authority']
    expanded = event_dates['Cruise', 'expanded_paid_driverless_authority']
    suspended = event_dates['Cruise', 'deployment_and_driverless_testing_suspended']
    rows = []
    for p in DATES:
        rows.append({'date': str(p),
                     'waymo_post_expanded_authority_day_fraction': day_fraction(p, waymo),
                     'cruise_2022_23_paid_authority_window_day_fraction': day_fraction(p, cruise, suspended),
                     'cruise_2023_expanded_authority_window_day_fraction': day_fraction(p, expanded, suspended),
                     'cruise_post_2023_suspension_day_fraction': day_fraction(p, suspended)})
    d = pd.DataFrame(rows)
    d.to_csv(OUT/'service_authority_month_calendar.csv', index=False)
    return d


def recent_trip_estimates(mileage, allocated, ca):
    """Two alternatives for the 18 redacted Waymo months, with fixed calibration."""
    estimates, audit = [], []
    ca = ca[ca.operator.eq('Waymo')].set_index('date').total_trips_ca
    for allocation in ['centerline', 'area']:
        trips = allocated[allocated.operator.eq('Waymo') & allocated.allocation.eq(allocation)]
        dec = trips[trips.date.eq('2024-12')].set_index('superzone_id').trip_starts_allocated
        study_ca_share = dec.sum()/ca.loc['2024-12']
        baseline_trips = trips[trips.date.between('2024-08', '2024-12')].trip_starts_allocated.sum()
        m = mileage[mileage.allocation.eq(allocation)].copy()
        baseline_miles = m[m.date.between('2024-08', '2024-12')].groupby('date').sf_reconciled_month_miles.first().sum()
        trips_per_mile = baseline_trips/baseline_miles
        new = m[m.date.between('2025-01', '2026-06')].copy()
        new['waymo_trips_estimate_ca_scaled_static'] = new.date.map(ca)*study_ca_share*new.superzone_id.map(dec/dec.sum())
        new['waymo_trips_estimate_ro_scaled_dynamic'] = new.sf_reconciled_month_miles*trips_per_mile*new.waymo_ro_study_zone_share
        new['recent_trip_status'] = 'estimated_redacted_tract_counts_two_alternatives'
        estimates.append(new[['superzone_id', 'date', 'allocation', 'waymo_trips_estimate_ca_scaled_static', 'waymo_trips_estimate_ro_scaled_dynamic', 'recent_trip_status']])
        audit.append({'allocation': allocation, 'static_calibration_month': '2024-12',
                      'dec_2024_study_allocated_trip_starts': float(dec.sum()),
                      'dec_2024_ca_total_trips': float(ca.loc['2024-12']),
                      'dec_2024_study_to_ca_trip_ratio': float(study_ca_share),
                      'dynamic_calibration_months': ['2024-08', '2024-09', '2024-10', '2024-11', '2024-12'],
                      'calibration_study_trip_starts': float(baseline_trips),
                      'calibration_sf_reconciled_ro_miles': float(baseline_miles),
                      'study_trips_per_sf_ro_mile': float(trips_per_mile)})
    (OUT/'trip_estimation_calibration.json').write_text(json.dumps(audit, indent=2)+'\n')
    d = pd.concat(estimates, ignore_index=True)
    d.to_csv(OUT/'waymo_recent_trip_estimates.csv', index=False)
    return d


SUM_FEATURES = ['traffic_vmt_estimate', 'waymo_ro_month_miles',
                'waymo_reported_trip_starts_allocated', 'waymo_reported_trip_ends_allocated',
                'cruise_reported_trip_starts_allocated', 'cruise_reported_trip_ends_allocated',
                'waymo_trips_estimate_ca_scaled_static', 'waymo_trips_estimate_ro_scaled_dynamic']
MEAN_FEATURES = ['traffic_daily_index_2024_mean', 'waymo_ro_daily_miles',
                 'waymo_positive_mileage_cell_road_fraction', 'waymo_100mi_daily_cell_road_fraction',
                 'waymo_published_positive_cell_road_fraction',
                 'waymo_endpoint_imputation_road_fraction', 'waymo_endpoint_revision_road_fraction',
                 'waymo_post_expanded_authority_day_fraction',
                 'cruise_2022_23_paid_authority_window_day_fraction',
                 'cruise_2023_expanded_authority_window_day_fraction',
                 'cruise_post_2023_suspension_day_fraction']


def summarize_periods(monthly, allocation):
    rows = []
    for (zid, year), g in monthly.groupby(['superzone_id', 'year']):
        row = {'superzone_id': zid, 'year': year, 'scope': 'h1' if year == 2026 else 'calendar_year',
               'allocation': allocation, 'period_start': g.date.min(), 'period_end': g.date.max(),
               'period_months': len(g), 'period_days': int(g.days.sum())}
        for col in SUM_FEATURES:
            row[col+'_sum_available_months'] = g[col].sum(min_count=1)
            row[col+'_available_months'] = int(g[col].notna().sum())
        for col in MEAN_FEATURES:
            valid = g[col].notna()
            row[col+'_mean_available_days'] = np.average(g.loc[valid, col], weights=g.loc[valid, 'days']) if valid.any() else np.nan
            row[col+'_available_days'] = int(g.loc[valid, 'days'].sum())
        rows.append(row)
    d = pd.DataFrame(rows)
    d[d.year.lt(2026)].to_csv(OUT/f'zone_year_covariates_{allocation}.csv', index=False)
    d[d.year.eq(2026)].to_csv(OUT/f'zone_2026_h1_covariates_{allocation}.csv', index=False)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    zones = sorted(pd.read_csv(ROOT.parent/'results/panel.csv').superzone_id.unique())
    assert len(zones) == 65
    mileage = activity(zones)
    flow = traffic(zones)
    authority = calendar()
    trips = pd.read_csv(OUT/'cpuc_zone_month_trip_activity.csv')
    ca = pd.read_csv(OUT/'cpuc_california_monthly_trips.csv')
    assert not ca.duplicated(['operator', 'date']).any()
    assert not trips.duplicated(['operator', 'allocation', 'superzone_id', 'date']).any()
    estimates = recent_trip_estimates(mileage, trips, ca)
    for allocation in ['centerline', 'area']:
        d = flow.merge(authority, on='date', validate='many_to_one')
        d['year'] = d.date.str[:4].astype(int)
        d = d.merge(mileage[mileage.allocation.eq(allocation)], on=['superzone_id', 'date'], how='left', validate='one_to_one')
        d['allocation'] = allocation
        d.waymo_activity_status = d.waymo_activity_status.fillna('no_resolved_spatial_interval')
        recent = estimates[estimates.allocation.eq(allocation)].drop(columns='allocation')
        d = d.merge(recent, on=['superzone_id', 'date'], how='left', validate='one_to_one')
        d.recent_trip_status = d.recent_trip_status.fillna('not_estimated_outside_redacted_2025_2026_window')
        for op in ['Waymo', 'Cruise']:
            prefix = op.lower()
            q = trips[trips.allocation.eq(allocation) & trips.operator.eq(op)]
            cols = {'trip_starts_allocated': prefix+'_reported_trip_starts_allocated',
                    'trip_ends_allocated': prefix+'_reported_trip_ends_allocated',
                    'count_status': prefix+'_trip_count_status', 'mode': prefix+'_trip_reporting_mode',
                    'reported_tracts_overlapping_zone': prefix+'_reported_tracts_overlapping_zone',
                    'tract_vintage': prefix+'_trip_tract_vintage'}
            d = d.merge(q[['superzone_id', 'date']+list(cols)].rename(columns=cols), on=['superzone_id', 'date'], how='left', validate='one_to_one')
            d[prefix+'_trip_count_status'] = d[prefix+'_trip_count_status'].fillna('no_sf_tract_count_records')
            c = ca[ca.operator.eq(op)][['date', 'total_trips_ca']].rename(columns={'total_trips_ca': prefix+'_ca_total_trips'})
            d = d.merge(c, on='date', how='left', validate='many_to_one')
        d = d.sort_values(['superzone_id', 'date'])
        assert len(d) == 65*66 and not d.duplicated(['superzone_id', 'date']).any()
        d.to_csv(OUT/f'zone_month_covariates_{allocation}.csv', index=False)
        summarize_periods(d, allocation)
    inputs = ['outputs/av_mileage_candidates/waymo_cumulative_audit_county_adjusted.csv',
              'outputs/s2_to_superzone_weights.csv', 'outputs/service_activity/cpuc_zone_month_trip_activity.csv',
              'outputs/service_activity/cpuc_california_monthly_trips.csv', 'outputs/sfcta_zone_month_vmt_proxy.csv',
              'outputs/sfcta_zone_road_coverage.csv', 'outputs/extension_2026_h1/segment_month_volume_audit.csv',
              'outputs/extension_2026_h1/sfcta_expansion_audit.csv', 'outputs/sfcta_segment_to_zone.csv',
              'outputs/human_mileage_candidates/validation.json', 'raw/sfcta/citywide_vmt.json',
              'inputs/service_authority_events.json']
    validation = {'status': 'completed_retrospective_estimated_covariate_handoff',
                  'zones': len(zones), 'monthly_period': ['2021-01', '2026-06'], 'months': len(DATES),
                  'rows_per_monthly_allocation': 65*66, 'rows_per_2021_2025_annual_allocation': 65*5,
                  'rows_per_2026_h1_allocation': 65, 'spatial_allocations': ['centerline', 'area'],
                  'waymo_activity_months': sorted(mileage.date.unique()),
                  'recent_estimated_trip_months': sorted(estimates.date.unique()),
                  'trip_coverage': json.loads((OUT/'cpuc_validation.json').read_text())['coverage_by_operator'],
                  'no_crash_outcomes_used': True,
                  'not_obtained': ['historical zone-by-date authorized service polygons',
                                   'observed 2025-2026 SF tract trip counts',
                                   'Uber/Lyft/all-operator ride requests or unmet demand',
                                   'comparable Waymo spatial mileage increments before August 2024'],
                  'forecast_caveat': 'Retrospective: cumulative reconciliation and county conversion use later releases; month splits and reports are not available in real time. Re-estimate with release-aware inputs for prospective tests.',
                  'input_sha256': {p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in inputs}}
    (OUT/'validation.json').write_text(json.dumps(validation, indent=2)+'\n')
    print(json.dumps({k: v for k, v in validation.items() if k not in ['input_sha256', 'trip_coverage']}, indent=2))


if __name__ == '__main__':
    main()
