from pathlib import Path
from artemis_mobile_agent.devices import FakeBackend
from artemis_mobile_agent.engine import Engine
from artemis_mobile_agent.models import Profile, RunRequest, RunStatus
from artemis_mobile_agent.planner import HeuristicPlanner
from artemis_mobile_agent.store import TraceStore

def make_engine(tmp_path):
    return Engine(FakeBackend(), HeuristicPlanner(), TraceStore(tmp_path / "traces"))

def test_flash_acceptance(tmp_path):
    e = make_engine(tmp_path)
    r = e.submit(RunRequest(goal="Open Settings, go to Battery and verify battery percentage", profile=Profile.FLASH), background=False)
    r = e.store.read_run(r.id)
    assert r.status == RunStatus.SUCCEEDED
    assert r.steps >= 2
    assert "87%" in r.result["message"]
    t = e.trace(r.id)
    assert len(t["steps"]) >= 2
    assert Path(t["steps"][0]["before"]["screenshot_path"]).exists()

def test_pro_has_precheck(tmp_path):
    e = make_engine(tmp_path)
    r = e.submit(RunRequest(goal="Open Settings, go to Battery and verify battery percentage", profile=Profile.PRO), background=False)
    t = e.trace(r.id)
    assert t["run"]["status"] == "succeeded"
    assert any((s.get("verification") or "").startswith("precheck") for s in t["steps"])

def test_strict_device_binding(tmp_path):
    e = make_engine(tmp_path)
    try:
        e.submit(RunRequest(goal="open settings", device_serial="missing"), background=False)
    except ValueError as ex:
        assert "not attached" in str(ex)
    else:
        raise AssertionError("expected rejection")

def test_trace_events(tmp_path):
    e = make_engine(tmp_path)
    r = e.submit(RunRequest(goal="Open Settings, go to Battery and verify battery percentage"), background=False)
    t = e.trace(r.id)
    assert any(x["type"] == "run_created" for x in t["events"])
    assert any(x["type"] == "step" for x in t["events"])
