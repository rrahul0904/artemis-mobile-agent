from __future__ import annotations
import asyncio, json
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse
from .engine import Engine
from .models import ManageRequest, RunRequest

engine = Engine()
app = FastAPI(title="Artemis Mobile Agent", version="0.2.0")

@app.get("/health")
def health():
    return {"status": "ok", "service": "artemis-mobile-agent", "diagnostics": engine.diagnose()}

@app.get("/api/devices")
def devices():
    return [d.model_dump() for d in engine.devices()]

@app.get("/api/runs")
def runs():
    return [r.model_dump() for r in engine.store.list_runs()]

@app.post("/api/runs", status_code=202)
def create_run(req: RunRequest):
    try:
        return engine.submit(req).model_dump()
    except ValueError as e:
        raise HTTPException(409, str(e)) from e

@app.get("/api/runs/{run_id}")
def get_run(run_id: str):
    run = engine.store.read_run(run_id)
    if not run:
        raise HTTPException(404, "run not found")
    return run.model_dump()

@app.post("/api/runs/{run_id}/manage")
def manage(run_id: str, req: ManageRequest):
    try:
        return engine.manage(run_id, req.action).model_dump()
    except KeyError as e:
        raise HTTPException(404, "run not found") from e

@app.get("/api/runs/{run_id}/trace")
def trace(run_id: str):
    try:
        return engine.trace(run_id)
    except KeyError as e:
        raise HTTPException(404, "run not found") from e

@app.get("/api/runs/{run_id}/logcat")
def logcat(run_id: str, lines: int = 200):
    run = engine.store.read_run(run_id)
    if not run:
        raise HTTPException(404, "run not found")
    return {"run_id": run_id, "device_serial": run.device_serial, "logcat": engine.backend.logcat(run.device_serial, lines)}

@app.get("/api/diagnostics")
def diagnostics():
    return engine.diagnose()

@app.get("/api/runs/{run_id}/artifacts/{name}")
def artifact(run_id: str, name: str):
    base = engine.store.artifacts_dir(run_id).resolve()
    p = (base / name).resolve()
    if base not in p.parents or not p.exists():
        raise HTTPException(404, "artifact not found")
    return FileResponse(p)

@app.websocket("/ws/runs/{run_id}")
async def run_ws(ws: WebSocket, run_id: str):
    await ws.accept()
    last = None
    try:
        while True:
            try:
                payload = engine.trace(run_id)
            except KeyError:
                await ws.send_json({"error": "run not found"})
                return
            encoded = json.dumps(payload, default=str, sort_keys=True)
            if encoded != last:
                await ws.send_json(payload)
                last = encoded
            if payload["run"]["status"] in {"succeeded", "failed", "cancelled"}:
                return
            await asyncio.sleep(.4)
    except WebSocketDisconnect:
        return

INDEX = r'''<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Artemis Mobile Agent</title><style>
body{font-family:Inter,system-ui;background:#0b1020;color:#e8ecf4;margin:0}.wrap{max-width:1100px;margin:auto;padding:28px}.card{background:#121a2f;border:1px solid #27324f;border-radius:14px;padding:18px;margin:14px 0}input,select,button{background:#0e162b;color:#fff;border:1px solid #34405f;border-radius:8px;padding:10px}input{width:60%}button{cursor:pointer;background:#315efb}.grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}pre{white-space:pre-wrap;max-height:420px;overflow:auto;font-size:12px}@media(max-width:800px){.grid{grid-template-columns:1fr}input{width:100%}}
</style></head><body><div class="wrap"><h1>Artemis Mobile Agent</h1><p>Trace-first autonomous Android testing runtime.</p>
<div class="card"><input id="goal" value="Open Settings, go to Battery and verify battery percentage"><select id="profile"><option value="flash">Flash</option><option value="pro">Pro</option></select><button onclick="runTask()">Run task</button></div>
<div class="grid"><div class="card"><h3>Devices</h3><pre id="devices"></pre></div><div class="card"><h3>Run</h3><pre id="run"></pre></div></div><div class="card"><h3>Live trace</h3><pre id="trace"></pre></div></div>
<script>
async function refreshDevices(){devices.textContent=JSON.stringify(await (await fetch('/api/devices')).json(),null,2)}
async function runTask(){let r=await fetch('/api/runs',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({goal:goal.value,profile:profile.value})});let x=await r.json();run.textContent=JSON.stringify(x,null,2);if(!r.ok)return;let ws=new WebSocket(`${location.protocol==='https:'?'wss':'ws'}://${location.host}/ws/runs/${x.id}`);ws.onmessage=e=>{let d=JSON.parse(e.data);trace.textContent=JSON.stringify(d,null,2);run.textContent=JSON.stringify(d.run||d,null,2)}} refreshDevices()
</script></body></html>'''

@app.get("/", response_class=HTMLResponse)
def index():
    return INDEX
