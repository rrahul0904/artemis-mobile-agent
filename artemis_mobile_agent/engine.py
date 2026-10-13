from __future__ import annotations
import threading, time, uuid
from .devices import DeviceBackend, make_backend
from .models import Action, ActionResult, Observation, Profile, RunRecord, RunRequest, RunStatus, StepRecord
from .planner import Planner, make_planner
from .policy import ActionPolicy
from .store import TraceStore
from .verifier import Verifier, make_verifier
from .video import generate_replay_video

class TaskControl:
    def __init__(self):
        self.cancel = threading.Event()
        self.pause = threading.Event()
        self.pause.set()
        self.approval_event = threading.Event()
        self.approval_id: str | None = None

class Engine:
    def __init__(self, backend: DeviceBackend | None = None, planner: Planner | None = None, store: TraceStore | None = None, verifier: Verifier | None = None, policy: ActionPolicy | None = None):
        self.backend = backend or make_backend()
        self.planner = planner or make_planner()
        self.verifier = verifier or make_verifier()
        self.policy = policy or ActionPolicy()
        self.store = store or TraceStore()
        self.controls: dict[str, TaskControl] = {}
        self.threads: dict[str, threading.Thread] = {}
        self.device_locks: dict[str, threading.Lock] = {}
    def devices(self):
        return self.backend.list_devices()
    def _choose_device(self, requested: str | None):
        devices = [d for d in self.devices() if d.state == "device"]
        if requested:
            if requested not in {d.serial for d in devices}:
                raise ValueError(f"Device {requested!r} is not attached and authorized")
            return requested
        if not devices:
            raise ValueError("No attached/authorized Android device found")
        for d in devices:
            lock = self.device_locks.get(d.serial)
            if not lock or not lock.locked():
                return d.serial
        return devices[0].serial
    def submit(self, req: RunRequest, background: bool = True):
        serial = self._choose_device(req.device_serial)
        now = time.time()
        rid = str(uuid.uuid4())
        run = RunRecord(id=rid, goal=req.goal, profile=req.profile, status=RunStatus.PENDING, device_serial=serial, created_at=now, updated_at=now, message="queued")
        self.store.write_run(run)
        self.store.event(rid, "run_created", {**run.model_dump(), "verification_level": req.verification_level, "explorer_mode": req.explorer_mode})
        ctrl = TaskControl()
        self.controls[rid] = ctrl
        if background:
            t = threading.Thread(target=self._execute, args=(run, req, ctrl), daemon=True, name=f"artemis-{rid[:8]}")
            self.threads[rid] = t
            t.start()
        else:
            self._execute(run, req, ctrl)
        return run
    def _bootstrap_app(self, serial: str, req: RunRequest):
        dummy = Observation()
        if req.app_path:
            result = self.backend.execute(serial, Action(type="install_apk", apk_path=req.app_path), dummy)
            if not result.ok:
                raise RuntimeError(f"APK install failed: {result.message or result.stderr}")
        if req.locked_app_package:
            result = self.backend.execute(serial, Action(type="launch_app", package=req.locked_app_package), dummy)
            if not result.ok:
                raise RuntimeError(f"App launch failed: {result.message or result.stderr}")
    def _locked_app_ok(self, req: RunRequest, observation: Observation) -> bool:
        if not req.locked_app_package or not observation.activity:
            return True
        return req.locked_app_package in observation.activity or observation.activity.startswith("fake/")
    def _wait_for_approval(self, run: RunRecord, req: RunRequest, ctrl: TaskControl, step_number: int, action: Action, before: Observation):
        decision = self.policy.assess(action, before)
        self.store.event(run.id, "policy", {"step": step_number, "risk": decision.risk.value, "approval_required": decision.approval_required, "reason": decision.reason, "target_fingerprint": decision.target_fingerprint})
        if not decision.approval_required:
            return "allow", None, before

        approval = self.policy.approval_payload(
            run_id=run.id,
            session_id=run.id,
            step_id=step_number,
            action=action,
            observation=before,
            decision=decision,
        )
        approval["approval_id"] = str(uuid.uuid4())
        approval["status"] = "pending"
        self.store.write_approval(run.id, approval)
        self.store.event(run.id, "approval_requested", approval)

        ctrl.approval_id = approval["approval_id"]
        ctrl.approval_event.clear()
        run.status = RunStatus.PAUSED
        run.message = f"approval required: {decision.reason}"
        run.updated_at = time.time()
        self.store.write_run(run)
        self.store.event(run.id, "status", {"status": "paused", "reason": "approval_required", "approval_id": approval["approval_id"]})

        while not ctrl.approval_event.wait(timeout=.25):
            if ctrl.cancel.is_set():
                return "cancel", approval, before

        resolved = self.store.read_approval(run.id, approval["approval_id"])
        ctrl.approval_id = None
        if not resolved:
            return "deny", approval, before
        status = resolved.get("status")
        if status == "denied":
            return "deny", resolved, before
        if status == "changed":
            return "change", resolved, before
        if status != "approved":
            return "deny", resolved, before

        valid, reason = self.policy.validate_binding(resolved, run_id=run.id, action=action, observation=before)
        if not valid:
            resolved["status"] = "invalid"
            resolved["invalid_reason"] = reason
            self.store.write_approval(run.id, resolved)
            self.store.event(run.id, "approval_invalid", {"approval_id": resolved["approval_id"], "reason": reason})
            return "deny", resolved, before

        # Re-observe immediately before the write. For ADB transports this adds the
        # stale-state protection that the device-native companion already enforces.
        fresh = self.backend.observe(run.device_serial, self.store.artifacts_dir(run.id), step_number * 2)
        expected = resolved.get("observation_digest")
        actual = fresh.digest or self.policy.observation_digest(fresh)
        if expected != actual:
            resolved["status"] = "stale"
            resolved["stale_observation_digest"] = actual
            self.store.write_approval(run.id, resolved)
            self.store.event(run.id, "approval_stale", {"approval_id": resolved["approval_id"], "expected": expected, "actual": actual})
            return "stale", resolved, fresh

        resolved["consumed_at"] = time.time()
        self.store.write_approval(run.id, resolved)
        self.store.event(run.id, "approval_consumed", {"approval_id": resolved["approval_id"], "intent_digest": resolved.get("intent_digest")})
        return "approve", resolved, fresh
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
                self._bootstrap_app(serial, req)
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
                    if not self._locked_app_ok(req, before):
                        raise RuntimeError(f"locked app boundary violated: expected {req.locked_app_package}, observed {before.activity}")
                    self.store.event(run.id, "observation", {"step": n, "elements": len(before.elements), "activity": before.activity, "screenshot": before.screenshot_path, "sequence": before.sequence, "digest": before.digest})
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
                    if action.type == "finish" and action.success and req.profile == Profile.PRO and req.verification_level != "off":
                        verified, reason = self.verifier.verify(req.goal, before, req.expected_output)
                        verification = f"final-check: {reason}"
                        if not verified:
                            self.store.event(run.id, "verification_failed", {"step": n, "reason": reason})
                            result = ActionResult(ok=False, message=reason)
                            step = StepRecord(number=n, thought=decision.thought, action=action, result=result, before=before, after=before, verification=verification)
                            self.store.append_step(run.id, step)
                            history.append(step.model_dump())
                            if req.verification_level == "strict" and n >= req.max_steps - 1:
                                run.status = RunStatus.FAILED
                                run.message = reason
                                run.error = reason
                                break
                            continue

                    approval_state, approval, approved_before = self._wait_for_approval(run, req, ctrl, n, action, before)
                    if approval_state == "cancel":
                        run.status = RunStatus.CANCELLED
                        run.message = "cancelled while awaiting approval"
                        break
                    if approval_state in {"deny", "change", "stale"}:
                        if approval_state == "change":
                            message = "CHANGES REQUESTED: " + str((approval or {}).get("decision_text") or "revise the action")
                        elif approval_state == "stale":
                            message = "approval invalidated because the screen changed"
                        else:
                            message = "human denied risky action"
                        result = ActionResult(ok=False, message=message)
                        step = StepRecord(number=n, thought=decision.thought, action=action, result=result, before=before, after=approved_before, verification=f"policy: {message}")
                        self.store.append_step(run.id, step)
                        self.store.event(run.id, "step_blocked", {"number": n, "action": action.model_dump(), "reason": message, "approval_id": (approval or {}).get("approval_id")})
                        history.append(step.model_dump())
                        run.status = RunStatus.RUNNING
                        run.message = "running"
                        run.updated_at = time.time()
                        self.store.write_run(run)
                        continue

                    run.status = RunStatus.RUNNING
                    run.message = "running"
                    run.updated_at = time.time()
                    self.store.write_run(run)
                    before_for_execution = approved_before if approval_state == "approve" else before
                    result = self.backend.execute(serial, action, before_for_execution)
                    after = before_for_execution if action.type == "finish" else self.backend.observe(serial, self.store.artifacts_dir(run.id), n * 2)
                    if not self._locked_app_ok(req, after):
                        raise RuntimeError(f"locked app boundary violated after action: expected {req.locked_app_package}, observed {after.activity}")
                    if req.profile == Profile.PRO and req.verification_level in {"checkpoints", "strict"} and action.type != "finish":
                        verification = (verification + "; " if verification else "") + f"checkpoint: post-state captured with {len(after.elements)} visible elements"
                    step = StepRecord(number=n, thought=decision.thought, action=action, result=result, before=before_for_execution, after=after, verification=verification)
                    self.store.append_step(run.id, step)
                    self.store.event(run.id, "step", {"number": n, "thought": decision.thought, "action": action.model_dump(), "result": result.model_dump(), "verification": verification})
                    history.append(step.model_dump())
                    run.steps = n
                    run.updated_at = time.time()
                    self.store.write_run(run)
                    if action.type == "finish":
                        run.status = RunStatus.SUCCEEDED if action.success else RunStatus.FAILED
                        run.message = action.message or ("succeeded" if action.success else "failed")
                        run.result = {"success": bool(action.success), "message": run.message, "evidence": {"screenshot": before_for_execution.screenshot_path, "activity": before_for_execution.activity}, "verification": verification}
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
            if req.record_video:
                video = generate_replay_video(self.store.artifacts_dir(run.id), self.store.run_dir(run.id) / "replay.mp4")
                if video:
                    run.result = run.result or {}
                    run.result["video"] = video
                    self.store.event(run.id, "video", {"path": video})
            run.updated_at = time.time()
            self.store.write_run(run)
            self.store.event(run.id, "status", {"status": run.status.value, "message": run.message})
    def resolve_approval(self, run_id: str, approval_id: str, decision: str, text: str | None = None):
        run = self.store.read_run(run_id)
        if not run:
            raise KeyError(run_id)
        approval = self.store.read_approval(run_id, approval_id)
        if not approval:
            raise KeyError(approval_id)
        if approval.get("status") != "pending":
            raise ValueError(f"approval is already {approval.get('status')}")
        if float(approval.get("expires_at") or 0) < time.time():
            approval["status"] = "expired"
            approval["decision_at"] = time.time()
            self.store.write_approval(run_id, approval)
            raise ValueError("approval expired")
        approval["status"] = {"approve": "approved", "deny": "denied", "change": "changed"}[decision]
        approval["decision_at"] = time.time()
        if text:
            approval["decision_text"] = text
        self.store.write_approval(run_id, approval)
        self.store.event(run_id, "approval_decided", {"approval_id": approval_id, "status": approval["status"], "text": text})
        ctrl = self.controls.get(run_id)
        if ctrl and ctrl.approval_id == approval_id:
            ctrl.approval_event.set()
        return approval
    def manage(self, run_id: str, action: str):
        run = self.store.read_run(run_id)
        if not run:
            raise KeyError(run_id)
        ctrl = self.controls.get(run_id)
        if not ctrl:
            return run
        if action == "cancel":
            ctrl.cancel.set()
            ctrl.approval_event.set()
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
        return {"run": run.model_dump(), "steps": [s.model_dump() for s in self.store.read_steps(run_id)], "events": self.store.read_events(run_id), "approvals": self.store.list_approvals(run_id)}
    def diagnose(self):
        devices = self.devices()
        return {"ok": bool(devices), "backend": type(self.backend).__name__, "planner": type(self.planner).__name__, "verifier": type(self.verifier).__name__, "trace_dir": str(self.store.root.resolve()), "devices": [d.model_dump() for d in devices], "issues": [] if devices else ["No attached/authorized Android device detected"]}