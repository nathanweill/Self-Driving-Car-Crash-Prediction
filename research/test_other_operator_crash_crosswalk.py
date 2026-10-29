import pandas as pd
from build_other_operator_crash_crosswalk import OUT


def test_report_join_and_outcome_preservation():
    d=pd.read_csv(OUT/'zoox_sf_h1_crash_crosswalk.csv')
    assert len(d)==17 and d['Report ID'].nunique()==17 and d.incident_key.nunique()==17
    assert d.same_report_version.all() and d._merge.eq('both').all()
    assert d.injury_status.value_counts().to_dict()=={'reported_no_injury':13,'reported_injury':2,'unknown':2}
    assert d.loc[d.injury_status.eq('reported_injury'),'superzone_id'].eq(36).all()


def test_zone_counts_conserve_reports_and_unknowns():
    d=pd.read_csv(OUT/'zoox_sf_h1_zone_crash_diagnostics.csv')
    assert len(d)==65 and d.superzone_id.nunique()==65
    assert d.reported_crashes_assigned.sum()==17
    assert d.reported_injury_assigned.sum()==2
    assert d.unknown_severity_assigned.sum()==2


def test_unverified_service_and_police_status_not_inferred():
    d=pd.read_csv(OUT/'zoox_sf_h1_crash_crosswalk.csv')
    assert d.passenger_pilot_scope.eq('not_established').all()
    assert d.police_report_status.eq('not_established').all()
    assert d.date_precision_used.str.startswith('month').all()
