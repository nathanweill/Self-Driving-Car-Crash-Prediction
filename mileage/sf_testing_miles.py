"""San Francisco autonomous testing mileage N_A(t) (million miles, DMV report years Dec-Nov).

    python mileage/sf_testing_miles.py            # reads and writes data/mileage/

The DMV mileage reports are statewide. Each operator's miles are attributed to San Francisco
with the share of its California SGO crashes (testing with someone on board) that occurred in
San Francisco: by year for Waymo, pooled over 2021-2025 for the other operators; operators
without any California SGO crash get no San Francisco miles. Waymo's driverless miles cannot be
separated from its commercial service in the SGO data, so three cases are computed:
low (none in San Francisco), mid (SF share of Waymo's driverless SGO crashes; used in the
paper) and high (all in San Francisco).
"""
import os

import numpy as np
import pandas as pd

D = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'mileage')
YEARS = range(2021, 2026)


def main():
    x = pd.read_csv(os.path.join(D, 'dmv_testing_monthly.csv'))
    x['ry'] = x.year + (x.month == 12)                    # DMV report year: December to November
    x = x[x.ry.isin(YEARS)]
    M = x.pivot_table(index=['mfr', 'kind'], columns='ry', values='miles', aggfunc='sum').fillna(0) / 1e6
    s = pd.read_csv(os.path.join(D, 'sgo_ca_incidents.csv'))
    s = s[s.year.isin(YEARS)]
    s['kind'] = np.where(s.onboard, 'drivered', 'driverless')

    def share(op, kind, yr=None):
        z = s[(s.op == op) & (s.kind == kind)]
        if yr is not None:
            z = z[z.year == yr]
        return (z.sf.sum() / len(z)) if len(z) else np.nan, len(z)

    rows = []
    for (m, k), row in M.iterrows():
        for y in M.columns:
            if row[y] == 0:
                continue
            if m == 'WAYMO' and k == 'drivered':
                sh, n = share('WAYMO', 'drivered', y)
            elif m == 'WAYMO' and k == 'driverless':
                sh, n = np.nan, 0                            # set by scenario below
            else:
                sh, n = share(m, 'drivered')
                if k == 'driverless':
                    sh2, n2 = share(m, 'driverless')
                    sh, n = (sh2, n2) if n2 else (sh, n)
                if n == 0:
                    sh = 0.0
            rows.append(dict(mfr=m, kind=k, year=y, miles=row[y], sf_share=sh, n_sgo=n))
    r = pd.DataFrame(rows)
    out = {}
    for name, val in [('low', 0.0), ('mid', None), ('high', 1.0)]:
        rr = r.copy()
        w = (rr.mfr == 'WAYMO') & (rr.kind == 'driverless')
        if val is None:
            rr.loc[w, 'sf_share'] = rr.loc[w, 'year'].map(
                lambda y: share('WAYMO', 'driverless', y)[0] if share('WAYMO', 'driverless', y)[1] else 1.0)
        else:
            rr.loc[w, 'sf_share'] = val
        out[name] = (rr.miles * rr.sf_share).groupby(rr.year).sum()
    T = pd.DataFrame(out)
    T['statewide'] = r.groupby('year').miles.sum()
    T.index.name = 'year'
    r.to_csv(os.path.join(D, 'sf_testing_share_by_operator.csv'), index=False)
    T.to_csv(os.path.join(D, 'sf_testing_miles.csv'))
    print('N_A(t), million miles (config/paper.yaml uses "mid"):')
    print(T.round(2).T.to_string())


if __name__ == '__main__':
    main()
