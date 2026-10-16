"""California ADS crashes from the NHTSA Standing General Order (SGO) files, one row per incident.

    python mileage/build_sgo_ca.py <SGO folder> sgo_ca_incidents.csv

<SGO folder> holds the two ADS incident files downloaded from NHTSA: the release before the
mid-2025 change of format ("pre summer 25 ...") and the current one. Only incidents in California with the ADS engaged are kept, and
one report per incident (latest version). The shipped data/mileage/sgo_ca_incidents.csv contains
the same 1,755 incidents; for three incidents reported by two entities whose reports disagree on
the city or the operator type, it keeps the other report, which is why the shipped file, not this
script's output, is the input of sf_testing_miles.py.
"""
import argparse, os, re
import pandas as pd

KNOWN = ['WAYMO', 'CRUISE', 'ZOOX', 'APPLE', 'APOLLO', 'ARGO AI', 'AUTOX', 'GHOST', 'MAY', 'MERCEDES', 'NURO',
         'NVIDIA', 'OHMIO', 'PONY', 'WERIDE']


def operator(name):
    u = str(name).upper().strip()
    for k in KNOWN:
        if re.match(rf'^{k}\b', u) or (k == 'PONY' and u.startswith('PONY')):
            return k
    return u[:15]


def load(sgo_dir, files):
    out = []
    for fn, tag in files:
        d = pd.read_csv(os.path.join(sgo_dir, fn), dtype=str, encoding='latin1')
        d = d[d['State'].str.strip().eq('CA')].copy()
        d['ver'] = pd.to_numeric(d['Report Version'])
        d = d.sort_values('ver').drop_duplicates('Report ID', keep='last')
        d['src'] = tag
        out.append(d)
    a = pd.concat(out, ignore_index=True)
    a = a[a['Automation System Engaged?'].eq('ADS')]
    # An incident can be reported by several entities (e.g. Cruise and General Motors, Waymo and
    # Transdev): one report is kept per incident.
    a = a.sort_values(['src', 'ver']).drop_duplicates(['src', 'Same Incident ID'], keep='last')
    a['op'] = a['Operating Entity'].map(operator)
    a['year'] = pd.to_datetime(a['Incident Date'], format='%b-%Y').dt.year
    a['sf'] = a['City'].str.upper().str.strip().eq('SAN FRANCISCO')
    a['onboard'] = a['Driver / Operator Type'].fillna('').str.startswith('In-Vehicle')
    return a


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('sgo_dir'); ap.add_argument('out')
    ap.add_argument('--old', default='pre summer 25 SGO-2021-01_Incident_Reports_ADS.csv')
    ap.add_argument('--new', default='SGO-2021-01_Incident_Reports_ADS.csv')
    a = ap.parse_args()
    s = load(a.sgo_dir, [(a.old, 'pre'), (a.new, 'SGO')])
    s[['Report ID', 'Same Incident ID', 'src', 'op', 'year', 'Incident Date', 'City', 'Driver / Operator Type', 'sf', 'onboard']].to_csv(a.out, index=False)
    print(len(s), 'California ADS incidents ->', a.out)
