"""Recover public CPUC pilot mileage, preserving program/geography limitations."""
import hashlib
import io
import json
from pathlib import Path
import zipfile
import pandas as pd

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'outputs/other_operators_2026'


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    totals=[];monthly=[];audit=[]
    for quarter in (1,2):
        archive=ROOT/f'raw/cpuc_pilot/2026q{quarter}.zip'
        with zipfile.ZipFile(archive) as z:
            for n in z.namelist():
                if n.endswith('/') or '/Waymo/' in n:continue
                operator=n.split('/')[1]
                if operator=='Zoox' and (n.endswith('.xlsx') or n.endswith('Month-Level.csv') or n.endswith('Incidents-Location.csv')):
                    mode='driverless' if 'Driverless' in n else 'drivered'
                    sheets=['Month-Level','Incidents-Location'] if n.endswith('.xlsx') else [Path(n).stem]
                    for sheet in sheets:
                        raw=z.read(n)
                        d=pd.read_excel(io.BytesIO(raw),sheet_name=sheet) if n.endswith('.xlsx') else pd.read_csv(io.BytesIO(raw))
                        d=d.dropna(how='all');d=d.loc[:,~d.columns.str.startswith('Unnamed:')]
                        d.to_csv(OUT/f'zoox_q{quarter}_{mode}_{sheet.lower()}.csv',index=False)
                        entry={'archive':archive.name,'member':n,'member_sha256':hashlib.sha256(raw).hexdigest(),'sheet':sheet,'operator':operator,'mode':mode,'archive_quarter':quarter,'rows':len(d)}
                        if sheet=='Month-Level':
                            assert len(d)==3 and d.Year.eq(2026).all()
                            assert sorted(d.Month.astype(int))==list(range(quarter*3-2,quarter*3+1))
                            cols=['TotalVMTPeriod1','TotalVMTPeriod2','TotalVMTPeriod3']
                            assert d[cols].notna().all().all() and d[cols].ge(0).all().all()
                            for _,row in d.iterrows():
                                monthly.append({'operator':operator,'mode':mode,'year':2026,'month':int(row.Month),'period1_miles':row.TotalVMTPeriod1,'period2_miles':row.TotalVMTPeriod2,'period3_miles':row.TotalVMTPeriod3,'pilot_vmt_miles':float(row[cols].sum())})
                            totals.append({'operator':operator,'mode':mode,'quarter':quarter,'reported_pilot_miles':float(d[cols].sum().sum()),'metric':'sum VMT periods 1+2+3','source_member':n,'source_sheet':sheet,'sf_geography':'redacted'})
                        else:
                            entry['reported_quarter_labels']=sorted(d.Quarter.dropna().unique().tolist())
                            entry['quarter_matches_archive']=set(entry['reported_quarter_labels'])=={f'Q{quarter}'}
                            entry['all_tracts_redacted']=bool(d.Tract.eq('REDACTED').all())
                            entry['disclosed_all_collision_sum']=float(d.CollisionsAll.sum(min_count=1))
                            entry['usable_as_sf_injury_count']=False
                        audit.append(entry)
                elif n.endswith('.xlsx') and operator in ['Tensor','Nuro','WeRide']:
                    x=pd.ExcelFile(io.BytesIO(z.read(n)))
                    sheets=['Master'] if operator=='Tensor' else ['Q2 2026 (April-June)'] if operator=='Nuro' else ['DriveredPilotProgramReport','DriverlessPilotProgramReport']
                    for sheet in sheets:
                        d=pd.read_excel(x,sheet_name=sheet,header=None)
                        mask=d[0].astype(str).str.startswith('Total quarterly vehicle miles traveled during passenger service by all vehicles')
                        assert mask.sum()==1
                        idx=d.index[mask][0];value=float(d.loc[idx,1])
                        # Total cell only, never add per-vehicle columns to the total.
                        assert value>=0
                        mode='driverless' if sheet.startswith('Driverless') else 'drivered'
                        totals.append({'operator':operator,'mode':mode,'quarter':quarter,'reported_pilot_miles':value,'metric':'reported quarterly passenger-service VMT','source_member':n,'source_sheet':sheet,'source_cell':f'B{idx+1}','sf_geography':'not supplied','note':'May 7-June 30 permit period; cover letter corrects workbook June 31 typo' if operator=='Nuro' else ''})
    pd.DataFrame(monthly).to_csv(OUT/'zoox_monthly_mileage.csv',index=False)
    (OUT/'pilot_quarterly_totals.json').write_text(json.dumps(totals,indent=2)+'\n')
    (OUT/'zoox_source_audit.json').write_text(json.dumps(audit,indent=2)+'\n')
    d=pd.DataFrame(totals)
    grouped=d.groupby(['operator','mode']).reported_pilot_miles.sum()
    summary=[{'operator':op,'mode':mode,'available_period_pilot_miles':round(float(miles),2),'quarters_present':sorted(d[(d.operator==op)&(d['mode']==mode)].quarter.tolist())} for (op,mode),miles in grouped.items()]
    zoox_driverless=float(grouped.loc[('Zoox','driverless')])
    # Bounds apply to the disclosed pilot component only, not all operator testing.
    sensitivity=[{'assumed_sf_fraction':f,'zoox_driverless_sf_pilot_miles':round(f*zoox_driverless,2),'interpretation':'scenario only; no preferred estimate; does not include non-passenger testing'} for f in [0,.25,.5,.75,1]]
    result={'as_of':'2026-10-29','totals':summary,'zoox_driverless_sf_sensitivity':sensitivity,'aurora_q1':'Attests zero passenger trips; no total testing mileage inferred','aurora_q2':'not in archive; unknown','nuro_q1':'not in archive; unknown','collision_use':'Zoox geography redacted, outcome all collisions, and Q2 table labels Q1; do not add to matched injury panel','coverage':'CPUC passenger pilot program only; not total autonomous testing mileage or deployment mileage'}
    (OUT/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
