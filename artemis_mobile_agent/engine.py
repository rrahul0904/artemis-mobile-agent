from __future__ import annotations
import threading, time, uuid
from .devices import DeviceBackend, make_backend
from .models import ActionResult, Profile, RunRecord, RunRequest, RunStatus, StepRecord
from .planner import Planner, make_planner
from .store import TraceStore

class TaskControl:
    def __init__(self):
        self.cancel = threading.Event()
        self.pause = threading.Event()
        self.pause.set()

class Engine:
    def __init__(self, backend: DeviceBackend | None = None, planner: Planner | None = None, store: TraceStore | None = None):
        self.backend = backend or make_backend()
        self.planner = planner or make_planner()
        self.store = store or TraceStore()
        self.controls: dict[str, TaskControl] = {}
        self.threads: dict[str, threading.Thread] = {}
        self.device_locks: dict[str, threading.Lock] = {}
    def devices(self):
        return self.backend.list_devices()
    def submit(self, req: RunRequest, background: bool = True):
        devices = [d for d in self.devices() if d.state == "device"]
        if req.device_serial:
            if req.device_serial not in {d.serial for d in devices}:
                raise ValueError(f"Device {req.device_serial!r} is not attached and authorized")
            serial = req.device_serial
        else:
            if not devices:
                raise ValueError("No attached/authorized Android device found")
            serial = devices[0].serial
        now = time.time()
        rid = str(uuid.uuid4())
        run = RunRecord(id=rid, goal=req.goal, profile=req.profile, status=RunStatus.PENDING, device_serial=serial, created_at=now, updated_at=now, message="queued")
        self.store.write_run(run)
        self.store.event(rid, "run_created", run.model_dump())
        ctrl = TaskControl()
        self.controls[rid] = ctrl
        if background:
            t = threading.Thread(target=self._execute, args=(run, req, ctrl), daemon=True, name=f"artemis-{rid[:8]}")
            self.threads[rid] = t
            t.start()
        else:
            self._execute(run, req, ctrl)
        return run
    def _execute(self, run: RunRecord, req: RunRequest, ctrl: TaskControl):
        serial = run.device_serial
        lock = self.device_locks.setdefault(serial, threading.Lock())
        with lock:
            run.status = RunStatus.RUNNING
            run.message = "running"
            run.updated_at = time.time()
            self.store.write_run(run)
            self.store.event(run.id, "status", {"status": "running"})
            history: list[dict] = []
            try:
                for n in range(1, req.max_steps + 1):
                    if ctrl.cancel.is_set():
                        run.status = RunStatus.CANCELLED
                        run.message = "cancelled"
                        break
                    while not ctrl.pause.wait(timeout=.25):
                        if ctrl.cancel.is_set():
                            break
                    if ctrl.cancel.is_set():
                        run.status = RunStatus.CANCELLED
                        run.message = "cancelled"
                        break
                    before = self.backend.observe(serial, self.store.artifacts_dir(run.id), n * 2 - 1)
                    self.store.event(run.id, "observation", {"step": n, "elements": len(before.elements), "activity": before.activity, "screenshot": before.screenshot_path})
                    decision = self.planner.decide(req.goal, req.profile, before, history)
                    action = decision.action
                    verification = None
                    if req.profile == Profile.PRO and action.type == "click" and action.target_index is not None:
                        if action.target_index >= len(before.elements):
                            result = ActionResult(ok=False, message="Pro precheck blocked stale target index")
                            step = StepRecord(number=n, thought=decision.thought, action=action, result=result, before=before, verification="blocked: target absent before action")
                            self.store.append_step(run.id, step)
                            history.append(step.model_dump())
                            continue
                        verification = f"precheck: element #{action.target_index} exists"
                    result = self.backend.execute(serial, action, before)
                    after = before if action.type == "finish" else self.backend.observe(serial, self.store.artifacts_dir(run.id), n * 2)
                    step = StepRecord(number=n, thought=decision.thought, action=action, result=result, before=before, after=after, verification=verification)
                    self.store.append_step(run.id, step)
                    self.store.event(run.id, "step", {"number": n, "thought": decision.thought, "action": action.model_dump(), "result": result.model_dump(), "verification": verification})
                    history.append(step.model_dump())
                    run.steps = n
                    run.updated_at = time.time()
                    self.store.write_run(run)
                    if action.type == "finish":
                        run.status = RunStatus.SUCCEEDED if action.success else RunStatus.FAILED
                        run.message = action.message or ("succeeded" if action.success else "failed")
                        run.result = {"success": bool(action.success), "message": run.message, "evidence": {"screenshot": before.screenshot_path, "activity": before.activity}}
                        break
                    if not result.ok and req.profile == Profile.PRO:
                        self.store.event(run.id, "recovery", {"step": n, "reason": result.message})
                        continue
                else:
                    run.status = RunStatus.FAILED
                    run.message = f"max steps ({req.max_steps}) reached"
                    run.error = run.message
            except Exception as e:
                run.status = RunStatus.FAILED
                run.error = str(e)
                run.message = "runtime failure"
                self.store.event(run.id, "error", {"error": repr(e)})
            run.updated_at = time.time()
            self.store.write_run(run)
            self.store.event(run.id, "status", {"status": run.status.value, "message": run.message})
    def manage(self, run_id: str, action: str):
        run = self.store.read_run(run_id)
        if not run:
            raise KeyError(run_id)
        ctrl = self.controls.get(run_id)
        if not ctrl:
            return run
        if action == "cancel":
            ctrl.cancel.set()
        elif action == "pause":
            ctrl.pause.clear()
            run.status = RunStatus.PAUSED
            run.message = "pause requested"
            self.store.write_run(run)
        elif action == "resume":
            ctrl.pause.set()
            run.status = RunStatus.RUNNING
            run.message = "resume requested"
            self.store.write_run(run)
        return self.store.read_run(run_id)
    def wait(self, run_id: str, timeout: float = 30):
        t = self.threads.get(run_id)
        if t:
            t.join(timeout)
        return self.store.read_run(run_id)
    def trace(self, run_id: str):
        run = self.store.read_run(run_id)
        if not run:
            raise KeyError(run_id)
        return {"run": run.model_dump(), "steps": [s.model_dump() for s in self.store.read_steps(run_id)], "events": self.store.read_events(run_id)}
    def diagnose(self):
        devices = self.devices()
        return {
            "ok": bool(devices),
            "backend": type(self.backend).__name__,
            "planner": type(self.planner).__name__,
            "trace_dir": str(self.store.root.resolve()),
            "devices": [d.model_dump() for d in devices],
            "issues": [] if devices else ["No attached/authorized Android device detected"],
        }
