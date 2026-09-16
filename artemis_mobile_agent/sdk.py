from __future__ import annotations
import time
import httpx

class ArtemisClient:
    def __init__(self, base_url: str = "http://127.0.0.1:8000", token: str | None = None, timeout: float = 30):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        self.client = httpx.Client(base_url=base_url.rstrip("/"), headers=headers, timeout=timeout)
    def close(self): self.client.close()
    def __enter__(self): return self
    def __exit__(self, *_): self.close()
    def devices(self):
        r = self.client.get("/api/devices"); r.raise_for_status(); return r.json()
    def run(self, goal: str, profile: str = "flash", device_serial: str | None = None, **kwargs):
        body = {"goal": goal, "profile": profile, "device_serial": device_serial, **kwargs}
        r = self.client.post("/api/runs", json={k:v for k,v in body.items() if v is not None}); r.raise_for_status(); return r.json()
    def status(self, run_id: str):
        r = self.client.get(f"/api/runs/{run_id}"); r.raise_for_status(); return r.json()
    def manage(self, run_id: str, action: str):
        r = self.client.post(f"/api/runs/{run_id}/manage", json={"action": action}); r.raise_for_status(); return r.json()
    def trace(self, run_id: str):
        r = self.client.get(f"/api/runs/{run_id}/trace"); r.raise_for_status(); return r.json()
    def wait(self, run_id: str, timeout: float = 300, poll: float = .5):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            state = self.status(run_id)
            if state["status"] in {"succeeded", "failed", "cancelled"}: return state
            time.sleep(poll)
        raise TimeoutError(run_id)
