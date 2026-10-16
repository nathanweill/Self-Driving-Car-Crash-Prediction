"""Monthly autonomous-mode miles per manufacturer from the California DMV mileage reports.

    python mileage/build_dmv_monthly.py <DMV report folder> data/mileage/dmv_testing_monthly.csv

<DMV report folder> is the unzipped DMV download "2015-2025 autonomous vehicle disengagement
reports", with one sub-folder per report year containing "* Autonomous Mileage Reports (CSV).csv"
(testing with a safety driver) and "* (driverless).csv" (driverless testing).
"""
import glob
import os
import re
import sys

import pandas as pd

MONTHS = {m: i + 1 for i, m in enumerate(['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC'])}


def main(root, out, years=range(2021, 2026)):
    rows = []
    for y in years:
        for f in sorted(glob.glob(os.path.join(root, str(y), '*Mileage*.csv'))):
            d = pd.read_csv(f, dtype=str, encoding='latin1')
            d.columns = [c.strip().lstrip('ï»¿') for c in d.columns]
            kind = 'driverless' if 'driverless' in f.lower() else 'drivered'
            mfr = d[d.columns[0]].str.upper().str.strip().str.extract(r'^(\w+)', expand=False)
            for c in d.columns:
                cu = c.upper().strip()
                m1 = re.match(r'^([A-Z]{3})[A-Z]* (\d{4})$', cu)
                m2 = re.match(r'^(\d{2})-([A-Z]{3})$', cu)
                if m1:
                    mo, yr = MONTHS[m1.group(1)], int(m1.group(2))
                elif m2:
                    mo, yr = MONTHS[m2.group(2)], 2000 + int(m2.group(1))
                else:
                    continue
                v = pd.to_numeric(d[c].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
                for k, val in v.groupby(mfr).sum().items():
                    rows.append(dict(kind=kind, mfr=k, year=yr, month=mo, miles=val))
    x = pd.DataFrame(rows).groupby(['kind', 'mfr', 'year', 'month']).miles.sum().reset_index()
    x.to_csv(out, index=False)
    print(len(x), 'rows ->', out)


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
