"""Audited location refinement; preserve original rows and conflicting sources.

No probabilistic confidence claims: buffers, frontage proxies, and fractional
allocations are explicit sensitivity assumptions. Original geocoding is untouched.
"""
import json
import hashlib
from pathlib import Path
import re
import numpy as np
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point, MultiPoint
from shapely.ops import nearest_points, unary_union
from pyproj import Transformer
from geocode_waymo import Geocoder

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'outputs/geocoding_refined'
TO_METRIC=Transformer.from_crs(4326,26910,always_xy=True)
TO_WGS=Transformer.from_crs(26910,4326,always_xy=True)


def metric_point(lon,lat):
    return Point(*TO_METRIC.transform(float(lon),float(lat)))


def normalize_public_coordinate(lon,lat):
    """Only auto-correct a reversal when exactly the swapped pair fits SF bounds."""
    if pd.isna(lon) or pd.isna(lat):return None,'missing'
    if -122.55<float(lon)<-122.30 and 37.68<float(lat)<37.84:
        return metric_point(lon,lat),'as_published'
    if -122.55<float(lat)<-122.30 and 37.68<float(lon)<37.84:
        return metric_point(lat,lon),'latitude_longitude_swapped'
    return None,'outside_sf_coordinate_bounds'


def locate_extended(coder,query):
    """Use exact names/nodes first, then document small centerline gaps."""
    p,method,meta=coder.locate(query)
    if p is not None:return p,[p],float(meta['uncertainty_radius_m']),method,meta
    between=re.fullmatch(r'(.+) between (.+) and (.+)',query,flags=re.I)
    if between:
        a,_,ma=coder.intersect(between[1],between[2]);b,_,mb=coder.intersect(between[1],between[3])
        if a is not None and b is not None:
            center=MultiPoint([a,b]).centroid
            return center,[center],a.distance(b)/2+40,'specified_block_midpoint',{'street_a':coder.resolve(between[1])}
    pair=re.split(r'\s+(?:at|near|and)\s+|\s*&\s*',query,flags=re.I)
    if len(pair)!=2:return None,[],0,method,meta
    a,b=map(coder.resolve,pair)
    if not a or not b:return None,[],0,method,meta
    if method=='multiple_intersections':
        # Retain separate locations; never place a point midway between distant junctions.
        pts=[MultiPoint(coder.node_points[k]).centroid for k in sorted(coder.nodes[a]&coder.nodes[b])]
        return None,pts,100 if ' near ' in query.lower() else 20,'multiple_junction_candidates',{'street_a':a,'street_b':b}
    left,right=coder.groups[a].geometry.union_all(),coder.groups[b].geometry.union_all()
    gap=left.distance(right)
    tolerance=150 if ' near ' in query.lower() else 40
    if gap<=tolerance:
        q,r=nearest_points(left,right);p=MultiPoint([q,r]).centroid
        radius=max(100 if ' near ' in query.lower() else 40,gap/2+20)
        return p,[p],radius,'nearest_centerline_connector',{'street_a':a,'street_b':b,'centerline_gap_m':gap}
    return None,[],0,method,meta|{'centerline_gap_m':gap}


def zone_details(points,radius,zones):
    if not points:return [],{},None
    support=unary_union([p.buffer(radius) for p in points])
    hits=zones[zones.intersects(support)]
    areas={int(r.superzone_id):r.geometry.intersection(support).area for _,r in hits.iterrows()}
    areas={k:v for k,v in areas.items() if v>0}
    ids=sorted(areas)
    return ids,areas,support


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    baseline=pd.read_csv(ROOT/'outputs/waymo_sf_geocoding.csv')
    interpretations={r['report_id']:r for r in json.loads((ROOT/'inputs/waymo_geocode_interpretations.json').read_text())}
    streets=gpd.read_file(ROOT/'raw/sf/streets.geojson').to_crs(26910)
    coder=Geocoder(streets)
    zones=gpd.read_file(ROOT.parent/'results/zones.geojson').to_crs(26910)
    tims_rows=[]
    for name in ['tims_waymo_through_2026h1_page0.json','tims_waymo_through_2026h1_offset1000.json']:
        x=json.loads((ROOT/'raw/dmv'/name).read_text());tims_rows.extend([f['attributes'] for f in x['features']])
    tims=pd.DataFrame(tims_rows)
    count=json.loads((ROOT/'raw/dmv/tims_waymo_through_2026h1_count.json').read_text())['count']
    assert len(tims)==count and tims.ObjectId.nunique()==count
    assert not tims.duplicated(['REPORT_ID','REPORT_VERSION']).any()
    tims=tims.sort_values('REPORT_VERSION').drop_duplicates('REPORT_ID',keep='last').set_index('REPORT_ID')
    nhtsa=pd.read_csv(ROOT/'raw/nhtsa/ads_20261029.csv').sort_values('Report Version').drop_duplicates('Report ID',keep='last').set_index('Report ID')
    rows=[];weights=[];features=[];alternate=[]
    for _,r in baseline.iterrows():
        rid=r['SGO Report ID'];oldpoint=metric_point(r.longitude,r.latitude) if pd.notna(r.longitude) else None
        points=[oldpoint] if oldpoint is not None else []
        primary=oldpoint;radius=float(r.uncertainty_radius_m) if oldpoint is not None else 0
        method='original_'+str(r.geocode_method);meta={};query=r['Location Address / Description'];note='';scope=True
        if rid in interpretations:
            it=interpretations[rid];query=it['query'];note=it['rationale']
        if oldpoint is None:
            primary,points,radius,method,meta=locate_extended(coder,query)
            if rid in interpretations:
                kind=interpretations[rid]['kind']
                if points and kind.startswith('offstreet'):radius=max(radius,150);method='offstreet_frontage_proxy'
                if points and kind=='intersection_complex':radius=max(radius,100)
                if points and kind in ['street_alias','route_alias']:radius=max(radius,50)
                if points and kind=='unconfirmed_street_correction':radius=max(radius,150);method='inferred_street_correction'
        # NHTSA report identity confirms a mislabeled Atlanta record in Waymo CSV2.
        if rid in nhtsa.index:
            n=nhtsa.loc[rid]
            state=str(n.State).strip()
            if len(state)==2 and state.isalpha() and state!='CA' and pd.notna(n.City) and str(n.City).strip().lower()!='san francisco':
                scope=False;primary=None;points=[];radius=0;method='excluded_cross_source_city_conflict';note=f"NHTSA {rid} identifies {n.City}, {str(n.State).strip()}; original County/State retained"
        public=None;public_status='no_matched_report';distance=np.nan;conflict=False;version_ok=False;period_ok=False;public_raw_lon=np.nan;public_raw_lat=np.nan;tims_version=np.nan
        if rid in tims.index:
            t=tims.loc[rid];public_raw_lon=t.LONGITUDE;public_raw_lat=t.LATITUDE;tims_version=t.REPORT_VERSION
            public,public_status=normalize_public_coordinate(t.LONGITUDE,t.LATITUDE)
            version_ok=int(t.REPORT_VERSION)==int(r['SGO Report Version'])
            dt=pd.to_datetime(r['Incident Date'])
            period_ok=int(t.INCIDENT_YEAR)==dt.year and int(t.INCIDENT_MONTH)==dt.month
            if public is not None and points:distance=min(public.distance(p) for p in points)
            if public is not None and scope:
                conflict=bool(points and distance>max(100,radius+50))
                if not version_ok or not period_ok:conflict=True
                alternate.append({'source_csv_row':int(r.source_csv_row),'report_id':rid,'raw_longitude':public_raw_lon,'raw_latitude':public_raw_lat,'coordinate_action':public_status,'distance_to_description_candidate_m':distance,'conflict':conflict,'same_report_version':version_ok,'same_incident_month':period_ok})
                if not conflict:
                    primary=public;points=[public];radius=50;method='tims_public_coordinate'
                    if public_status=='latitude_longitude_swapped':method+='_axis_corrected'
        ids,areas,support=zone_details(points,radius,zones)
        point_hits=zones[zones.geometry.covers(primary)] if primary is not None else zones.iloc[0:0]
        point_zone=int(point_hits.iloc[0].superzone_id) if len(point_hits)==1 else None
        stable=bool(len(ids)==1 and support is not None and zones.loc[zones.superzone_id.eq(ids[0]),'geometry'].iloc[0].covers(support))
        lon,lat=TO_WGS.transform(primary.x,primary.y) if primary is not None else (np.nan,np.nan)
        pub_lon,pub_lat=TO_WGS.transform(public.x,public.y) if public is not None else (np.nan,np.nan)
        reason=''
        if not scope:reason='source_city_conflict_excluded_from_sf'
        elif not points:reason='no_supported_location; original reason='+str(r.geocode_method)
        elif primary is None:reason='multiple_junctions; use candidate-zone sensitivity'
        elif method=='inferred_street_correction':reason='street_name_correction_hypothesis_requires_confirmation'
        elif conflict:reason='public_coordinate_disagrees_with_description; retain_description_primary'
        elif not stable:reason='zone_boundary_sensitive'
        row=r.to_dict()
        for key in ['longitude','latitude','point_zone_id','zone_candidates','geocode_method','uncertainty_radius_m','zone_assignment_stable_within_assumed_radius']:
            row['original_'+key]=row.pop(key)
        row.update({'longitude':lon,'latitude':lat,'point_zone_id':point_zone,'zone_candidates':';'.join(map(str,ids)),'geocode_method':method,'uncertainty_radius_m':radius,'zone_assignment_stable_within_assumed_radius':stable,'sf_scope_candidate':scope,'interpreted_description':query,'interpretation_note':note,'interpretation_kind':interpretations.get(rid,{}).get('kind','none'),'candidate_point_count':len(points),'tims_report_version':tims_version,'tims_raw_longitude':public_raw_lon,'tims_raw_latitude':public_raw_lat,'tims_candidate_longitude':pub_lon,'tims_candidate_latitude':pub_lat,'tims_coordinate_status':public_status,'tims_same_report_version':version_ok,'tims_same_incident_month':period_ok,'public_description_distance_m':distance,'public_coordinate_conflict':conflict,'review_reason':reason,'centerline_gap_m':meta.get('centerline_gap_m',np.nan)})
        if primary is not None:
            row['shift_from_original_m']=primary.distance(oldpoint) if oldpoint is not None else np.nan
            row['point_zone_changed']=bool(pd.notna(r.point_zone_id) and point_zone!=int(r.point_zone_id))
            features.append({'type':'Feature','geometry':{'type':'Point','coordinates':[lon,lat]},'properties':{'source_csv_row':int(r.source_csv_row),'report_id':rid,'method':method,'superzone_id':point_zone,'review_reason':reason}})
        else:row['shift_from_original_m']=np.nan;row['point_zone_changed']=False
        rows.append(row)
        for scenario,rad in [('default',radius),('minimum_100m',max(radius,100))]:
            zone_ids,zone_areas,_=zone_details(points,rad,zones)
            for zid in zone_ids:
                weights.append({'source_csv_row':int(r.source_csv_row),'report_id':rid,'scenario':scenario,'radius_m':rad,'superzone_id':zid,'equal_candidate_weight':1/len(zone_ids),'buffer_area_weight':zone_areas[zid]/sum(zone_areas.values()),'interpretation':'sensitivity allocation, not location probability'})
    result=pd.DataFrame(rows)
    assert len(result)==len(baseline) and result.source_csv_row.is_unique
    result.to_csv(OUT/'waymo_sf_geocoding_refined.csv',index=False)
    result[result.original_longitude.isna()].to_csv(OUT/'original_48_resolution_audit.csv',index=False)
    result[result.review_reason.ne('')].to_csv(OUT/'review_queue.csv',index=False)
    result[result.sf_scope_candidate & result.candidate_point_count.eq(0)].to_csv(OUT/'unresolved_locations.csv',index=False)
    result[result.public_coordinate_conflict].to_csv(OUT/'public_coordinate_conflicts.csv',index=False)
    pd.DataFrame(alternate).to_csv(OUT/'tims_coordinate_comparison.csv',index=False)
    pd.DataFrame(weights).to_csv(OUT/'zone_allocation_sensitivities.csv',index=False)
    (OUT/'waymo_sf_geocoding_refined.geojson').write_text(json.dumps({'type':'FeatureCollection','features':features})+'\n')
    original_missing=result.original_longitude.isna()
    # Show the effect on Category 3 without silently replacing its delivered panel.
    dates=pd.to_datetime(result['Incident Date'],format='mixed')
    selected=result[dates.between('2026-01-01','2026-06-30') & result.sf_scope_candidate & result['Road Type'].eq('Surface Street') & result['Is Police-Reported'].eq(True) & result['Is Any-Injury-Reported'].eq(True) & result['Is NHTSA Reportable In-Transport'].eq(True)].drop_duplicates('SGO Report ID')
    zone_ids=sorted(zones.superzone_id.astype(int))
    impact=pd.DataFrame({'superzone_id':zone_ids}).set_index('superzone_id')
    for col,name in [('original_point_zone_id','original_point_count'),('point_zone_id','refined_point_count')]:
        impact[name]=selected.groupby(col).size().reindex(zone_ids,fill_value=0)
    impact['original_equal_candidate_count']=0.
    for value in selected.original_zone_candidates.dropna():
        ids=[int(x) for x in str(value).split(';')]
        if ids:impact.loc[ids,'original_equal_candidate_count']+=1/len(ids)
    weight_frame=pd.DataFrame(weights)
    chosen=weight_frame[weight_frame.scenario.eq('default')&weight_frame.source_csv_row.isin(selected.source_csv_row)]
    for col,name in [('equal_candidate_weight','refined_equal_candidate_count'),('buffer_area_weight','refined_buffer_area_count')]:
        impact[name]=chosen.groupby('superzone_id')[col].sum().reindex(zone_ids,fill_value=0)
    impact.to_csv(OUT/'h1_injury_allocation_comparison.csv')
    summary={'source_rows':len(result),'unique_report_ids':int(result['SGO Report ID'].nunique()),'original_coordinate_rows':int(result.original_longitude.notna().sum()),'refined_coordinate_rows':int(result.longitude.notna().sum()),'rows_with_point_zone':int(result.point_zone_id.notna().sum()),'rows_with_candidate_zones':int(result.zone_candidates.ne('').sum()),'original_48_now_with_point':int((original_missing&result.longitude.notna()).sum()),'original_48_multiple_candidates':int((original_missing&result.longitude.isna()&result.candidate_point_count.gt(0)).sum()),'original_48_excluded_city_conflict':int((original_missing&~result.sf_scope_candidate).sum()),'unresolved_in_scope':int((result.sf_scope_candidate&result.candidate_point_count.eq(0)).sum()),'public_coordinate_conflicts':int(result.public_coordinate_conflict.sum()),'public_axis_reversals':int(result.tims_coordinate_status.eq('latitude_longitude_swapped').sum()),'point_zones_changed':int(result.point_zone_changed.sum()),'h1_selected_injury_events':len(selected),'h1_selected_point_zones_changed':int(selected.point_zone_changed.sum()),'stable_within_assumed_default_support':int(result.zone_assignment_stable_within_assumed_radius.sum()),'methods':result.geocode_method.value_counts().to_dict(),'notes':['Original source rows and original candidate geocodes preserved.','Source-match does not guarantee coordinate accuracy; conflicts retain description-based primary.','No nearest-zone snapping; unresolved rows remain unassigned.','All buffer and frontage assumptions are sensitivity designs, not calibrated confidence regions.']}
    summary['input_sha256']={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in ['inputs/waymo_geocode_interpretations.json','outputs/waymo_sf_geocoding.csv','raw/sf/streets.geojson','raw/nhtsa/ads_20261029.csv']}
    (OUT/'validation.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2))

if __name__=='__main__':main()
