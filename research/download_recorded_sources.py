"""Restore pinned public sources sequentially; changed source bytes fail closed."""
import json
from fetch_sources import ROOT, fetch


if __name__ == '__main__':
    for name, record in json.loads((ROOT/'sources.json').read_text()).items():
        fetch(record['url'], name, record.get('description', ''))
