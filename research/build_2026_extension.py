"""Matched Jan–Jun 2026 Waymo/reference candidates; never an all-operator panel."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
import geopandas as gpd
from build_sfcta_exposure import deduplicate_daily_volumes
from build_human_mileage_candidates import expand_network, calibrate

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'outputs/extension_2026_h1'
MONTHS=[f'2026-{m:02}' for m in range(1,7)]


def crash_counts(events, zones, allocation):
    counts=pd.Series(0.,index=zones)
    for _,row in events.iterrows():
        candidates=([int(row.point_zone_id)] if pd.notna(row.point_zone_id) else []) if allocation=='point' else ([int(x) for x in str(row.zone_candidates).split(';')] if pd.notna(row.zone_candidates) else [])
        assert set(candidates)<=set(zones)
        if candidates:
            counts.loc[candidates]+=1/len(candidates)
    return counts


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    zones=sorted(pd.read_csv(ROOT.parent/'results/panel.csv').superzone_id.unique())
    daily=deduplicate_daily_volumes(pd.DataFrame(json.loads((ROOT/'raw/sfcta/monthly_volumes_2026_h1.json').read_text())))
    assert sorted(daily.date.unique())==MONTHS
    # Missing segment-months use that segment's mean over available H1 months.
    full=pd.MultiIndex.from_product([sorted(daily.cmp_segid.unique()),MONTHS],names=['cmp_segid','date'])
    traffic=daily.set_index(['cmp_segid','date'])[['imp_vol']].reindex(full).reset_index()
    traffic['volume_imputed']=traffic.imp_vol.isna()
    traffic.imp_vol=traffic.imp_vol.fillna(traffic.groupby('cmp_segid').imp_vol.transform('mean'))
    traffic['days']=pd.to_datetime(traffic.date).dt.days_in_month
    traffic.to_csv(OUT/'segment_month_volume_audit.csv',index=False)
    cross=pd.read_csv(ROOT/'outputs/sfcta_segment_to_zone.csv')
    segments=gpd.read_file(ROOT/'outputs/sfcta_segments.geojson').to_crs(26910)
    assert set(traffic.cmp_segid)<=set(segments.cmp_segid)
    joined=traffic.merge(cross[['cmp_segid','superzone_id','allocated_source_length_miles']],on='cmp_segid')
    joined['vmt']=joined.imp_vol*joined.days*joined.allocated_source_length_miles
    partial=joined.groupby('superzone_id').vmt.sum().reindex(zones)
    # Recompute coverage for the H1 observed network, rather than reuse 2021–25 coverage.
    corridor=segments[segments.cmp_segid.isin(traffic.cmp_segid)].geometry.union_all().buffer(20)
    streets=gpd.read_file(ROOT/'raw/sf/streets.geojson').to_crs(26910)
    streets=streets[streets.active.eq(True)&streets.layer.isin(['STREETS','PARKS','PARKS_NPS_PRESIDIO','PARKS_NPS_FTMASON','PRIVATE','STREETS_TI','STREETS_YBI','STREETS_HUNTERSP'])]
    geozones=gpd.read_file(ROOT.parent/'results/zones.geojson').to_crs(26910)
    coverage=[]
    for _,z in geozones.iterrows():
        geom=streets.iloc[streets.sindex.query(z.geometry,predicate='intersects')].geometry.intersection(z.geometry).union_all()
        coverage.append({'superzone_id':z.superzone_id,'official_surface_centerline_m':geom.length,'surface_centerline_within_20m_cmp_m':geom.intersection(corridor).length})
    frame=pd.DataFrame(coverage).set_index('superzone_id').reindex(zones)
    frame['partial_network_annual_vmt_proxy']=partial # Legacy helper field; values cover H1 only.
    city=pd.DataFrame(json.loads((ROOT/'raw/sfcta/citywide_vmt.json').read_text()))
    city=city[city.fac_typ.eq('Citywide')&city.date.isin(MONTHS)]
    assert city.groupby('date').metric.nunique().eq(1).all()
    city=city.drop_duplicates('date').copy()
    assert sorted(city.date)==MONTHS
    city['days']=pd.to_datetime(city.date).dt.days_in_month
    city['million_miles']=city.metric*city.days
    total=city.million_miles.sum()
    city.to_csv(OUT/'citywide_monthly_mileage.csv',index=False)
    k=json.loads((ROOT/'outputs/human_mileage_candidates/validation.json').read_text())['shrinkage_length_m']
    expanded=calibrate(expand_network(frame,.5,k),total)
    expanded.rename(columns={'partial_network_annual_vmt_proxy':'partial_network_h1_vmt_proxy'}).to_csv(OUT/'sfcta_expansion_audit.csv')
    hpms=pd.read_csv(ROOT/'outputs/human_mileage_candidates/hpms_2022_static.csv')
    hpms=hpms[hpms.year.eq(2025)].set_index('superzone_id').zone_share.reindex(zones)
    reference={'sfcta_expanded':expanded.zone_share,'hpms_static':hpms}
    cumulative=pd.read_csv(ROOT/'outputs/av_mileage_candidates/waymo_cumulative_audit_county_adjusted.csv',dtype={'s2_cell':str})
    pivot=cumulative.pivot(index='s2_cell',columns='snapshot',values='fitted_cumulative_miles')
    delta=pivot[202606]-pivot[202512]
    assert delta.ge(0).all() and delta.sum()>0
    delta.rename('h1_miles').to_csv(OUT/'waymo_cell_interval_miles.csv')
    weights=pd.read_csv(ROOT/'outputs/s2_to_superzone_weights.csv',dtype={'S2 Cell':str})
    allocated=weights.merge(delta.rename('miles'),left_on='S2 Cell',right_index=True,how='left')
    allocated['allocated_miles']=allocated.miles*allocated.centerline_weight
    spatial=allocated.groupby('superzone_id').allocated_miles.sum().reindex(zones,fill_value=0)
    waymo_total=float(delta.sum())
    events=pd.read_csv(ROOT/'outputs/waymo_sf_geocoding.csv')
    dates=pd.to_datetime(events['Incident Date'],format='%m/%d/%Y')
    events=events[dates.between('2026-01-01','2026-06-30')].copy()
    raw_count=len(events)
    # Multiple vehicle rows may describe a single SGO event. Reject conflicting event attributes.
    fields=['Incident Date','Road Type','Is NHTSA Reportable In-Transport','Is Police-Reported','Is Any-Injury-Reported','point_zone_id','zone_candidates']
    assert not events.groupby('SGO Report ID')[fields].nunique(dropna=False).gt(1).any().any()
    assert events[['Is NHTSA Reportable In-Transport','Is Police-Reported','Is Any-Injury-Reported']].notna().all().all()
    events['duplicate_event_row']=events.duplicated('SGO Report ID')
    events['selected_outcome']=events['Road Type'].eq('Surface Street')&events['Is NHTSA Reportable In-Transport'].eq(True)&events['Is Police-Reported'].eq(True)&events['Is Any-Injury-Reported'].eq(True)
    events.to_csv(OUT/'waymo_h1_event_audit.csv',index=False)
    unique=events.drop_duplicates('SGO Report ID')
    selected=unique[unique.selected_outcome]
    counts=pd.read_csv(ROOT/'outputs/sf_injury_zone_counts_2026_h1.csv').set_index('superzone_id').recorded_injury_crashes_in_unique_zone.reindex(zones)
    reference_events=pd.read_csv(ROOT/'outputs/sf_injury_2025_2026_geocoded_candidate.csv')
    reference_events=reference_events[reference_events.date.between('2026-01-01','2026-06-30')]
    assert not reference_events.case_id_pkey.duplicated().any()
    reference_events.to_csv(OUT/'reference_h1_event_audit.csv',index=False)
    reference_total=len(reference_events)
    frames=[]
    for method,share in reference.items():
        av_share=.99*spatial/spatial.sum()+.01*share
        for allocation in ['point','fractional_candidates']:
            d=pd.DataFrame({'superzone_id':zones,'n_reference_injury':counts.values,'n_waymo_police_injury':crash_counts(selected,zones,allocation).values,'reference_mileage_million_miles':(share*total).values,'waymo_ro_mileage_million_miles':(av_share*waymo_total/1e6).values})
            d['window_start']='2026-01-01';d['window_end']='2026-06-30';d['window_days']=181
            d['reference_method']=method;d['waymo_location_allocation']=allocation
            d['av_scope']='Waymo rider-only; testing and commercial combined'
            d['reference_scope']='city-street injury records; not confirmed human-only'
            d.to_csv(OUT/f'{method}_{allocation}.csv',index=False);frames.append(d)
    pd.concat(frames,ignore_index=True).to_csv(OUT/'all_candidates.csv',index=False)
    summary={'window_start':'2026-01-01','window_end':'2026-06-30','days':181,'zones':65,'variants':4,'reference_million_miles':float(total),'waymo_ro_million_miles':waymo_total/1e6,'waymo_miles_before_zone_normalization':float(spatial.sum()),'segment_months_imputed':int(traffic.volume_imputed.sum()),'waymo_source_rows':raw_count,'waymo_unique_sgo_ids':len(unique),'waymo_any_injury_events':int(unique['Is Any-Injury-Reported'].eq(True).sum()),'waymo_police_injury_intransport_events':len(selected),'waymo_selected_with_point_zone':int(selected.point_zone_id.notna().sum()),'reference_injury_cases':reference_total,'reference_injury_cases_assigned':int(counts.sum()),'reference_cases_unassigned':reference_total-int(counts.sum()),'status':'Matched-window Waymo/reference estimated-data handoff complete; all-operator DMV deployment coverage not obtained.'}
    (OUT/'validation.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2))

if __name__=='__main__':main()
