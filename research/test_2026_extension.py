import json
import numpy as np
import pandas as pd
from build_2026_extension import OUT, crash_counts


def test_window_and_exposure_conservation():
    d=pd.read_csv(OUT/'all_candidates.csv');v=json.loads((OUT/'validation.json').read_text())
    assert len(d)==260 and d.window_start.eq('2026-01-01').all() and d.window_end.eq('2026-06-30').all()
    for _,g in d.groupby(['reference_method','waymo_location_allocation']):
        assert len(g)==65 and g.superzone_id.nunique()==65
        for col,key in [('reference_mileage_million_miles','reference_million_miles'),('waymo_ro_mileage_million_miles','waymo_ro_million_miles')]:
            assert np.isfinite(g[col]).all() and g[col].gt(0).all()
            np.testing.assert_allclose(g[col].sum(),v[key])
        np.testing.assert_allclose(g.n_waymo_police_injury.sum(),8)
        assert g.n_reference_injury.sum()==1559


def test_outcome_selection_and_event_deduplication():
    d=pd.read_csv(OUT/'waymo_h1_event_audit.csv')
    assert len(d)==158 and d['SGO Report ID'].nunique()==157
    u=d.drop_duplicates('SGO Report ID')
    eligible=u['Is Police-Reported']&u['Is Any-Injury-Reported']&u['Is NHTSA Reportable In-Transport']&u['Road Type'].eq('Surface Street')
    assert eligible.equals(u.selected_outcome) and eligible.sum()==8
    assert u['Is Any-Injury-Reported'].sum()==14


def test_fractional_assignment_preserves_events_without_forcing_unknowns():
    d=pd.DataFrame({'point_zone_id':[1,2,np.nan],'zone_candidates':['1;2','2',np.nan]})
    np.testing.assert_allclose(crash_counts(d,[1,2],'point'),[1,1])
    np.testing.assert_allclose(crash_counts(d,[1,2],'fractional_candidates'),[.5,1.5])


def test_missing_reference_locations_retained():
    d=pd.read_csv(OUT/'reference_h1_event_audit.csv')
    assert len(d)==1578 and d.case_id_pkey.nunique()==1578
    assert d.geographic_status.eq('unique_zone').sum()==1559
    assert d.geographic_status.eq('missing_coordinates').sum()==15


def test_monthly_volume_imputation_and_city_days():
    d=pd.read_csv(OUT/'segment_month_volume_audit.csv')
    assert d.groupby('cmp_segid').size().eq(6).all()
    assert d.volume_imputed.sum()==101 and d.imp_vol.notna().all()
    for _,g in d.groupby('cmp_segid'):
        if g.volume_imputed.any():
            np.testing.assert_allclose(g.loc[g.volume_imputed,'imp_vol'],g.loc[~g.volume_imputed,'imp_vol'].mean())
    city=pd.read_csv(OUT/'citywide_monthly_mileage.csv')
    assert len(city)==6 and city.days.sum()==181
