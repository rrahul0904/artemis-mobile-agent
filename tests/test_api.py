import importlib, time
from fastapi.testclient import TestClient

def test_api_acceptance(tmp_path, monkeypatch):
    monkeypatch.setenv("ARTEMIS_FAKE_DEVICE", "1")
    monkeypatch.setenv("ARTEMIS_TRACE_DIR", str(tmp_path / "traces"))
    import artemis_mobile_agent.api as api
    importlib.reload(api)
    c = TestClient(api.app)
    assert c.get("/health").status_code == 200
    assert c.get("/api/devices").json()[0]["serial"] == "fake-android-001"
    r = c.post("/api/runs", json={"goal": "Open Settings, go to Battery and verify battery percentage", "profile": "flash"})
    assert r.status_code == 202
    rid = r.json()["id"]
    for _ in range(100):
        run = c.get(f"/api/runs/{rid}").json()
        if run["status"] in {"succeeded", "failed", "cancelled"}:
            break
        time.sleep(.02)
    assert run["status"] == "succeeded"
    tr = c.get(f"/api/runs/{rid}/trace").json()
    assert len(tr["steps"]) >= 2
    assert c.get("/").status_code == 200
    assert "Artemis Mobile Agent" in c.get("/").text
