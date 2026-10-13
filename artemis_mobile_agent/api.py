from __future__ import annotations
import asyncio, html, json, os
from pathlib import Path
from fastapi import Depends, FastAPI, Header, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse
from .engine import Engine
from .models import ApprovalDecisionRequest, ManageRequest, RunRequest

engine = Engine()
app = FastAPI(title="Artemis Mobile Agent", version="0.3.0")

def require_token(authorization: str | None = Header(default=None)):
    expected = os.getenv("ARTEMIS_API_TOKEN")
    if not expected:
        return
    supplied = authorization.removeprefix("Bearer ").strip() if authorization else ""
    if supplied != expected:
        raise HTTPException(401, "invalid API token")

secure = [Depends(require_token)]

@app.get("/health")
def health():
    return {"status": "ok", "service": "artemis-mobile-agent", "diagnostics": engine.diagnose()}

@app.get("/api/devices", dependencies=secure)
def devices():
    return [d.model_dump() for d in engine.devices()]

@app.get("/api/runs", dependencies=secure)
def runs():
    return [r.model_dump() for r in engine.store.list_runs()]

@app.post("/api/runs", status_code=202, dependencies=secure)
def create_run(req: RunRequest):
    try:
        return engine.submit(req).model_dump()
    except ValueError as e:
        raise HTTPException(409, str(e)) from e

@app.get("/api/runs/{run_id}", dependencies=secure)
def get_run(run_id: str):
    run = engine.store.read_run(run_id)
    if not run:
        raise HTTPException(404, "run not found")
    return run.model_dump()

@app.post("/api/runs/{run_id}/manage", dependencies=secure)
def manage(run_id: str, req: ManageRequest):
    try:
        return engine.manage(run_id, req.action).model_dump()
    except KeyError as e:
        raise HTTPException(404, "run not found") from e

@app.get("/api/runs/{run_id}/approvals/pending", dependencies=secure)
def pending_approval(run_id: str):
    if not engine.store.read_run(run_id):
        raise HTTPException(404, "run not found")
    approval = engine.store.pending_approval(run_id)
    return {"run_id": run_id, "approval": approval}

@app.post("/api/runs/{run_id}/approvals/{approval_id}", dependencies=secure)
def decide_approval(run_id: str, approval_id: str, req: ApprovalDecisionRequest):
    try:
        return engine.resolve_approval(run_id, approval_id, req.decision, req.text)
    except KeyError as e:
        raise HTTPException(404, "run or approval not found") from e
    except ValueError as e:
        raise HTTPException(409, str(e)) from e

@app.get("/api/runs/{run_id}/trace", dependencies=secure)
def trace(run_id: str):
    try:
        return engine.trace(run_id)
    except KeyError as e:
        raise HTTPException(404, "run not found") from e

@app.get("/api/runs/{run_id}/logcat", dependencies=secure)
def logcat(run_id: str, lines: int = 200):
    run = engine.store.read_run(run_id)
    if not run:
        raise HTTPException(404, "run not found")
    return {"run_id": run_id, "device_serial": run.device_serial, "logcat": engine.backend.logcat(run.device_serial, lines)}

@app.get("/api/diagnostics", dependencies=secure)
def diagnostics():
    return engine.diagnose()

@app.get("/api/runs/{run_id}/artifacts/{name}", dependencies=secure)
def artifact(run_id: str, name: str):
    base = engine.store.artifacts_dir(run_id).resolve()
    p = (base / name).resolve()
    if base not in p.parents or not p.exists():
        raise HTTPException(404, "artifact not found")
    return FileResponse(p)

@app.get("/api/runs/{run_id}/video", dependencies=secure)
def video(run_id: str):
    p = engine.store.run_dir(run_id) / "replay.mp4"
    if not p.exists():
        raise HTTPException(404, "video not recorded")
    return FileResponse(p, media_type="video/mp4")

@app.get("/api/runs/{run_id}/replay", response_class=HTMLResponse, dependencies=secure)
def replay(run_id: str):
    try:
        t = engine.trace(run_id)
    except KeyError as e:
        raise HTTPException(404, "run not found") from e
    rows = []
    for s in t["steps"]:
        shot = Path(s["before"]["screenshot_path"]).name if s["before"].get("screenshot_path") else None
        image = f'<img src="/api/runs/{run_id}/artifacts/{html.escape(shot)}" style="max-width:280px;max-height:500px">' if shot else ""
        rows.append(f"<article><h3>Step {s['number']}: {html.escape(s['action']['type'])}</h3>{image}<pre>{html.escape(json.dumps({'thought':s['thought'],'action':s['action'],'result':s['result'],'verification':s.get('verification')}, indent=2, default=str))}</pre></article>")
    approvals = html.escape(json.dumps(t.get("approvals", []), indent=2, default=str))
    return f"<!doctype html><meta charset='utf-8'><title>Replay {run_id}</title><style>body{{font-family:system-ui;background:#0b1020;color:#e8ecf4;max-width:1000px;margin:auto;padding:24px}}article{{border:1px solid #27324f;border-radius:12px;padding:16px;margin:16px 0}}pre{{white-space:pre-wrap}}</style><h1>Replay</h1><p>{html.escape(t['run']['goal'])}</p><h2>Approval receipts</h2><pre>{approvals}</pre>{''.join(rows)}"

@app.websocket("/ws/runs/{run_id}")
async def run_ws(ws: WebSocket, run_id: str, token: str | None = Query(default=None)):
    expected = os.getenv("ARTEMIS_API_TOKEN")
    auth = ws.headers.get("authorization", "").removeprefix("Bearer ").strip()
    if expected and token != expected and auth != expected:
        await ws.close(code=4401)
        return
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
body{font-family:Inter,system-ui;background:#0b1020;color:#e8ecf4;margin:0}.wrap{max-width:1100px;margin:auto;padding:28px}.card{background:#121a2f;border:1px solid #27324f;border-radius:14px;padding:18px;margin:14px 0}input,select,button{background:#0e162b;color:#fff;border:1px solid #34405f;border-radius:8px;padding:10px}input{width:55%}button{cursor:pointer;background:#315efb}.grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}pre{white-space:pre-wrap;max-height:420px;overflow:auto;font-size:12px}a{color:#93c5fd}@media(max-width:800px){.grid{grid-template-columns:1fr}input{width:100%}}
</style></head><body><div class="wrap"><h1>Artemis Mobile Agent</h1><p>Trace-first autonomous Android testing runtime.</p>
<div class="card"><input id="goal" value="Open Settings, go to Battery and verify battery percentage"><select id="profile"><option value="flash">Flash</option><option value="pro">Pro</option></select><label><input id="recordVideo" type="checkbox" style="width:auto"> video</label><button onclick="runTask()">Run task</button></div>
<div class="grid"><div class="card"><h3>Devices</h3><pre id="devices"></pre></div><div class="card"><h3>Run</h3><div id="links"></div><pre id="run"></pre></div></div><div class="card"><h3>Live trace</h3><pre id="trace"></pre></div></div>
<script>
const apiToken=localStorage.getItem('artemis_api_token')||'';const headers={'content-type':'application/json',...(apiToken?{'authorization':'Bearer '+apiToken}:{})};
async function refreshDevices(){devices.textContent=JSON.stringify(await (await fetch('/api/devices',{headers})).json(),null,2)}
async function runTask(){let r=await fetch('/api/runs',{method:'POST',headers,body:JSON.stringify({goal:goal.value,profile:profile.value,record_video:recordVideo.checked})});let x=await r.json();run.textContent=JSON.stringify(x,null,2);if(!r.ok)return;links.innerHTML=`<a target="_blank" href="/api/runs/${x.id}/replay">Replay</a>`;let ws=new WebSocket(`${location.protocol==='https:'?'wss':'ws'}://${location.host}/ws/runs/${x.id}${apiToken?'?token='+encodeURIComponent(apiToken):''}`);ws.onmessage=e=>{let d=JSON.parse(e.data);trace.textContent=JSON.stringify(d,null,2);run.textContent=JSON.stringify(d.run||d,null,2)}} refreshDevices()
</script></body></html>'''

@app.get("/", response_class=HTMLResponse)
def index():
    return INDEX