from rippermod_manager.schemas.deploy import (
    DeployOp,
    DeployPlan,
    DeployReport,
    DriftReport,
    PreflightReport,
)


def test_deploy_op_roundtrip():
    op = DeployOp(operation="link", src="staging/foo", dst="r6/scripts/foo")
    assert op.operation == "link"


def test_deploy_plan_is_empty_when_no_ops():
    p = DeployPlan(game_id=1)
    assert p.is_empty


def test_preflight_report_defaults():
    r = PreflightReport()
    assert r.ok is True
    assert r.reasons == []


def test_drift_report_counters():
    r = DriftReport(total=10, linked=8, missing=2, foreign=0)
    assert r.is_clean is False


def test_deploy_report_clean_when_no_failures():
    r = DeployReport(total=3, done=3, failed=0)
    assert r.is_clean is True
