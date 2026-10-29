"""Complete, explicitly estimated human-mileage candidates for all 65 x 5 rows.

No fitting to crash outcomes. Outputs are alternative exposure inputs, not new
observations. City totals follow the published baseline panel (million miles).
"""
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'outputs/human_mileage_candidates'


def expand_network(frame, alpha, shrinkage_m):
    """Expand unobserved streets with shrunken local VMT per covered road-metre.

    alpha scales traffic density on missing streets relative to covered streets.
    A zone with no source observations uses the pooled city density, not zero.
    """
    d = frame.copy()
    d['covered_m'] = d.surface_centerline_within_20m_cmp_m
    d['uncovered_m'] = (d.official_surface_centerline_m - d.covered_m).clip(lower=0)
    d['source_missing'] = d.partial_network_annual_vmt_proxy.isna()
    d['observed_component_miles'] = d.partial_network_annual_vmt_proxy.fillna(0)
    observed = ~d.source_missing & d.covered_m.gt(0)
    pooled = d.loc[observed, 'observed_component_miles'].sum() / d.loc[observed, 'covered_m'].sum()
    local = d.observed_component_miles.div(d.covered_m.replace(0, np.nan)).fillna(pooled)
    weight = d.covered_m / (d.covered_m + shrinkage_m)
    weight = weight.where(observed, 0)
    d['pooled_vmt_per_covered_metre'] = pooled
    d['local_density_weight'] = weight
    d['imputation_density_vmt_per_metre'] = alpha * (weight * local + (1-weight) * pooled)
    # If an otherwise covered zone lacks a year of data, impute its entire network.
    d['length_to_impute_m'] = d.uncovered_m.where(~d.source_missing, d.official_surface_centerline_m)
    d['imputed_component_miles'] = d.length_to_impute_m * d.imputation_density_vmt_per_metre
    d['raw_full_zone_miles'] = d.observed_component_miles + d.imputed_component_miles
    d['imputed_share_before_calibration'] = d.imputed_component_miles / d.raw_full_zone_miles
    return d


def calibrate(d, total_million):
    d = d.copy()
    if d.raw_full_zone_miles.isna().any() or not d.raw_full_zone_miles.gt(0).all():
        raise ValueError('Every zone requires a positive finite raw estimate')
    d['zone_share'] = d.raw_full_zone_miles / d.raw_full_zone_miles.sum()
    d['citywide_anchor_million_miles'] = total_million
    d['calibration_factor'] = total_million * 1e6 / d.raw_full_zone_miles.sum()
    d['human_mileage_million_miles'] = d.zone_share * total_million
    d['human_mileage_miles'] = d.human_mileage_million_miles * 1e6
    return d


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    panel = pd.read_csv(ROOT.parent/'results/panel.csv')
    zones = sorted(panel.superzone_id.unique())
    assert len(zones) == 65 and not panel.duplicated(['superzone_id','year']).any()
    assert panel.groupby('year').N_H.nunique().eq(1).all()
    anchors = panel.groupby('year').N_H.first()
    source = pd.read_csv(ROOT/'outputs/sfcta_zone_year_vmt_proxy.csv')
    coverage = source.drop_duplicates('superzone_id')
    shrinkage_m = float(coverage.loc[coverage.surface_centerline_within_20m_cmp_m.gt(0), 'surface_centerline_within_20m_cmp_m'].median())
    all_rows, diagnostics = [], []
    for alpha, name in [(0.5,'sfcta_expanded'), (0.25,'sfcta_expanded_low'), (1.0,'sfcta_expanded_equal')]:
        frames = []
        for year,total in anchors.items():
            d = source[source.calendar_year.eq(year)].copy().rename(columns={'calendar_year':'year'})
            assert sorted(d.superzone_id) == zones
            d = calibrate(expand_network(d, alpha, shrinkage_m), total)
            d['method'] = name
            d['missing_road_density_multiplier'] = alpha
            d['imputation_flag'] = np.where(d.source_missing, 'whole_zone_pooled_density', 'uncovered_roads_shrunken_local_density')
            frames.append(d)
        diagnostic = pd.concat(frames,ignore_index=True)
        diagnostic.to_csv(OUT/f'{name}_diagnostics.csv', index=False)
        diagnostics.append(diagnostic)
        all_rows.append(diagnostic)

    hpms = pd.read_csv(ROOT/'outputs/waymo_human_zone_snapshot_exposure.csv')
    for allocation, name in [('centerline','hpms_2022_static'), ('area','hpms_2022_static_area')]:
        base = hpms[hpms.snapshot.eq(202606) & hpms.allocation.eq(allocation)].copy()
        assert len(base)==65 and sorted(base.superzone_id)==zones
        frames = []
        for year,total in anchors.items():
            d = base[['superzone_id','human_vmt_2022_benchmark_allocated']].rename(columns={'human_vmt_2022_benchmark_allocated':'raw_full_zone_miles'})
            d = calibrate(d, total)
            d['year'] = year
            d['method'] = name
            d['imputation_flag'] = '2022_benchmark_spatial_share_fixed_across_years'
            d['benchmark_year'] = 2022
            d['source_snapshot'] = 202606
            d['cell_allocation'] = allocation
            frames.append(d)
        diagnostic = pd.concat(frames,ignore_index=True)
        diagnostic.to_csv(OUT/f'{name}_diagnostics.csv',index=False)
        all_rows.append(diagnostic)

    columns = ['superzone_id','year','method','human_mileage_miles','human_mileage_million_miles','zone_share','citywide_anchor_million_miles','imputation_flag']
    combined = pd.concat([d[columns] for d in all_rows],ignore_index=True).sort_values(['method','year','superzone_id'])
    combined['data_status'] = 'modeled_full_zone_candidate'
    combined['city_total_allocation_assumption'] = 'all_paper_citywide_miles_allocated_to_65_study_zones'
    combined.to_csv(OUT/'human_mileage_all_candidates.csv',index=False)
    for method,d in combined.groupby('method'):
        d.to_csv(OUT/f'{method}.csv',index=False)
    wide = combined.pivot(index=['superzone_id','year'],columns='method',values='human_mileage_million_miles').reset_index()
    wide.columns.name = None
    wide.to_csv(OUT/'human_mileage_comparison_million_miles.csv',index=False)
    # Joinable keys and candidate columns only: never overwrite the baseline N_H.
    checks = []
    for (method,year),d in combined.groupby(['method','year']):
        assert len(d)==65 and d.human_mileage_miles.gt(0).all()
        assert np.isfinite(d.human_mileage_miles).all()
        error = float(d.human_mileage_million_miles.sum()-anchors.loc[year])
        assert abs(error) < 1e-8
        checks.append({'method':method,'year':int(year),'zones':len(d),'sum_million_miles':float(d.human_mileage_million_miles.sum()),'anchor_error_million_miles':error})
    comparison=[]
    for year,g in wide.groupby('year'):
        a,b=g.sfcta_expanded,g.hpms_2022_static
        comparison.append({'year':int(year),'pearson_zone_correlation':float(a.corr(b)),
                           'total_variation_of_zone_shares':float(((a/a.sum())-(b/b.sum())).abs().sum()/2)})
    input_paths=['results/panel.csv','research/outputs/sfcta_zone_year_vmt_proxy.csv','research/outputs/waymo_human_zone_snapshot_exposure.csv']
    summary={'created_date':'2026-10-29','main_candidates':['sfcta_expanded','hpms_2022_static'],
             'sensitivity_candidates':['sfcta_expanded_low','sfcta_expanded_equal','hpms_2022_static_area'],
             'rows_per_candidate':325,'zones_per_year':65,'years':[int(y) for y in anchors.index],
             'shrinkage_length_m':shrinkage_m,'default_missing_road_density_multiplier':0.5,
             'input_sha256':{p:hashlib.sha256((ROOT.parent/p).read_bytes()).hexdigest() for p in input_paths},
             'conservation_checks':checks,'main_candidate_comparison':comparison,
             'status':'Human mileage acquisition/processing deliverable complete for candidate-model testing; estimates are not direct measurements.'}
    (OUT/'validation.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps({k:v for k,v in summary.items() if k not in ['conservation_checks','input_sha256']},indent=2))


if __name__ == '__main__': main()
