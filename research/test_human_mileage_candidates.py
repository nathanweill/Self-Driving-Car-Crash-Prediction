import numpy as np
import pandas as pd
from build_human_mileage_candidates import expand_network, calibrate, OUT, ROOT


def test_missing_zone_gets_pooled_density():
    d=pd.DataFrame({'partial_network_annual_vmt_proxy':[1000.,np.nan],
                    'surface_centerline_within_20m_cmp_m':[100.,0.],
                    'official_surface_centerline_m':[200.,200.]})
    x=expand_network(d,.5,100.)
    assert x.loc[1,'raw_full_zone_miles']==1000
    assert x.loc[1,'imputed_share_before_calibration']==1
    assert x.loc[0,'raw_full_zone_miles']==1500


def test_calibration_preserves_shares_and_total():
    x=calibrate(pd.DataFrame({'raw_full_zone_miles':[1.,3.]}),20.)
    np.testing.assert_allclose(x.human_mileage_million_miles,[5.,15.])


def test_complete_candidate_outputs_and_anchor_conservation():
    x=pd.read_csv(OUT/'human_mileage_all_candidates.csv')
    anchors=pd.read_csv(ROOT.parent/'results/panel.csv').groupby('year').N_H.first()
    assert len(x)==5*65*5
    assert not x.duplicated(['method','year','superzone_id']).any()
    assert x.human_mileage_miles.gt(0).all() and np.isfinite(x.human_mileage_miles).all()
    for (_,year),g in x.groupby(['method','year']):
        assert len(g)==65
        np.testing.assert_allclose(g.human_mileage_million_miles.sum(),anchors.loc[year],rtol=1e-12)


def test_hpms_shares_constant_and_sfcta_missing_zone_flagged():
    x=pd.read_csv(OUT/'hpms_2022_static.csv')
    assert x.groupby('superzone_id').zone_share.apply(lambda s:s.max()-s.min()).max()<1e-12
    d=pd.read_csv(OUT/'sfcta_expanded_diagnostics.csv')
    assert d.loc[d.superzone_id.eq(31),'source_missing'].all()
    assert d.loc[d.superzone_id.eq(31),'imputed_share_before_calibration'].eq(1).all()


def test_lower_missing_road_assumption_reduces_raw_imputation():
    low=pd.read_csv(OUT/'sfcta_expanded_low_diagnostics.csv')
    high=pd.read_csv(OUT/'sfcta_expanded_equal_diagnostics.csv')
    np.testing.assert_allclose(high.imputed_component_miles,4*low.imputed_component_miles)
