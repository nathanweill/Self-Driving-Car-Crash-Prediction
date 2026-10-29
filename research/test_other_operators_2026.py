import json
import numpy as np
import pandas as pd
from audit_other_operators_2026 import OUT


def test_zoox_mileage_periods_and_totals():
    d=pd.read_csv(OUT/'zoox_monthly_mileage.csv')
    assert len(d)==12 and not d.duplicated(['mode','month']).any()
    assert d.groupby('mode').month.apply(lambda s: sorted(s)==[1,2,3,4,5,6]).all()
    np.testing.assert_allclose(d.pilot_vmt_miles,d[['period1_miles','period2_miles','period3_miles']].sum(axis=1))
    totals=pd.DataFrame(json.loads((OUT/'pilot_quarterly_totals.json').read_text()))
    for mode,g in d.groupby('mode'):
        np.testing.assert_allclose(g.pilot_vmt_miles.sum(),totals[(totals.operator=='Zoox')&(totals['mode']==mode)].reported_pilot_miles.sum())


def test_collision_period_problem_is_exposed():
    audit=json.loads((OUT/'zoox_source_audit.json').read_text())
    collisions=[r for r in audit if r['sheet']=='Incidents-Location']
    assert len(collisions)==4 and all(not r['usable_as_sf_injury_count'] for r in collisions)
    assert all(r['all_tracts_redacted'] for r in collisions)
    assert all(not r['quarter_matches_archive'] for r in collisions if r['archive_quarter']==2)


def test_missing_is_not_zero_and_scenarios_are_labeled():
    s=json.loads((OUT/'summary.json').read_text())
    assert 'unknown' in s['aurora_q2'] and 'unknown' in s['nuro_q1']
    values=[r['zoox_driverless_sf_pilot_miles'] for r in s['zoox_driverless_sf_sensitivity']]
    total=next(r['available_period_pilot_miles'] for r in s['totals'] if r['operator']=='Zoox' and r['mode']=='driverless')
    np.testing.assert_allclose(values,[0,.25*total,.5*total,.75*total,total],atol=.005)
