from __future__ import annotations
from functools import lru_cache
from .engine import Engine
from .models import Profile, RunRequest

@lru_cache(maxsize=1)
def _engine():
    return Engine()

def mobile_run_task(task_desc: str, conversation_id: str | None = None, model: str = "Flash", device_serial: str | None = None, expected_output_desc: str | None = None, verification_level: str | None = None, explorer_mode: str | None = None, locked_app_package: str | None = None, app_path: str | None = None, record_video: bool = False):
    profile = Profile.PRO if model.lower() == "pro" else Profile.FLASH
    r = _engine().submit(RunRequest(goal=task_desc, profile=profile, device_serial=device_serial, expected_output=expected_output_desc, verification_level=verification_level or "final", explorer_mode=explorer_mode or "flash", locked_app_package=locked_app_package, app_path=app_path, record_video=record_video))
    return {"trace_id": r.id, "status": r.status.value, "device_serial": r.device_serial, "message": r.message}

def mobile_manage_task(action: str = "status", trace_id: str | None = None):
    if not trace_id:
        return {"status": "failed", "error": "trace_id required"}
    e = _engine()
    r = e.store.read_run(trace_id)
    if not r:
        return {"status": "not_found", "trace_id": trace_id}
    if action in {"cancel", "pause", "resume"}:
        r = e.manage(trace_id, action)
    return r.model_dump()

def mobile_get_device_state(device_serial: str | None = None):
    ds = _engine().devices()
    return {"devices": [d.model_dump() for d in ds], "selected": device_serial or (ds[0].serial if ds else None)}

def mobile_inspect_trace(trace_id: str, action: str = "view_summary", step_number: int | None = None, query: str | None = None):
    t = _engine().trace(trace_id)
    if action == "view_step_details" and step_number:
        return t["steps"][step_number - 1] if 0 < step_number <= len(t["steps"]) else {"error": "step not found"}
    if action == "search" and query:
        q = query.lower()
        return {"matches": [s for s in t["steps"] if q in str(s).lower()]}
    return t

def mobile_diagnose():
    return _engine().diagnose()
