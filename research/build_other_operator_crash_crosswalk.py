"""Join public NHTSA/TIMS reports; preserve unknown police and service scope."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'outputs/other_operators_2026'


def main():
    raw=pd.read_csv(ROOT/'raw/nhtsa/ads_20261029.csv')
    assert not raw.duplicated(['Report ID','Report Version']).any()
    latest=raw.sort_values('Report Version').drop_duplicates('Report ID',keep='last')
    dates=pd.to_datetime(latest['Incident Date'],format='%b-%Y',errors='coerce')
    sf=latest[dates.between('2026-01-01','2026-06-30')&latest.State.str.strip().eq('CA')&latest.City.str.strip().str.casefold().eq('san francisco')&~latest['Reporting Entity'].str.contains('Waymo',case=False)].copy()
    cols=['Report ID','Report Version','Same Incident ID','Reporting Entity','Operating Entity','Incident Date','Highest Injury Severity Alleged','Roadway Type','Driver / Operator Type','Data Availability - Police Rpt','Investigating Agency']
    sf=sf[cols]
    source=json.loads((ROOT/'raw/dmv/tims_crashes_2026_h1.json').read_text())
    assert 'error' not in source and not source.get('exceededTransferLimit',False)
    tims=pd.DataFrame([r['attributes'] for r in source['features']])
    assert not tims.duplicated(['REPORT_ID','REPORT_VERSION']).any()
    tims=tims.sort_values('REPORT_VERSION').drop_duplicates('REPORT_ID',keep='last')
    fields=['REPORT_ID','REPORT_VERSION','INCIDENT_ID','INCIDENT_YEAR','INCIDENT_MONTH','LATITUDE','LONGITUDE','SEVERITY','PERMIT_TYPE','DATA_AVAILABILITY','INVESTIGATING_AGENCY']
    d=sf.merge(tims[fields],left_on='Report ID',right_on='REPORT_ID',how='left',validate='one_to_one',indicator=True)
    assert d._merge.eq('both').all()
    d['same_report_version']=d['Report Version'].eq(d.REPORT_VERSION)
    assert d.same_report_version.all()
    d['incident_key']=d['Same Incident ID'].fillna(d['Report ID'])
    d['duplicate_incident']=d.duplicated(['Reporting Entity','incident_key'])
    zones=gpd.read_file(ROOT.parent/'results/zones.geojson').to_crs(4326)
    metric=zones.to_crs(26910)
    records=[]
    for _,r in d.iterrows():
        if pd.isna(r.LATITUDE) or pd.isna(r.LONGITUDE):
            records.append({'superzone_id':np.nan,'point_zone_candidates':'','zones_within_20m':'','location_status':'missing'});continue
        p=Point(r.LONGITUDE,r.LATITUDE)
        candidates=sorted(zones.loc[zones.geometry.covers(p),'superzone_id'].astype(int))
        mp=gpd.GeoSeries([p],crs=4326).to_crs(26910).iloc[0]
        near=sorted(metric.loc[metric.geometry.intersects(mp.buffer(20)),'superzone_id'].astype(int))
        records.append({'superzone_id':candidates[0] if len(candidates)==1 else np.nan,'point_zone_candidates':';'.join(map(str,candidates)),'zones_within_20m':';'.join(map(str,near)),'location_status':'unique_point_zone' if len(candidates)==1 else 'ambiguous_or_outside'})
    d=pd.concat([d.reset_index(drop=True),pd.DataFrame(records)],axis=1)
    injury=['Minor W/O Hospitalization','Minor With Hospitalization','Moderate W/O Hospitalization','Moderate With Hospitalization','Serious W/O Hospitalization','Serious With Hospitalization','Fatality']
    d['injury_status']=np.where(d['Highest Injury Severity Alleged'].isin(injury),'reported_injury',np.where(d['Highest Injury Severity Alleged'].eq('Property Damage. No Injured Reported'),'reported_no_injury','unknown'))
    d['police_report_status']='not_established' # Blank SGO checkbox is not a verified negative.
    d['passenger_pilot_scope']='not_established'
    d['date_precision_used']='month; do not interpret TIMS day 01 as an exact date'
    d['coordinate_source']='public DMV-linked TIMS dashboard; pre-Apr28 locations supplemented from DMV reports'
    d.to_csv(OUT/'zoox_sf_h1_crash_crosswalk.csv',index=False)
    # Counts are separate diagnostic outcomes, not matched to the pilot denominator.
    unique=d[~d.duplicate_incident]
    counts=[]
    for zone in sorted(zones.superzone_id.astype(int)):
        g=unique[unique.superzone_id.eq(zone)]
        counts.append({'superzone_id':zone,'reported_crashes_assigned':len(g),'reported_injury_assigned':int(g.injury_status.eq('reported_injury').sum()),'unknown_severity_assigned':int(g.injury_status.eq('unknown').sum()),'outcome_scope':'all ADS reports; passenger-pilot operation not established'})
    pd.DataFrame(counts).to_csv(OUT/'zoox_sf_h1_zone_crash_diagnostics.csv',index=False)
    summary={'reports':len(d),'unique_incidents':len(unique),'matched_tims_reports':int(d._merge.eq('both').sum()),'coordinate_records':int(d.LATITUDE.notna().sum()),'unique_point_zone_records':int(d.superzone_id.notna().sum()),'injury_status_counts':d.injury_status.value_counts().to_dict(),'injury_report_ids':d.loc[d.injury_status.eq('reported_injury'),'Report ID'].tolist(),'injury_point_zones':d.loc[d.injury_status.eq('reported_injury'),'superzone_id'].tolist(),'police_report_and_pilot_scope':'not established; no matched injury-rate calculation','location_sensitivity':'20m buffer is an assumption, not a measured error bound','source_note':'NHTSA city filter identifies reports, not complete surveillance of every operator'}
    (OUT/'crash_crosswalk_validation.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2))

if __name__=='__main__':main()
