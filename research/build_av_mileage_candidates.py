"""Category 2: explicit estimated AV exposure, by operator, zone and year.

Preserves raw evidence. Waymo RO replaces (never adds to) Waymo DMV driverless
testing. All periods are calendar-based; 2025 June-15 cutoff is a separate scope.
No crash counts enter spatial allocation; inherited SGO shares do enter testing
city allocation. Estimates are retrospective inputs, not observed fleet traces.
"""
from pathlib import Path
import calendar
import hashlib
import io
import json
import re
import zipfile
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
OUT = ROOT/'outputs/av_mileage_candidates'
YEARS = range(2021, 2026)


def pava(values):
    """Equal-weight least-squares monotone fit, preserving adjustments for audit."""
    blocks=[]
    for v in np.asarray(values, dtype=float):
        if not np.isfinite(v) or v < 0: raise ValueError('Invalid cumulative mileage')
        blocks.append([v,1])
        while len(blocks)>1 and blocks[-2][0] > blocks[-1][0]:
            b=blocks.pop(); a=blocks.pop()
            blocks.append([(a[0]*a[1]+b[0]*b[1])/(a[1]+b[1]),a[1]+b[1]])
    return np.concatenate([np.repeat(v,n) for v,n in blocks])


def day_number(date):
    return pd.Timestamp(date).value / 86400e9


def snapshot_boundary(stamp):
    return (pd.Timestamp(f'{stamp[:4]}-{stamp[4:]}-01') + pd.offsets.MonthBegin(1))


def paper_anchors():
    # Pinned extract includes exact source lines/hash; no private Overleaf clone
    # is needed when another researcher reproduces this package.
    p=ROOT/'inputs/paper_commercial_mileage_anchors.csv'
    d=pd.read_csv(p)
    assert len(d)==5
    d.to_csv(OUT/'original_paper_anchors.csv',index=False)
    return d.set_index('year')


def cruise_monthly():
    rows=[]
    for p in sorted((ROOT/'raw/cpuc_historical').glob('*.zip')):
        with zipfile.ZipFile(p) as z:
            for name in z.namelist():
                if '/Cruise/' not in name or not name.endswith('.csv') or not re.search(r'AV_Month_Part',name): continue
                payload=z.read(name)
                d=pd.read_csv(io.BytesIO(payload),dtype=str)
                for _,r in d.iterrows():
                    vals=pd.to_numeric(pd.Series([r.get(f'TotalVMTPeriod{k}') for k in (1,2,3)],dtype='string').str.replace(',',''),errors='coerce')
                    rows.append({'year':int(r.Year),'month':int(r.Month),'miles':float(vals.sum()) if vals.notna().all() else np.nan,
                                 'archive':p.name,'member':name,'member_sha256':hashlib.sha256(payload).hexdigest(),
                                 'cpuc_value_status':'numeric_period1_plus2_plus3' if vals.notna().all() else 'blank_not_observed_zero'})
    d=pd.DataFrame(rows)
    assert not d.duplicated(['year','month']).any()
    d.to_csv(OUT/'cruise_public_monthly_evidence.csv',index=False)
    return d


def testing_monthly():
    raw=pd.read_csv(REPO/'data/mileage/dmv_testing_monthly.csv')
    raw=raw[raw.year.isin(YEARS)].copy()
    raw[raw.mfr.eq('WAYMO') & raw.kind.eq('driverless')].to_csv(OUT/'excluded_waymo_driverless_testing.csv',index=False)
    raw=raw[~(raw.mfr.eq('WAYMO') & raw.kind.eq('driverless'))]
    assert not raw.duplicated(['mfr','kind','year','month']).any()
    sgo=pd.read_csv(REPO/'data/mileage/sgo_ca_incidents.csv')
    sgo=sgo[sgo.year.isin(YEARS)].copy()
    assert sgo.onboard.dtype==bool and sgo.sf.dtype==bool
    sgo['kind']=np.where(sgo.onboard,'drivered','driverless')
    def share(op,kind,year):
        d=sgo[sgo.op.eq(op)&sgo.kind.eq(kind)]
        if op=='WAYMO': d=d[d.year.eq(year)]
        if not len(d) and kind=='driverless': d=sgo[sgo.op.eq(op)&sgo.kind.eq('drivered')]
        return (float(d.sf.mean()),len(d),'calendar_year_sgo' if op=='WAYMO' else 'pooled_2021_2025_sgo') if len(d) else (0.,0,'no_sgo_evidence_assumed_zero_sf')
    rows=[]
    for (op,kind),g in raw.groupby(['mfr','kind']):
        lookup=g.set_index(['year','month']).miles
        for year in YEARS:
            sf,n,method=share(op,kind,year)
            for month in range(1,13):
                key=(year,month)
                if key in lookup.index:
                    miles=float(lookup.loc[key]); status='source_month'
                elif year==2025 and month==12:
                    values=[float(lookup.get((2025,m),0)) for m in (9,10,11)]
                    miles=float(np.mean(values)); status='dec2025_estimated_mean_sep_nov'
                else:
                    miles=0.;status='no_source_row_assumed_zero'
                rows.append({'operator':op,'mode':kind,'year':year,'month':month,'statewide_miles':miles,
                             'sf_share':sf,'sgo_reports_for_share':n,'sf_share_method':method,
                             'sf_miles':miles*sf,'month_status':status})
    d=pd.DataFrame(rows)
    d.to_csv(OUT/'testing_operator_monthly_estimates.csv',index=False)
    return d


def waymo_curves(geography):
    latest=pd.read_csv(ROOT/'raw/waymo/202606_csv4.csv',dtype={'S2 Cell':str})
    grouping=['state_name','county_name','S2 Cell']
    assert latest.groupby(grouping)['Waymo RO Miles'].nunique().max()==1
    latest=latest.drop_duplicates(grouping)
    total=latest.groupby('S2 Cell')['Waymo RO Miles'].sum()
    sf=latest[latest.county_name.eq('San Francisco')].set_index('S2 Cell')['Waymo RO Miles']
    county_fraction=(sf/total).fillna(0)
    frames=[]
    for p in sorted((ROOT/'raw/waymo').glob('*_csv4.csv')):
        a=pd.read_csv(p,dtype={'S2 Cell':str}); old='Location' in a
        a=a[a['Location' if old else 'county_name'].eq('SAN_FRANCISCO' if old else 'San Francisco')]
        assert a.groupby('S2 Cell')['Waymo RO Miles'].nunique().max()==1
        a=a.drop_duplicates('S2 Cell').set_index('S2 Cell')['Waymo RO Miles']
        if old and geography=='county_adjusted':
            if county_fraction.reindex(a.index).isna().any(): raise ValueError('Missing county reconciliation fraction')
            a=a*county_fraction.reindex(a.index)
        frames.append(a.rename(p.stem[:6]))
    raw=pd.concat(frames,axis=1).sort_index()
    axis=np.array([day_number(snapshot_boundary(str(c))) for c in raw.columns])
    fitted=raw.copy();audit=[]
    for cell,row in raw.iterrows():
        valid=row.notna().values
        monotone=pava(row.values[valid])
        values=np.interp(axis,axis[valid],monotone,left=0,right=monotone[-1])
        fitted.loc[cell]=values
        for stamp,before,after,known in zip(raw.columns,row,values,valid):
            audit.append({'geography':geography,'s2_cell':cell,'snapshot':stamp,'reconciled_input_miles':before,
                          'fitted_cumulative_miles':after,'adjustment_miles':after-before if known else np.nan,
                          'status':'observed_reconciled' if known and abs(after-before)<1e-6 else 'monotone_adjusted' if known else 'missing_snapshot_interpolated_or_zero_before_first',
                          'legacy_county_fraction_proxy':float(county_fraction.get(cell,1))})
    pd.DataFrame(audit).to_csv(OUT/f'waymo_cumulative_audit_{geography}.csv',index=False)
    def at(date):
        t=day_number(date)
        return pd.Series([np.interp(t,axis,row.values) for _,row in fitted.iterrows()],index=fitted.index)
    return at


def normalize_weights(series):
    if not np.isfinite(series).all() or series.lt(-1e-7).any() or series.sum()<=0: raise ValueError('Invalid spatial weights')
    series=series.clip(lower=0) # only floating-point noise, not negative source increments
    return series/series.sum()


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    anchors=paper_anchors(); cruise=cruise_monthly(); testing=testing_monthly()
    curves={g:waymo_curves(g) for g in ['county_adjusted','legacy_labels']}
    weights=pd.read_csv(ROOT/'outputs/s2_to_superzone_weights.csv',dtype={'S2 Cell':str})
    humans=pd.read_csv(ROOT/'outputs/human_mileage_candidates/human_mileage_all_candidates.csv')
    zones=sorted(humans.superzone_id.unique()); assert len(zones)==65
    def human_shares(year,method):
        x=humans[humans.year.eq(year)&humans.method.eq(method)].set_index('superzone_id').zone_share.reindex(zones)
        return normalize_weights(x)
    spatial_audits=[]
    def waymo_shares(year,scope,style,geo,human_method):
        at=curves[geo]
        if style=='fixed' or year<=2023:
            cell=at('2024-08-01');label='backcast_first_202407_cumulative_footprint'
        elif year==2024:
            cell=at('2025-01-01')-at('2024-08-01');label='aug_dec2024_increment_used_for_full2024'
        else:
            cell=at('2025-06-16' if scope=='through_june15_2025' else '2026-01-01')-at('2025-01-01');label='fitted_2025_interval'
        if style=='fixed': label='first_202407_footprint_fixed_all_years'
        assert cell.min()>=-1e-6
        merged=weights.merge(cell.rename('miles'),left_on='S2 Cell',right_index=True,how='left')
        if merged.miles.isna().any(): raise ValueError('S2 crosswalk missing cell values')
        allocated=(merged.miles*merged.centerline_weight).groupby(merged.superzone_id).sum().reindex(zones,fill_value=0)
        retained=allocated.sum()/cell.sum()
        # 1% human-share regularization avoids accidental structural-zero zones
        # from missing snapshot coverage. It is an explicit sensitivity assumption.
        shares=.99*normalize_weights(allocated)+.01*human_shares(year,human_method)
        spatial_audits.append({'year':year,'scope':scope,'style':style,'geography':geo,'human_method':human_method,
                               'basis':label,'cell_sum_miles':cell.sum(),'retained_crosswalk_fraction':retained,
                               'human_share_regularization':.01})
        return normalize_weights(shares),label

    source_rows=[]
    for scope in ['calendar_year','through_june15_2025']:
        for year in YEARS:
            end=pd.Timestamp(f'{year+1}-01-01') if year<2025 or scope=='calendar_year' else pd.Timestamp('2025-06-16')
            start=pd.Timestamp(f'{year}-01-01')
            for (op,mode),g in testing[testing.year.eq(year)].groupby(['operator','mode']):
                sf=state=imputed=0.
                for _,r in g.iterrows():
                    a=pd.Timestamp(year=year,month=int(r.month),day=1);b=a+pd.offsets.MonthBegin(1)
                    fraction=max(0,(min(b,end)-a).days)/(b-a).days if a<end else 0
                    sf+=r.sf_miles*fraction;state+=r.statewide_miles*fraction
                    if r.month_status=='dec2025_estimated_mean_sep_nov': imputed+=r.sf_miles*fraction
                source_rows.append({'scope':scope,'year':year,'operator':op,'mode':mode,'stream':'testing_excluding_waymo_driverless',
                                   'sf_miles':sf,'statewide_miles':state,'estimated_december_sf_miles':imputed,
                                   'total_basis':'DMV calendar months times baseline-style SGO SF share',
                                   'window_start':str(start.date()),'window_end':str((end-pd.Timedelta(days=1)).date())})
            c=cruise[cruise.year.eq(year)]
            # Cruise operation outside Jun2022-Oct2023 is zero by the draft's
            # service-history assumption, not because a blank report equals zero.
            cmiles=float(c.miles.sum(min_count=1)) if c.miles.notna().any() else 0.
            source_rows.append({'scope':scope,'year':year,'operator':'CRUISE','mode':'commercial_driverless','stream':'cruise_commercial',
                               'sf_miles':cmiles,'statewide_miles':np.nan,'estimated_december_sf_miles':0,
                               'total_basis':'CPUC periods 1+2+3; assume fleet mileage in SF; inactive months zero by stated service history',
                               'window_start':str(start.date()),'window_end':str((end-pd.Timedelta(days=1)).date())})
    source=pd.DataFrame(source_rows)
    source.to_csv(OUT/'testing_cruise_operator_period_totals.csv',index=False)
    methods={
        'hybrid_hpms':('hpms_2022_static','dynamic','county_adjusted',False),
        'hybrid_sfcta':('sfcta_expanded','dynamic','county_adjusted',False),
        'fixed_waymo_footprint':('hpms_2022_static','fixed','county_adjusted',False),
        'legacy_geography_sensitivity':('hpms_2022_static','dynamic','legacy_labels',False),
        'testing_sf_upper':('hpms_2022_static','dynamic','county_adjusted',True)}
    rows=[]
    for name,(human,style,geo,upper) in methods.items():
        for scope in ['calendar_year','through_june15_2025']:
            for year in YEARS:
                human_w=human_shares(year,human)
                period=source[source.scope.eq(scope)&source.year.eq(year)]
                common={'candidate':name,'scope':scope,'year':year,'window_start':period.iloc[0].window_start,'window_end':period.iloc[0].window_end}
                for _,r in period.iterrows():
                    total=r.statewide_miles if upper and r.stream=='testing_excluding_waymo_driverless' else r.sf_miles
                    for zone in zones:
                        rows.append(common|{'superzone_id':zone,'operator':r.operator,'mode':r['mode'],'stream':r.stream,
                                           'av_mileage_miles':total*human_w.loc[zone],'stream_operator_total_miles':total,
                                           'spatial_basis':human,'total_basis':r.total_basis+('; SF screening upper: all CA testing assigned to SF' if upper and r.stream=='testing_excluding_waymo_driverless' else ''),
                                           'estimated_december_sf_miles':r.estimated_december_sf_miles if not upper else np.nan})
                w,basis=waymo_shares(year,scope,style,geo,human)
                if year<=2024:
                    total=float(anchors.loc[year,'waymo_ro_million']*1e6)
                    total_basis='rounded original-paper calendar-year Waymo RO anchor'
                else:
                    at=curves[geo]
                    stop='2025-06-16' if scope=='through_june15_2025' else '2026-01-01'
                    total=float((at(stop)-at('2025-01-01')).sum())
                    total_basis='difference of reconciled monotone cumulative SF cell estimates; within-snapshot interval uniform daily mileage'
                for zone in zones:
                    rows.append(common|{'superzone_id':zone,'operator':'WAYMO','mode':'rider_only_testing_plus_commercial','stream':'waymo_rider_only',
                                       'av_mileage_miles':total*w.loc[zone],'stream_operator_total_miles':total,
                                       'spatial_basis':basis+'; 99% Waymo + 1% human regularization; '+geo,
                                       'total_basis':total_basis,'estimated_december_sf_miles':0.})
    operator=pd.DataFrame(rows)
    operator['av_mileage_million_miles']=operator.av_mileage_miles/1e6
    operator.to_csv(OUT/'operator_zone_year_all_candidates.csv.gz',index=False,compression={'method':'gzip','mtime':0})
    keys=['candidate','scope','year','window_start','window_end','superzone_id']
    streams=operator.groupby(keys+['stream']).av_mileage_miles.sum().unstack('stream').reset_index()
    stream_cols=['testing_excluding_waymo_driverless','waymo_rider_only','cruise_commercial']
    streams['av_mileage_miles']=streams[stream_cols].sum(axis=1)
    streams['av_mileage_million_miles']=streams.av_mileage_miles/1e6
    streams['data_status']='modeled_complete_zone_candidate_not_observed_all_fleet_mileage'
    streams.to_csv(OUT/'combined_zone_year_all_candidates.csv',index=False)
    for (name,scope),g in streams.groupby(['candidate','scope']):
        g.to_csv(OUT/f'{name}_{scope}.csv',index=False)
    totals=operator.groupby(['candidate','scope','year','stream']).av_mileage_miles.sum().reset_index()
    totals.to_csv(OUT/'stream_totals_and_windows.csv',index=False)
    pd.DataFrame(spatial_audits).drop_duplicates().to_csv(OUT/'waymo_spatial_allocation_audit.csv',index=False)
    comparison=streams.pivot(index=['scope','year','superzone_id'],columns='candidate',values='av_mileage_million_miles').reset_index()
    comparison.to_csv(OUT/'candidate_comparison_million_miles.csv',index=False)
    # Conservation and temporal/overlap safeguards.
    assert len(streams)==5*2*5*65 and streams.av_mileage_miles.gt(0).all()
    assert not operator[(operator.operator=='WAYMO')&(operator['mode']=='driverless')].shape[0]
    assert not operator.duplicated(keys+['operator','mode']).any()
    sums=operator.groupby(['candidate','scope','year','operator','mode']).agg(allocated=('av_mileage_miles','sum'),target=('stream_operator_total_miles','first'))
    error=float((sums.allocated-sums.target).abs().max()); assert error<1e-6
    for y in YEARS:
        left=streams[(streams.year==y)&(streams.scope=='calendar_year')].set_index(['candidate','superzone_id']).av_mileage_miles
        right=streams[(streams.year==y)&(streams.scope=='through_june15_2025')].set_index(['candidate','superzone_id']).av_mileage_miles
        if y<2025: np.testing.assert_allclose(left,right)
    inputs=[REPO/'data/mileage/dmv_testing_monthly.csv',REPO/'data/mileage/sgo_ca_incidents.csv',ROOT/'inputs/paper_commercial_mileage_anchors.csv',ROOT/'outputs/human_mileage_candidates/human_mileage_all_candidates.csv',ROOT/'outputs/s2_to_superzone_weights.csv']
    summary={'date':'2026-10-29','status':'complete estimated-data handoff for the paper scope',
             'source_manifest_sha256':hashlib.sha256((ROOT/'sources.json').read_bytes()).hexdigest(),
             'main_candidates':['hybrid_hpms','hybrid_sfcta'],'sensitivity_candidates':list(methods)[2:],
             'rows_per_candidate_per_scope':325,'scopes':['calendar_year','through_june15_2025'],
             'operator_mode_pairs':int(operator[['operator','mode']].drop_duplicates().shape[0]),
             'operator_rows':len(operator),'max_conservation_error_miles':error,
             'inputs':{str(p.relative_to(REPO)):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs},
             'assumptions':['2021-2024 Waymo totals retain rounded author estimates, not independently reconstructed exact totals',
                            'legacy operational-location cells apportioned to SF using June2026 per-cell SF county mileage fraction',
                            'monotone least-squares fit; missing interior snapshots interpolated, pre-first-observation cells assumed zero',
                            'Dec2025 testing estimated from Sep-Nov2025 mean for each operator/mode',
                            'Cruise fleet mileage assumed SF; pre-service and post-cessation blank/unreported months assumed zero',
                            'all SF component mileage allocated among 65 study zones; Waymo spatial weights regularized with 1% human shares',
                            'other testing and Cruise spatial weights are human-mileage proxies, not observed operator routes',
                            'paper-scope fleets only; zero SGO allocation is an assumption, not proof of no operation; not a census of all California AV activity']}
    (OUT/'validation.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps({k:v for k,v in summary.items() if k not in ['inputs','assumptions']},indent=2))
    print(totals[totals.candidate.eq('hybrid_hpms')].to_string(index=False))


if __name__=='__main__': main()
