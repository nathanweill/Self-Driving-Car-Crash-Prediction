"""Standalone scientific figure of the exposure coverage diagnostic."""
from pathlib import Path
import os
import tempfile
import geopandas as gpd
import pandas as pd
os.environ.setdefault('MPLCONFIGDIR', str(Path(tempfile.gettempdir()) / 'av-crash-matplotlib-cache'))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent


def main():
    zones = gpd.read_file(ROOT.parent / 'results/zones.geojson').to_crs(26910)
    coverage = pd.read_csv(ROOT / 'outputs/sfcta_zone_road_coverage.csv')
    zones = zones.merge(coverage, on='superzone_id')
    zones['coverage_pct'] = 100 * zones.surface_centerline_coverage_fraction
    segments = gpd.read_file(ROOT / 'outputs/sfcta_segments.geojson').to_crs(26910)
    fig, ax = plt.subplots(figsize=(9, 8))
    zones.plot(column='coverage_pct', cmap='YlGnBu', vmin=0, vmax=100, linewidth=.5, edgecolor='#5b6470', ax=ax,
               legend=True, legend_kwds={'label': 'Surface-street length covered (%)', 'shrink': .65})
    segments.clip(zones.geometry.union_all()).plot(ax=ax, color='#283747', linewidth=.35, alpha=.7)
    p = zones.loc[zones.superzone_id.eq(31)].geometry.iloc[0].representative_point()
    ax.annotate('Zone 31: no segment observations', xy=(p.x, p.y), xytext=(30, 25), textcoords='offset points',
                fontsize=9, arrowprops={'arrowstyle': '->', 'color': '#222'}, bbox={'facecolor':'white','alpha':.9,'edgecolor':'none'})
    ax.set_axis_off()
    fig.suptitle('SFCTA dashboard coverage of the 65 study zones', fontsize=15, y=.97)
    fig.text(.08,.92,'Official surface centerlines within 20 m of the dashboard network; median coverage 36.5%.',fontsize=10)
    fig.text(.08,.04,'Coverage measures road length, not traffic or VMT share. Dark lines: dashboard segments.\nSources: SFCTA public API; SF DPW centerlines retrieved 2026-10-27; paper’s committed zones.',fontsize=9)
    fig.subplots_adjust(top=.88,bottom=.10,left=.05,right=.95)
    fig.savefig(ROOT/'outputs/sfcta_coverage.png',dpi=180,facecolor='white')
    plt.close(fig)


if __name__ == '__main__': main()
