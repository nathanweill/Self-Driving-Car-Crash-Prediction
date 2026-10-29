"""Extract public passenger-program trip counts and allocate by tract vintage.

Counts remain separate from redactions. Zone allocation is an assumption; sparse
tract lists do not establish that an unlisted zone had no service.
"""
import hashlib
import io
import json
from pathlib import Path
import re
import zipfile
import geopandas as gpd
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'outputs/service_activity'


def archive_month_files(z,prefix=''):
    for name in z.namelist():
        if name.lower().endswith('.zip'):
            with zipfile.ZipFile(io.BytesIO(z.read(name))) as nested:
                yield from archive_month_files(nested,prefix+name+'::')
        elif name.lower().endswith('.csv') and 'month' in name.lower():
            yield prefix+name,z.read(name)


def numeric(values):
    return pd.to_numeric(values.astype('string').str.strip().str.replace(',','',regex=False),errors='coerce')


def tract_weights():
    zones=gpd.read_file(ROOT.parent/'results/zones.geojson').to_crs(26910)
    streets=gpd.read_file(ROOT/'raw/sf/streets.geojson').to_crs(26910)
    layers=['STREETS','PARKS','PARKS_NPS_PRESIDIO','PARKS_NPS_FTMASON','PRIVATE','STREETS_TI','STREETS_YBI','STREETS_HUNTERSP']
    streets=streets[streets.active.eq(True)&streets.layer.isin(layers)]
    def roads(poly):
        near=streets.iloc[streets.sindex.query(poly,predicate='intersects')]
        return near.geometry.intersection(poly).union_all().length if len(near) else 0.
    frames=[];vintage_ids={}
    for year,name,key in [(2010,'census_tracts_2010_verified.geojson','geoid10'),(2020,'census_tracts_2020.geojson','geoid')]:
        tr=gpd.read_file(ROOT/'raw/sf'/name).to_crs(26910).rename(columns={key:'tract_geoid'})
        vintage_ids[year]=set(tr.tract_geoid)
        tr['tract_area_m2']=tr.area
        tr['tract_road_m']=tr.geometry.map(roads)
        over=gpd.overlay(tr[['tract_geoid','tract_area_m2','tract_road_m','geometry']],zones[['superzone_id','geometry']],how='intersection',keep_geom_type=True)
        over['area_weight']=over.area/over.tract_area_m2
        over['overlap_road_m']=over.geometry.map(roads)
        over['centerline_weight']=over.overlap_road_m/over.tract_road_m.replace(0,np.nan)
        over['centerline_fallback_to_area']=over.centerline_weight.isna()
        over.centerline_weight=over.centerline_weight.fillna(over.area_weight)
        sums=over.groupby('tract_geoid').centerline_weight.sum()
        over['road_boundary_normalization']=over.tract_geoid.map(sums).clip(lower=1)
        over.centerline_weight/=over.road_boundary_normalization
        over['tract_vintage']=year
        frames.append(pd.DataFrame(over.drop(columns='geometry')))
    cross=pd.concat(frames,ignore_index=True)
    cross.to_csv(OUT/'tract_to_zone_weights.csv',index=False)
    return cross,vintage_ids,sorted(zones.superzone_id.astype(int))


def select_vintage(ids,reference):
    missing={v:len(set(ids)-known) for v,known in reference.items()}
    ranked=sorted(missing,key=lambda v:(missing[v],-v))
    chosen=ranked[0]
    tied=missing[ranked[0]]==missing[ranked[1]]
    return chosen,'ambiguous_prefer_2020' if tied else 'identified_by_valid_tract_codes',missing


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    cross,reference,zones=tract_weights()
    tract=[];months=[];audit=[]
    for folder in ['cpuc_historical','cpuc_activity','cpuc']:
        for archive in sorted((ROOT/'raw'/folder).glob('*.zip')):
            with zipfile.ZipFile(archive) as z:
                for name,blob in archive_month_files(z):
                    operator='Cruise' if 'cruise' in name.lower() else 'Waymo'
                    mode='driverless_deployment' if 'driverless' in name.lower() else 'drivered_deployment' if 'drivered' in name.lower() else 'deployment_mode_unspecified'
                    d=pd.read_csv(io.BytesIO(blob),dtype=str).dropna(how='all');d.columns=d.columns.str.strip()
                    if not {'Year','Month'}<=set(d):continue
                    y,m=numeric(d.Year),numeric(d.Month)
                    valid=y.between(2021,2026)&m.between(1,12)&y.mod(1).eq(0)&m.mod(1).eq(0)
                    dropped=int((~valid).sum());d=d[valid].copy()
                    d['date']=y[valid].astype(int).astype(str)+'-'+m[valid].astype(int).astype(str).str.zfill(2)
                    info={'archive':str(archive.relative_to(ROOT/'raw')),'member':name,'member_sha256':hashlib.sha256(blob).hexdigest(),'operator':operator,'mode':mode,'rows_kept':len(d),'rows_without_valid_period':dropped}
                    if 'Tract' in d and {'TripsStart','TripsEnd'}<=set(d):
                        d['tract_geoid']=d.Tract.str.strip().str.replace(r'\.0$','',regex=True).str.zfill(11)
                        d=d[d.tract_geoid.str.startswith('06075',na=False)].copy()
                        info['sf_rows']=len(d)
                        for col in ['TripsStart','TripsEnd']:
                            d[col+'_numeric']=numeric(d[col])
                            d[col+'_status']=np.where(d[col+'_numeric'].notna(),'numeric',np.where(d[col].str.casefold().eq('redacted'),'redacted','blank_or_unrecognized'))
                        info['sf_start_numeric_rows']=int(d.TripsStart_numeric.notna().sum())
                        for date,g in d.groupby('date'):
                            vintage,status,missing=select_vintage(g.tract_geoid,reference)
                            g=g.copy();g['tract_vintage']=vintage;g['vintage_status']=status
                            g['unmatched_tract_code']=~g.tract_geoid.isin(reference[vintage])
                            g['operator']=operator;g['mode']=mode;g['source_archive']=info['archive'];g['source_member']=name
                            tract.append(g[['operator','mode','date','tract_geoid','tract_vintage','vintage_status','unmatched_tract_code','TripsStart','TripsEnd','TripsStart_numeric','TripsEnd_numeric','TripsStart_status','TripsEnd_status','source_archive','source_member']])
                    elif 'TotalTrips' in d:
                        for _,r in d.iterrows():
                            months.append({'operator':operator,'mode':mode,'date':r.date,'total_trips_ca':numeric(pd.Series([r.TotalTrips])).iloc[0],'total_trips_raw':r.TotalTrips,'source_archive':info['archive'],'source_member':name})
                    else:continue
                    audit.append(info)
    raw=pd.concat(tract,ignore_index=True)
    assert not raw.duplicated(['operator','mode','date','tract_geoid']).any()
    raw.to_csv(OUT/'cpuc_sf_tract_month_records.csv.gz',index=False,compression={'method':'gzip','mtime':0})
    pd.DataFrame(months).to_csv(OUT/'cpuc_california_monthly_trips.csv',index=False)
    (OUT/'cpuc_member_audit.json').write_text(json.dumps(audit,indent=2)+'\n')
    allocated=[];coverage=[]
    for (op,mode,date),g in raw.groupby(['operator','mode','date']):
        assert g.tract_vintage.nunique()==1
        vintage=int(g.tract_vintage.iloc[0]);source_complete=g[['TripsStart_numeric','TripsEnd_numeric']].notna().all().all()
        h=g.merge(cross[cross.tract_vintage.eq(vintage)],on=['tract_geoid','tract_vintage'],how='left')
        for allocation in ['centerline','area']:
            h['starts_assigned']=h.TripsStart_numeric*h[allocation+'_weight']
            h['ends_assigned']=h.TripsEnd_numeric*h[allocation+'_weight']
            grouped=h.groupby('superzone_id')[['starts_assigned','ends_assigned']].sum(min_count=1).reindex(zones)
            if source_complete:grouped=grouped.fillna(0)
            # Source support is a coverage diagnostic, never proof of inactivity.
            support=h[h[allocation+'_weight'].notna()].groupby('superzone_id').tract_geoid.nunique().reindex(zones,fill_value=0)
            for zid,r in grouped.iterrows():
                allocated.append({'operator':op,'mode':mode,'date':date,'superzone_id':zid,'allocation':allocation,'trip_starts_allocated':r.starts_assigned,'trip_ends_allocated':r.ends_assigned,'reported_tracts_overlapping_zone':support.loc[zid],'tract_vintage':vintage,'vintage_status':g.vintage_status.iloc[0],'count_status':'reported_counts_spatially_allocated' if source_complete else 'redacted_or_missing_counts','meaning_of_zero':'no positive trips allocated from reported tracts; not proof of no service'})
            coverage.append({'operator':op,'mode':mode,'date':date,'allocation':allocation,'tract_vintage':vintage,'vintage_status':g.vintage_status.iloc[0],'sf_reported_tract_rows':len(g),'unmatched_tract_rows':int(g.unmatched_tract_code.sum()),'numeric_start_rows':int(g.TripsStart_numeric.notna().sum()),'sf_trip_starts_sum':g.TripsStart_numeric.sum(min_count=1),'sf_trip_ends_sum':g.TripsEnd_numeric.sum(min_count=1),'zone_starts_sum':grouped.starts_assigned.sum(min_count=1),'zone_ends_sum':grouped.ends_assigned.sum(min_count=1),'all_reported_counts_numeric':bool(source_complete)})
    out=pd.DataFrame(allocated);out.to_csv(OUT/'cpuc_zone_month_trip_activity.csv',index=False)
    cov=pd.DataFrame(coverage);cov.to_csv(OUT/'cpuc_monthly_coverage.csv',index=False)
    summary={'zone_month_rows':len(out),'coverage_by_operator':{},'unmatched_sf_tract_rows':int(raw.unmatched_tract_code.sum()),'ambiguous_vintage_rows':int(raw.vintage_status.eq('ambiguous_prefer_2020').sum()),'notes':['Counts are fulfilled passenger activity, not requests or unmet demand.','Sparse tract lists and redactions are not evidence of inactive zones.','Tract-to-zone allocation uses current surface roads or polygon area as sensitivity.']}
    for op,g in cov[cov.allocation.eq('centerline')].groupby('operator'):
        good=g[g.all_reported_counts_numeric]
        summary['coverage_by_operator'][op]={'numeric_months':sorted(good.date.unique()),'redacted_or_missing_months':sorted(g.loc[~g.all_reported_counts_numeric,'date'].unique())}
    (OUT/'cpuc_validation.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))

if __name__=='__main__':main()
