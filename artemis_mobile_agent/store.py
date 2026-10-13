from __future__ import annotations
import json, os, threading, time
from pathlib import Path
from .models import RunRecord, StepRecord

class TraceStore:
    def __init__(self, root: str | Path | None = None):
        self.root = Path(root or os.getenv("ARTEMIS_TRACE_DIR", ".artemis/traces"))
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
    def run_dir(self, run_id: str) -> Path:
        p = self.root / run_id
        p.mkdir(parents=True, exist_ok=True)
        return p
    def artifacts_dir(self, run_id: str) -> Path:
        p = self.run_dir(run_id) / "artifacts"
        p.mkdir(exist_ok=True)
        return p
    def approvals_dir(self, run_id: str) -> Path:
        p = self.run_dir(run_id) / "approvals"
        p.mkdir(exist_ok=True)
        return p
    def write_run(self, run: RunRecord) -> None:
        target = self.run_dir(run.id) / "run.json"
        tmp = target.with_suffix(".json.tmp")
        with self._lock:
            tmp.write_text(run.model_dump_json(indent=2), encoding="utf-8")
            tmp.replace(target)
    def read_run(self, run_id: str) -> RunRecord | None:
        p = self.root / run_id / "run.json"
        return RunRecord.model_validate_json(p.read_text()) if p.exists() else None
    def append_step(self, run_id: str, step: StepRecord) -> None:
        p = self.run_dir(run_id) / "steps.jsonl"
        with self._lock, p.open("a", encoding="utf-8") as f:
            f.write(step.model_dump_json() + "\n")
    def read_steps(self, run_id: str) -> list[StepRecord]:
        p = self.root / run_id / "steps.jsonl"
        if not p.exists():
            return []
        return [StepRecord.model_validate_json(x) for x in p.read_text().splitlines() if x.strip()]
    def write_approval(self, run_id: str, approval: dict) -> None:
        approval_id = approval.get("approval_id")
        if not approval_id:
            raise ValueError("approval_id is required")
        target = self.approvals_dir(run_id) / f"{approval_id}.json"
        tmp = target.with_suffix(".json.tmp")
        with self._lock:
            tmp.write_text(json.dumps(approval, indent=2, sort_keys=True, default=str), encoding="utf-8")
            tmp.replace(target)
    def read_approval(self, run_id: str, approval_id: str) -> dict | None:
        p = self.root / run_id / "approvals" / f"{approval_id}.json"
        return json.loads(p.read_text()) if p.exists() else None
    def list_approvals(self, run_id: str) -> list[dict]:
        p = self.root / run_id / "approvals"
        if not p.exists():
            return []
        items = [json.loads(item.read_text()) for item in p.glob("*.json")]
        return sorted(items, key=lambda x: float(x.get("issued_at") or 0))
    def pending_approval(self, run_id: str) -> dict | None:
        for item in reversed(self.list_approvals(run_id)):
            if item.get("status") == "pending":
                return item
        return None
    def event(self, run_id: str, event_type: str, payload) -> None:
        p = self.run_dir(run_id) / "events.jsonl"
        row = {"ts": time.time(), "type": event_type, "payload": payload}
        with self._lock, p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, default=str) + "\n")
    def read_events(self, run_id: str):
        p = self.root / run_id / "events.jsonl"
        return [json.loads(x) for x in p.read_text().splitlines() if x.strip()] if p.exists() else []
    def list_runs(self, limit: int = 100):
        items = []
        for p in self.root.iterdir():
            if p.is_dir():
                r = self.read_run(p.name)
                if r:
                    items.append(r)
        return sorted(items, key=lambda x: x.created_at, reverse=True)[:limit]