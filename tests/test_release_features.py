import importlib, shutil
from fastapi.testclient import TestClient
from artemis_mobile_agent.devices import FakeBackend
from artemis_mobile_agent.engine import Engine
from artemis_mobile_agent.models import Profile, RunRequest
from artemis_mobile_agent.planner import HeuristicPlanner
from artemis_mobile_agent.store import TraceStore
from artemis_mobile_agent.video import generate_replay_video

def test_pro_final_verification_and_checkpoint(tmp_path):
    e = Engine(FakeBackend(), HeuristicPlanner(), TraceStore(tmp_path / "traces"))
    r = e.submit(RunRequest(goal="Open Settings, go to Battery and verify battery percentage", profile=Profile.PRO, verification_level="strict"), background=False)
    t = e.trace(r.id)
    assert t["run"]["status"] == "succeeded"
    assert any("checkpoint:" in (s.get("verification") or "") for s in t["steps"][:-1])
    assert "final-check:" in (t["steps"][-1].get("verification") or "")

def test_api_token_and_replay(tmp_path, monkeypatch):
    monkeypatch.setenv("ARTEMIS_FAKE_DEVICE", "1")
    monkeypatch.setenv("ARTEMIS_TRACE_DIR", str(tmp_path / "traces"))
    monkeypatch.setenv("ARTEMIS_API_TOKEN", "secret")
    import artemis_mobile_agent.api as api
    importlib.reload(api)
    c = TestClient(api.app)
    assert c.get("/api/devices").status_code == 401
    h = {"Authorization": "Bearer secret"}
    assert c.get("/api/devices", headers=h).status_code == 200
    r = c.post("/api/runs", headers=h, json={"goal":"Open Settings, go to Battery and verify battery percentage"})
    rid = r.json()["id"]
    api.engine.wait(rid)
    replay = c.get(f"/api/runs/{rid}/replay", headers=h)
    assert replay.status_code == 200 and "Replay" in replay.text

def test_video_export_if_ffmpeg_available(tmp_path):
    if not shutil.which("ffmpeg"):
        return
    e = Engine(FakeBackend(), HeuristicPlanner(), TraceStore(tmp_path / "traces"))
    r = e.submit(RunRequest(goal="Open Settings, go to Battery and verify battery percentage", record_video=True), background=False)
    state = e.store.read_run(r.id)
    assert state.status.value == "succeeded"
    assert state.result.get("video")
